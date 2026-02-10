import logging
import math
import time
from dataclasses import dataclass


import app.config as app_config_module
from app.config import (
    VOLATILITY_FOR_KF_WEIGHT_ATR,
    VOLATILITY_FOR_KF_WEIGHT_CURRENT,
    VOLATILITY_FLOOR,
)


logger = logging.getLogger(__name__)



@dataclass
class ProbabilityCoefficient:
    """Результат расчета вероятностного коэффициента."""


    kf: float  # сам коэффициент [0..1]
    math_probability: float  # математическая вероятность
    market_probability: float  # подразумеваемая вероятность из цены
    edge: float  # разница (edge)
    expected_move_pct: float  # ожидаемое движение за оставшееся время
    relative_deviation_pct: float  # насколько текущее изменение от expected
    reason: str  # объяснение
    # Детали расчета для логов
    current_price: float | None = None
    target_price: float | None = None
    volatility_pct: float | None = None
    time_remaining_minutes: float | None = None
    time_in_hours: float | None = None
    price_move_pct: float | None = None
    std_dev_pct: float | None = None
    z_score: float | None = None
    reach_probability: float | None = None
    inverted: bool = False



class PostEntryProbabilityAnalyzer:
    """
    Считает вероятности для post-entry сценариев.
    Используется для решения: докупать ли противоположную, свою сторону или выходить.
    """


    def __init__(self, rfr: float = 0.0):
        self.rfr = rfr
        self._last_exit_log_ts = 0.0


    def calculate_hybrid_volatility(
        self,
        volatility_current_pct: float,
        atr: float | None,
        current_price: float,
    ) -> tuple[float, float, float]:
        """
        Рассчитать гибридную волатильность для KF расчётов.


        Комбинирует:
        - ATR(14)-based волатильность (60%) — более стабильная
        - Текущую волатильность (40%) — более реактивная
        - Floor (0.5%) — protection от слишком спокойных периодов


        Returns:
            (volatility_for_kf, atr_pct, vol_current_pct)
        """
        atr_pct = 0.0
        if atr is not None and atr > 0 and current_price > 0:
            atr_pct = (atr / current_price)  # Уже в десятичной форме


        volatility_hybrid = (
            atr_pct * VOLATILITY_FOR_KF_WEIGHT_ATR
            + volatility_current_pct * VOLATILITY_FOR_KF_WEIGHT_CURRENT
        )


        volatility_for_kf = max(volatility_hybrid, VOLATILITY_FLOOR)


        return volatility_for_kf, atr_pct, volatility_current_pct


    def calculate_normal_cdf(self, x: float) -> float:
        """Normal CDF."""
        return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


    def calculate_expected_move(
        self,
        volatility_pct: float,
        time_remaining_minutes: float,
        vol_period_minutes: float = 60.0,
    ) -> float:
        """
        Ожидаемое движение = Vol x sqrt(T).
        """
        if vol_period_minutes <= 0:
            return 0.0
        expected_move = volatility_pct * math.sqrt(
            time_remaining_minutes / vol_period_minutes
        )
        return expected_move


    def calculate_reach_probability(
        self,
        current_price: float,
        target_price: float,
        volatility_pct: float,
        time_remaining_minutes: float,
        vol_period_minutes: float = 60.0,
    ) -> float:
        """
        Вероятность достичь target за оставшееся время.
        """
        if time_remaining_minutes <= 0 or volatility_pct <= 0:
            return 0.5


        price_move_pct = (target_price - current_price) / current_price
        if vol_period_minutes <= 0:
            return 0.5
        std_dev_pct = volatility_pct * math.sqrt(
            time_remaining_minutes / vol_period_minutes
        )


        if std_dev_pct == 0:
            return 0.5


        z_score = price_move_pct / std_dev_pct
        prob = 1.0 - self.calculate_normal_cdf(z_score)


        return max(0.0, min(1.0, prob))

    def calculate_absorption_probability(
        self,
        current_price: float,
        barrier_price: float,
        volatility_pct: float,
        time_remaining_minutes: float,
        vol_period_minutes: float = 60.0,
        risk_free_rate: float = 0.0,
        absorption_type: str = "up",
    ) -> float:
        """
        Вероятность того, что цена будет ВЫШЕ/НИЖЕ barrier_price в момент экспирации.

        Это terminal absorption probability - вероятность быть выше/ниже барьера в конце.

        Args:
            current_price: Текущая цена
            barrier_price: Барьерная цена (target)
            volatility_pct: Волатильность в процентах
            time_remaining_minutes: Оставшееся время в минутах
            vol_period_minutes: Период волатильности в минутах
            risk_free_rate: Безрисковая ставка (по умолчанию 0)
            absorption_type: "up" для P(S_T >= K), "down" для P(S_T <= K)

        Returns:
            Вероятность terminal absorption (0.0 - 1.0)
        """
        if time_remaining_minutes <= 0:
            # Время вышло - проверяем текущее положение
            if absorption_type == "up":
                return 1.0 if current_price >= barrier_price else 0.0
            else:  # down
                return 1.0 if current_price <= barrier_price else 0.0

        if volatility_pct <= 0:
            return 0.5

        # Используем простую нормальную аппроксимацию (как в exit analysis)
        # Для terminal probability используем CDF нормального распределения

        # Конвертируем волатильность в десятичную форму для расчетов
        vol_decimal = volatility_pct / 100.0

        # Рассчитываем std_dev за оставшееся время
        std_dev_pct = vol_decimal * math.sqrt(time_remaining_minutes / vol_period_minutes) * 100.0

        if std_dev_pct == 0:
            if absorption_type == "up":
                return 1.0 if current_price >= barrier_price else 0.0
            else:  # down
                return 1.0 if current_price <= barrier_price else 0.0

        # Целевое движение цены
        price_move_pct = ((barrier_price - current_price) / current_price) * 100.0

        # z-score
        z_score = price_move_pct / std_dev_pct

        if absorption_type == "up":
            # P(S_T >= barrier_price) = 1 - Φ(z_score)
            # Где z_score = (barrier_price - current_price) / std_dev
            absorption_prob = 1.0 - self.calculate_normal_cdf(z_score)
        else:  # down
            # P(S_T <= barrier_price) = Φ(z_score)
            absorption_prob = self.calculate_normal_cdf(z_score)

        return max(0.0, min(1.0, absorption_prob))


    def calculate_reach_details(
        self,
        current_price: float,
        target_price: float,
        volatility_pct: float,
        time_remaining_minutes: float,
        vol_period_minutes: float = 60.0,
    ) -> tuple[float, float, float, float, float]:
        """
        Возвращает (reach_prob, price_move_pct, std_dev_pct, z_score, time_in_hours).
        """
        if time_remaining_minutes <= 0 or volatility_pct <= 0:
            return 0.5, 0.0, 0.0, 0.0, time_remaining_minutes / 60.0

        price_move_pct = (target_price - current_price) / current_price
        time_in_hours = time_remaining_minutes / 60.0

        if vol_period_minutes <= 0:
            return 0.5, price_move_pct, 0.0, 0.0, time_in_hours

        std_dev_pct = volatility_pct * math.sqrt(time_remaining_minutes / vol_period_minutes)

        if std_dev_pct == 0:
            return 0.5, price_move_pct, std_dev_pct, 0.0, time_in_hours

        z_score = price_move_pct / std_dev_pct
        prob = 1.0 - self.calculate_normal_cdf(z_score)

        final_prob = max(0.0, min(1.0, prob))

        return final_prob, price_move_pct, std_dev_pct, z_score, time_in_hours


    def analyze_opposite_side_buy(
        self,
        current_price_btc: float,
        market_target: float,
        market_direction: str,
        opposite_side: str,
        volatility_pct: float,
        time_remaining_minutes: float,
        current_price_up: float,
        current_price_down: float,
        atr: float | None = None,
        vol_period_minutes: float = 60.0,
    ) -> ProbabilityCoefficient:
        """
        Анализирует, стоит ли ДОКУПАТЬ противоположную сторону.


        ЛОГИКА:
        1. Модель имеет мнение (market_direction): "будет UP" или "будет DOWN"
        2. Это отражается в reach_prob (вероятность дойти до market_target)
        3. Если opposite_side != market_direction → math_prob_opposite = 1.0 - reach_prob
        4. Если opposite_side == market_direction → math_prob_opposite = reach_prob


        Использует гибридную волатильность (ATR + текущая) для более
        стабильных KF расчётов.
        """
        vol_for_kf, atr_pct, vol_current = self.calculate_hybrid_volatility(
            volatility_pct, atr, current_price_btc
        )


        expected_move = self.calculate_expected_move(
            vol_for_kf, time_remaining_minutes, vol_period_minutes=vol_period_minutes
        )


        logger.debug(
            "[VOL HYBRID] ATR=%.3f%% vol_current=%.3f%% → vol_for_kf=%.3f%% "
            "(ATR_weight=%.1f%% current_weight=%.1f%% floor=%.2f%%)",
            atr_pct * 100,
            vol_current * 100,
            vol_for_kf * 100,
            VOLATILITY_FOR_KF_WEIGHT_ATR * 100,
            VOLATILITY_FOR_KF_WEIGHT_CURRENT * 100,
            VOLATILITY_FLOOR * 100,
        )


reach_prob_raw, price_move_pct, std_dev_pct, z_score, time_in_hours = (
    self.calculate_reach_details(
        current_price_btc,
        market_target,
        vol_for_kf,
        time_remaining_minutes,
        vol_period_minutes=vol_period_minutes,
    )
)

# reach_prob_raw = P(S_T > target) - вероятность быть выше target в конце
# Touch probabilities не зависят от текущего положения - это вероятность достижения цели
reach_prob_up = reach_prob_raw  # Вероятность быть выше target в конце
reach_prob_down = 1.0 - reach_prob_raw  # Вероятность быть ниже target в конце

if opposite_side == "UP":
    math_prob_opposite = reach_prob_up
    reach_probability = reach_prob_up
    direction_note = f"{opposite_side} (market_direction={market_direction})"
    inverted = (market_direction == "DOWN")
else:
    math_prob_opposite = reach_prob_down
    reach_probability = reach_prob_down
    direction_note = f"{opposite_side} (market_direction={market_direction})"
    inverted = (market_direction == "UP")

logger.info(f"REACH CALC: current_price={current_price_btc:.2f}, target={market_target:.2f}, reach_prob_raw={reach_prob_raw:.4f}, price_move_pct={price_move_pct:.4f}, z_score={z_score:.4f}, reach_prob_up={reach_prob_up:.4f}, reach_prob_down={reach_prob_down:.4f}, math_prob_opposite={math_prob_opposite:.4f}")


        if opposite_side == "UP":
            market_price_opposite = current_price_up
        else:
            market_price_opposite = current_price_down


        market_prob_opposite = market_price_opposite


        edge = math_prob_opposite - market_prob_opposite


        kf = max(0.0, min(1.0, edge))


        relative_deviation = (
            abs(current_price_btc - market_target) / market_target * 100
            if market_target != 0
            else 0
        )


        reason = (
            f"Opposite side: {direction_note} | "
            f"math_prob={math_prob_opposite*100:.1f}% vs market={market_prob_opposite*100:.1f}% "
            f"-> edge={edge*100:.2f}% -> KF={kf:.4f}"
        )


        logger.debug(
            "[OPPOSITE ANALYSIS] %s | reach_prob_target=%.2f%% | "
            "math_prob_opposite=%.2f%% | market_prob=%.2f%% | edge=%.2f%% | kf=%.4f",
            direction_note,
            reach_probability * 100,
            math_prob_opposite * 100,
            market_prob_opposite * 100,
            edge * 100,
            kf,
        )


        return ProbabilityCoefficient(
            kf=kf,
            math_probability=math_prob_opposite,
            market_probability=market_prob_opposite,
            edge=edge,
            expected_move_pct=expected_move,
            relative_deviation_pct=relative_deviation,
            reason=reason,
            current_price=current_price_btc,
            target_price=market_target,
            volatility_pct=vol_for_kf,
            time_remaining_minutes=time_remaining_minutes,
            time_in_hours=time_in_hours,
            price_move_pct=price_move_pct,
            std_dev_pct=std_dev_pct,
            z_score=z_score,
            reach_probability=reach_probability,
            inverted=inverted,
        )


    def analyze_same_side_add(
        self,
        current_price_btc: float,
        market_target: float,
        market_direction: str,
        volatility_pct: float,
        time_remaining_minutes: float,
        current_price_up: float,
        current_price_down: float,
        position_side: str,
        atr: float | None = None,
        vol_period_minutes: float = 60.0,
    ) -> ProbabilityCoefficient:
        """
        Анализирует, стоит ли добавлять свою позицию.


        KF высокий для своей стороны = цена повышается в нашу сторону,
        но еще не дорого -> хорошо докупать.
        """
        vol_for_kf, atr_pct, vol_current = self.calculate_hybrid_volatility(
            volatility_pct, atr, current_price_btc
        )


        expected_move = self.calculate_expected_move(
            vol_for_kf, time_remaining_minutes, vol_period_minutes=vol_period_minutes
        )


        logger.debug(
            "[VOL HYBRID] ATR=%.3f%% vol_current=%.3f%% → vol_for_kf=%.3f%% "
            "(ATR_weight=%.1f%% current_weight=%.1f%% floor=%.2f%%)",
            atr_pct * 100,
            vol_current * 100,
            vol_for_kf * 100,
            VOLATILITY_FOR_KF_WEIGHT_ATR * 100,
            VOLATILITY_FOR_KF_WEIGHT_CURRENT * 100,
            VOLATILITY_FLOOR * 100,
        )


        reach_prob, price_move_pct, std_dev_pct, z_score, time_in_hours = (
            self.calculate_reach_details(
                current_price_btc,
                market_target,
                vol_for_kf,
                time_remaining_minutes,
                vol_period_minutes=vol_period_minutes,
            )
        )
        inverted = False
        if market_direction == "UP" and position_side == "UP":
            math_prob_same = reach_prob
            market_price_same = current_price_up
        elif market_direction == "DOWN" and position_side == "DOWN":
            math_prob_same = reach_prob
            market_price_same = current_price_down
        else:
            math_prob_same = 1.0 - self.calculate_reach_probability(
                current_price_btc,
                market_target,
                vol_for_kf,
                time_remaining_minutes,
                vol_period_minutes=vol_period_minutes,
            )
            inverted = True
            market_price_same = current_price_up if position_side == "UP" else current_price_down


        market_prob_same = market_price_same
        edge = math_prob_same - market_prob_same
        kf = max(0.0, min(1.0, edge))


        relative_deviation = (
            abs(current_price_btc - market_target) / market_target * 100
            if market_target != 0
            else 0
        )


        reason = (
            f"Same side: math_prob={math_prob_same*100:.1f}% vs "
            f"market={market_prob_same*100:.1f}% -> edge={edge*100:.2f}% -> KF={kf:.4f}"
        )


        return ProbabilityCoefficient(
            kf=kf,
            math_probability=math_prob_same,
            market_probability=market_prob_same,
            edge=edge,
            expected_move_pct=expected_move,
            relative_deviation_pct=relative_deviation,
            reason=reason,
            current_price=current_price_btc,
            target_price=market_target,
            volatility_pct=vol_for_kf,
            time_remaining_minutes=time_remaining_minutes,
            time_in_hours=time_in_hours,
            price_move_pct=price_move_pct,
            std_dev_pct=std_dev_pct,
            z_score=z_score,
            reach_probability=reach_prob,
            inverted=inverted,
        )


    def analyze_exit_bad(
        self,
        current_price_btc: float,
        market_target: float,
        market_direction: str,
        volatility_pct: float,
        time_remaining_minutes: float,
        current_price_up: float,
        current_price_down: float,
        position_side: str,
        atr: float | None = None,
        vol_period_minutes: float = 60.0,
    ) -> ProbabilityCoefficient:
        """
        Анализирует, нужно ли выходить из позиции.


        ЛОГИКА:
        1. Определяем целевую цену для выигрыша
        2. Считаем p_hit = вероятность дойти до target за оставшееся время (Normal CDF)
        3. Считаем p_terminal = вероятность ОСТАТЬСЯ В ВЫИГРЫШЕ к концу
        4. EXIT если p_hit < HIT_THRESHOLD ИЛИ p_terminal < TERMINAL_THRESHOLD


        vol_period_minutes: за какой период считается волатильность
          - 15.0 если используем 15m волатильность
          - 60.0 если используем 1h волатильность
        """
        vol_for_kf, atr_pct, vol_current = self.calculate_hybrid_volatility(
            volatility_pct, atr, current_price_btc
        )


        now = time.time()
        should_log = now - self._last_exit_log_ts >= 5
        if should_log:
            self._last_exit_log_ts = now
            logger.info(
                "[VOL HYBRID - EXIT] ATR=%.3f%% vol_current=%.3f%% → vol_for_kf=%.3f%% "
                "(ATR_weight=%.1f%% current_weight=%.1f%% floor=%.2f%%) | vol_period=%d min",
                atr_pct * 100,
                vol_current * 100,
                vol_for_kf * 100,
                VOLATILITY_FOR_KF_WEIGHT_ATR * 100,
                VOLATILITY_FOR_KF_WEIGHT_CURRENT * 100,
                VOLATILITY_FLOOR * 100,
                int(vol_period_minutes),
            )


        if position_side == "UP":
            win_target = market_target
            position_description = f"UP (need price > {win_target:.2f})"
        else:
            win_target = market_target
            position_description = f"DOWN (need price < {win_target:.2f})"


        # ========== СЧИТАЕМ p_hit (Normal CDF без инверсии) ==========
        # p_hit = вероятность дойти до target за оставшееся время
        # 
        # UP:   z = (target - current) / std > 0
        #       P(S_T > target) = 1 - Φ(z)
        #
        # DOWN: z = (target - current) / std < 0
        #       P(S_T < target) = Φ(z)
        #
        # Единообразие: Φ(-z) = 1 - Φ(z)

        if time_remaining_minutes <= 0 or vol_for_kf <= 0:
            p_hit = 0.5
            price_move_pct_hit = 0.0
            std_dev_hit = 0.0
            z_hit = 0.0
        else:
            # Какой move нужен до целевой цены
            price_move_pct_hit = (
                (win_target - current_price_btc) / current_price_btc
            )

            # std_dev за оставшееся время
            std_dev_hit = vol_for_kf * math.sqrt(
                time_remaining_minutes / vol_period_minutes
            )

            if std_dev_hit == 0:
                p_hit = 0.5
                z_hit = 0.0
            else:
                z_hit = price_move_pct_hit / std_dev_hit

                # === ПРОСТАЯ ЛОГИКА: Normal CDF ===
                if position_side == "UP":
                    # Нам нужна цена ВЫШЕ target
                    # P(S_T > target) = 1 - Φ(z)
                    p_hit = 1.0 - self.calculate_normal_cdf(z_hit)
                else:  # DOWN
                    # Нам нужна цена НИЖЕ target
                    # P(S_T < target) = Φ(z)
                    p_hit = self.calculate_normal_cdf(z_hit)

                p_hit = max(0.0, min(1.0, p_hit))


        if position_side == "UP":
            if current_price_btc < win_target:
                # Нам нужно вырасти до win_target
                move_description = f"UP: {current_price_btc:.2f} → {win_target:.2f}"
            else:
                # Уже выше, можем коснуться ниже, но это не основная метрика
                move_description = f"UP: {current_price_btc:.2f} (уже выше {win_target:.2f})"
        else:  # DOWN
            if current_price_btc > win_target:
                # Нам нужно упасть до win_target
                move_description = f"DOWN: {current_price_btc:.2f} → {win_target:.2f}"
            else:
                # Уже ниже, можем коснуться выше, но это не основная метрика
                move_description = f"DOWN: {current_price_btc:.2f} (уже ниже {win_target:.2f})"


        # ========== СЧИТАЕМ p_terminal ==========
        # p_terminal = вероятность ОСТАТЬСЯ В ВЫИГРЫШЕ в момент экспирации
        if time_remaining_minutes <= 0 or vol_for_kf <= 0:
            p_terminal = 0.5
            time_in_hours = 0.0
            std_dev_terminal = 0.0
            z_terminal = 0.0
        else:
            # Какой нужен move к моменту конца?
            price_move_for_terminal = (
                (win_target - current_price_btc) / current_price_btc
            )
            time_in_hours = time_remaining_minutes / 60.0


            # std_dev за оставшееся время
            # КЛЮЧЕВОЙ МОМЕНТ: масштабируем волу правильно через vol_period_minutes!
            std_dev_terminal = vol_for_kf * math.sqrt(
                time_remaining_minutes / vol_period_minutes
            )


            if std_dev_terminal == 0:
                p_terminal = 0.5
                z_terminal = 0.0
            else:
                # z-score = сколько std_devs нужно нам
                z_terminal = price_move_for_terminal / std_dev_terminal


                # P(S_T > win_target) для UP, P(S_T < win_target) для DOWN
                if position_side == "UP":
                    # Нам нужна цена выше таргета в конце
                    # P(S_T > target) = 1 - Φ(z)
                    p_terminal = 1.0 - self.calculate_normal_cdf(z_terminal)
                else:  # DOWN
                    # Нам нужна цена ниже таргета в конце
                    # P(S_T < target) = Φ(z)
                    p_terminal = self.calculate_normal_cdf(z_terminal)


                p_terminal = max(0.0, min(1.0, p_terminal))


            if should_log:
                logger.info(
                    "[TERMINAL DEBUG] position=%s\n"
                    "  current_price=%.2f target=%.2f\n"
                    "  price_move_for_terminal=%.4f%%\n"
                    "  vol_for_kf=%.3f%% time=%.1f min vol_period=%d min\n"
                    "  std_dev_terminal=%.4f%%\n"
                    "  z_terminal=%.4f\n"
                    "  p_terminal=%.4f (%.1f%%)",
                    position_side,
                    current_price_btc,
                    win_target,
                    price_move_for_terminal,
                    vol_for_kf,
                    time_remaining_minutes,
                    int(vol_period_minutes),
                    std_dev_terminal,
                    z_terminal,
                    p_terminal,
                    p_terminal * 100,
                )


        market_price = current_price_up if position_side == "UP" else current_price_down


        if should_log:
            logger.info(
                "[EXIT CHECK] %s | p_hit=%.2f%% (Normal CDF) vs p_terminal=%.2f%% (terminal) | "
                "z_hit=%.4f z_terminal=%.4f | "
                "hit_threshold=%.2f%% terminal_threshold=%.2f%% | time=%.1f min | "
                "vol_for_kf=%.2f%% (atr=%.2f%% current=%.2f%% vol_period=%d min) | %s",
                position_description,
                p_hit * 100,
                p_terminal * 100,
                z_hit,
                z_terminal,
                app_config_module.EXIT_HIT_THRESHOLD * 100,
                app_config_module.EXIT_TERMINAL_THRESHOLD * 100,
                time_remaining_minutes,
                vol_for_kf,
                atr_pct,
                vol_current,
                int(vol_period_minutes),
                move_description,
            )


        hit_ok = p_hit >= app_config_module.EXIT_HIT_THRESHOLD
        terminal_ok = p_terminal >= app_config_module.EXIT_TERMINAL_THRESHOLD
        should_exit = not (hit_ok and terminal_ok)
        if should_exit:
            if not hit_ok:
                exit_reason = (
                    f"p_hit={p_hit*100:.1f}% < {app_config_module.EXIT_HIT_THRESHOLD*100:.1f}% "
                    f"(не дотронемся до цены)"
                )
            else:
                exit_reason = (
                    f"p_terminal={p_terminal*100:.1f}% < "
                    f"{app_config_module.EXIT_TERMINAL_THRESHOLD*100:.1f}% "
                    f"(не будем в выигрыше в конце)"
                )
        else:
            exit_reason = "Both thresholds OK → HOLD"
        reason = (
            f"p_hit={p_hit*100:.1f}% vs {app_config_module.EXIT_HIT_THRESHOLD*100:.1f}% | "
            f"p_terminal={p_terminal*100:.1f}% vs {app_config_module.EXIT_TERMINAL_THRESHOLD*100:.1f}% | "
            f"vol_for_kf={vol_for_kf:.2f}% (atr={atr_pct:.2f}% current={vol_current:.2f}% period={int(vol_period_minutes)}min) | "
            f"{exit_reason}"
        )


        reach_prob, price_move_pct, std_dev_pct, z_score, time_in_hours = (
            self.calculate_reach_details(
                current_price_btc,
                win_target,
                vol_for_kf,
                time_remaining_minutes,
                vol_period_minutes=vol_period_minutes,
            )
        )


        return ProbabilityCoefficient(
            kf=p_hit,
            math_probability=p_terminal,
            market_probability=market_price,
            edge=p_terminal - p_hit,
            expected_move_pct=self.calculate_expected_move(
                vol_for_kf, time_remaining_minutes, vol_period_minutes=vol_period_minutes
            ),
            relative_deviation_pct=(
                abs(current_price_btc - win_target) / win_target * 100
                if win_target != 0
                else 0
            ),
            reason=reason,
            current_price=current_price_btc,
            target_price=win_target,
            volatility_pct=vol_for_kf,
            time_remaining_minutes=time_remaining_minutes,
            time_in_hours=time_in_hours,
            price_move_pct=price_move_pct,
            std_dev_pct=std_dev_pct,
            z_score=z_score,
            reach_probability=reach_prob,
            inverted=False,
        )