"""
Position Manager Balanced Trading - двусторонний вход с value-weighted перебалансировкой.

ОТЛИЧИЯ ОТ ДРУГИХ СТРАТЕГИЙ:
=====================================

СТАНДАРТНАЯ СТРАТЕГИЯ (position_manager.py):
- Односторонний вход + хеджирование потом
- Агрессивное хеджирование с противоположными позициями
- Риск: просадка если не удаётся зайти в противоположную сторону

SOFT TRADING (position_manager_soft_trading.py):
- Edge-based вход в одну сторону
- Постепенное усреднение обеих сторон
- Цель: avg_UP + avg_DOWN < 1

BALANCED TRADING (этот файл):
- Вход СРАЗУ в обе стороны (UP и DOWN)
- Распределение капитала по формуле value-weighted allocation
- Постепенная перебалансировка по мере обновления вероятностей
- Цель: минимизация worst-case + возможность арбитража

КАК ИСПОЛЬЗОВАТЬ:
- В config.py: TRADING_STRATEGY = "balanced"
- Или в .env: TRADING_STRATEGY=balanced
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict, Tuple, Any

from app.config import (
    SIM_MODE,
    BALANCED_ENTRY_MAX_BUDGET_PCT,
    BALANCED_ENTRY_STEP_PCT,
    BALANCED_ENTRY_LAMBDA,
    BALANCED_ENTRY_MIN_TRADE_USD,
    BALANCED_ENTRY_CHECK_INTERVAL,
    BALANCED_ENTRY_COOLDOWN_AFTER_BUY,
    BALANCED_ENTRY_MAX_STEPS,
    BALANCED_ENTRY_TARGET_SUM,
    BALANCED_STRATEGY_MIN_EDGE,
    BALANCED_STRATEGY_MIN_PRICE_IMPROVEMENT_PCT,
    BALANCED_ARBITRAGE_TARGET_PROFIT_PCT,
)
from polymarket.client import PolymarketClient
from monitoring.price_monitor import PriceMonitor
from trading.order_manager import OrderManager
from trading.position import Position, position_storage
from analysis.price_to_beat_service import PriceToBeatService

logger = logging.getLogger(__name__)


class PositionManagerBalancedTrading:
    """
    Стратегия двустороннего входа с value-weighted перебалансировкой.

    Алгоритм:
    1. При старте рынка входим СРАЗУ в обе стороны (UP и DOWN)
    2. Доли определяются формулой alpha_star (value-weighted + hedge blend)
    3. Каждые N секунд пересчитываем alpha_star и докупаем по дельтам
    4. Long-only: если дельта < 0, не уменьшаем позицию
    5. Параллельно мониторим арбитражную возможность (avg_UP + avg_DOWN < 1)
    """

    def __init__(
        self,
        market_id: str,
        polymarket_client: PolymarketClient,
        order_manager: OrderManager,
        price_monitor: PriceMonitor,
    ):
        self.market_id = market_id
        self.pm_client = polymarket_client
        self.order_manager = order_manager
        self.price_monitor = price_monitor

        # Позиции
        self.positions: List[Position] = []
        self.positions_up: List[Position] = []
        self.positions_down: List[Position] = []
        self.is_active = False

        # Состояние
        self.current_probabilities = None
        self.last_buy_time: Optional[datetime] = None
        self.entry_step_count = 0  # Сколько шагов входа выполнено

        # Текущие alpha_star (для логирования)
        self.current_alpha_star_up = 0.5
        self.current_alpha_star_down = 0.5

        # Сервисы
        self.price_to_beat_service = PriceToBeatService(price_monitor, polymarket_client)
        self.symbol = "BTCUSDT"  # Обновится при первом _get_symbol_from_cache()

        logger.info(f"PositionManagerBalancedTrading инициализирован для рынка {market_id}")

    # ──────────────────────────────────────────────
    #  Основной цикл
    # ──────────────────────────────────────────────

    async def start_management(self, initial_position: Optional[Position] = None) -> None:
        """Запустить управление рынком (balanced trading)."""
        if initial_position:
            self.positions = [initial_position]
            if initial_position.side == "UP":
                self.positions_up = [initial_position]
            else:
                self.positions_down = [initial_position]
        else:
            self.positions = []
            self.positions_up = []
            self.positions_down = []

        self.is_active = True
        self._log_counter = 0

        logger.info(f"🚀 [{self.market_id}] Начато управление BALANCED TRADING")

        try:
            # Шаг 0: дождаться данных (вероятности, цены)
            await self._wait_for_data()

            # Шаг 1: универсальный цикл принятия решений (вход + ребалансировка)
            status_log_counter = 0

            while self.is_active and self._market_active():
                await self._rebalance_step()

                # Статус каждые 30 секунд
                status_log_counter += 1
                if status_log_counter >= int(30 / BALANCED_ENTRY_CHECK_INTERVAL):
                    await self._log_status()
                    status_log_counter = 0

                await asyncio.sleep(BALANCED_ENTRY_CHECK_INTERVAL)

        except Exception as exc:
            logger.error(f"[{self.market_id}] Ошибка в balanced trading: {exc}", exc_info=True)
        finally:
            self.is_active = False
            logger.info(f"🛑 [{self.market_id}] Управление BALANCED TRADING остановлено")

    def stop_management(self) -> None:
        """Остановить управление."""
        self.is_active = False
        logger.info(f"[{self.market_id}] Остановка balanced trading")

    # ──────────────────────────────────────────────
    #  Alpha-star: ядро математики
    # ──────────────────────────────────────────────

    def calculate_pure_alpha(
        self, p_up: float, p_down: float, prob_up: float, prob_down: float
    ) -> float:
        """
        Рассчитать чистое value-weighted распределение (pure alpha).

        Value = probability / price (отношение ценности к цене)
        Pure alpha = normalized value weights (нормализованные веса)

        Args:
            p_up: цена UP токена
            p_down: цена DOWN токена
            prob_up: наша вероятность UP
            prob_down: наша вероятность DOWN

        Returns:
            alpha_pure_up: доля капитала для UP (0.0-1.0)
        """
        # Защита от деления на ноль
        if p_up <= 0 or p_down <= 0:
            return 0.5

        # Calculate value ratios (ценность на единицу цены)
        v_u = prob_up / p_up
        v_d = prob_down / p_down

        # Normalize to get pure alpha (чистое распределение)
        alpha_pure_up = v_u / (v_u + v_d)

        # Clamp to reasonable bounds
        alpha_pure_up = max(0.1, min(0.9, alpha_pure_up))

        return alpha_pure_up

    def calculate_target_alpha(
        self, p_up: float, p_down: float, prob_up: float, prob_down: float, lambda_val: float
    ) -> Tuple[float, float, float]:
        """
        Рассчитать итоговое распределение капитала (alpha_star).

        Смешивает нейтральный хедж и нашу модель через коэффициент lambda.

        Args:
            p_up: цена UP токена
            p_down: цена DOWN токена
            prob_up: наша вероятность UP
            prob_down: наша вероятность DOWN
            lambda_val: коэффициент доверия к модели (0.0-1.0)
                       0.0 = чистая модель, 1.0 = чистый хедж

        Returns:
            (alpha_star, alpha_neutral, alpha_pure)
            alpha_star: итоговое распределение для UP
            alpha_neutral: нейтральный хедж (рыночная безопасность)
            alpha_pure: чистая модель (наш прогноз)
        """
        # Защита от деления на ноль
        if p_up <= 0 or p_down <= 0:
            return 0.5, 0.5, 0.5

        # 1. Alpha Neutral: рыночная безопасность (хедж)
        alpha_neutral = p_up / (p_up + p_down)

        # 2. Alpha Pure: наша модель (ценность)
        v_u = prob_up / p_up
        v_d = prob_down / p_down
        alpha_pure = v_u / (v_u + v_d)

        # Clamp alpha_pure to reasonable bounds
        alpha_pure = max(0.1, min(0.9, alpha_pure))

        # 3. Alpha Star: смешивание через lambda
        alpha_star = (lambda_val * alpha_neutral) + ((1 - lambda_val) * alpha_pure)

        # Clamp alpha_star to reasonable bounds
        alpha_star = max(0.1, min(0.9, alpha_star))

        return alpha_star, alpha_neutral, alpha_pure

    def calculate_arbitrage_close_sum(
        self, pos_up_shares: float, pos_down_shares: float, total_spent: float,
        p_up: float, p_down: float, target_profit: float = None
    ) -> Dict[str, Any]:
        """
        Рассчитать арбитражное закрытие позиции (предохранитель).

        Находит сколько нужно докупить слабой стороны, чтобы payouts > costs при любом исходе.

        Args:
            pos_up_shares: количество акций UP
            pos_down_shares: количество акций DOWN
            total_spent: общие затраты ($)
            p_up: текущая цена UP
            p_down: текущая цена DOWN
            target_profit: целевая прибыль (%) или None (использует config)

        Returns:
            {
                "side": "UP"|"DOWN"|None,
                "amount_usd": сумма для покупки ($),
                "shares_to_buy": количество акций,
                "is_possible": True/False
            }
        """
        if target_profit is None:
            target_profit = BALANCED_ARBITRAGE_TARGET_PROFIT_PCT / 100.0

        # Защита от деления на ноль
        if p_up <= 0 or p_down <= 0 or total_spent <= 0:
            return {"side": None, "amount_usd": 0, "shares_to_buy": 0, "is_possible": False}

        # Функция для расчёта дельты
        def calc_delta(q_target: float, q_current: float, total_exp: float, price: float, profit: float) -> float:
            """Рассчитать сколько акций нужно докупить для достижения арбитража."""
            effective_price = price * (1 + profit)
            denom = 1 - effective_price

            if denom <= 0:  # Цена слишком высокая для арбитража
                logger.info(f"         ❌ Арбитраж невозможен: цена {price:.4f} × (1 + {profit:.1%}) = {effective_price:.4f} ≥ 1")
                return float('inf')

            return (total_exp * (1 + profit) - q_current) / denom

        # Пробуем закрыть арбитраж через DOWN (докупаем DOWN)
        delta_q_down = calc_delta(pos_up_shares, pos_down_shares, total_spent, p_down, target_profit)

        # Пробуем закрыть арбитраж через UP (докупаем UP)
        delta_q_up = calc_delta(pos_down_shares, pos_up_shares, total_spent, p_up, target_profit)

        # Определяем лучшую сторону для докупки
        best_side = None
        best_delta_q = float('inf')
        best_price = 0

        # Проверяем DOWN
        if delta_q_down > 0 and delta_q_down != float('inf'):
            best_side = "DOWN"
            best_delta_q = delta_q_down
            best_price = p_down

        # Проверяем UP (если лучше или равен DOWN)
        if delta_q_up > 0 and delta_q_up != float('inf'):
            if best_side is None or delta_q_up < best_delta_q:
                best_side = "UP"
                best_delta_q = delta_q_up
                best_price = p_up

        # Если нашли подходящую сторону
        if best_side and best_delta_q != float('inf'):
            amount_usd = best_delta_q * best_price
            return {
                "side": best_side,
                "amount_usd": amount_usd,
                "shares_to_buy": best_delta_q,
                "is_possible": True
            }

        return {"side": None, "amount_usd": 0, "shares_to_buy": 0, "is_possible": False}

    def _calculate_alpha_star(
        self, p_u: float, p_d: float, math_prob_up: float
    ) -> Tuple[float, float]:
        """
        Рассчитать оптимальное распределение капитала между UP и DOWN.

        Формулы:
        --------
        1) Value каждой стороны (аналогия с value-betting):
           v_u = math_prob_up / p_u   — сколько "ценности" на доллар в UP
           v_d = math_prob_down / p_d  — то же для DOWN

        2) Чистое value-weighted распределение:
           alpha_pure_up = v_u / (v_u + v_d)

        3) Нейтральный хедж (пропорционально ценам):
           alpha_neutral_up = p_u / (p_u + p_d)

        4) Смешанное с параметром доверия λ ∈ [0, 1]:
           alpha_star_up = λ * alpha_neutral_up + (1-λ) * alpha_pure_up
           При λ=1: чистый хедж, при λ=0: чистый value-bet

        Args:
            p_u: текущая ask-цена UP токена (0..1)
            p_d: текущая ask-цена DOWN токена (0..1)
            math_prob_up: наша оценка вероятности UP (0..1)

        Returns:
            (alpha_star_up, alpha_star_down) — доли капитала
        """
        math_prob_down = 1.0 - math_prob_up
        lam = BALANCED_ENTRY_LAMBDA

        # Защита от деления на ноль
        p_u = max(p_u, 0.01)
        p_d = max(p_d, 0.01)
        math_prob_up = max(min(math_prob_up, 0.99), 0.01)
        math_prob_down = max(min(math_prob_down, 0.99), 0.01)

        # Value каждой стороны
        v_u = math_prob_up / p_u
        v_d = math_prob_down / p_d

        # Чистое value-weighted распределение
        alpha_pure_up = v_u / (v_u + v_d)

        # Нейтральный хедж по ценам
        alpha_neutral_up = p_u / (p_u + p_d)

        # Смешанное распределение
        alpha_star_up = lam * alpha_neutral_up + (1.0 - lam) * alpha_pure_up
        alpha_star_down = 1.0 - alpha_star_up

        # Clamp: не допускаем крайних перекосов (мин 10% на сторону)
        alpha_star_up = max(0.10, min(0.90, alpha_star_up))
        alpha_star_down = 1.0 - alpha_star_up

        return alpha_star_up, alpha_star_down

    # ──────────────────────────────────────────────
    #  Начальный вход
    # ──────────────────────────────────────────────

    async def _execute_initial_entry(self) -> None:
        """
        Выполнить начальный двусторонний вход.

        Берёт B_step = balance * MAX_BUDGET_PCT/100 * STEP_PCT/100,
        рассчитывает alpha_star, распределяет между UP и DOWN.
        """
        try:
            # Получить баланс
            balance = self.order_manager.get_balance()
            if balance <= 0:
                logger.warning(f"[{self.market_id}] Баланс = 0, не можем войти")
                return

            # Бюджет на этот рынок
            max_budget = balance * (BALANCED_ENTRY_MAX_BUDGET_PCT / 100.0)
            b_step = max_budget * (BALANCED_ENTRY_STEP_PCT / 100.0)

            logger.info(f"⚖️ [{self.market_id}] НАЧАЛЬНЫЙ ДВУСТОРОННИЙ ВХОД")
            logger.info(f"   💰 Баланс: ${balance:.2f}")
            logger.info(f"   📊 Макс бюджет на рынок: ${max_budget:.2f} ({BALANCED_ENTRY_MAX_BUDGET_PCT}%)")
            logger.info(f"   📊 Бюджет на шаг: ${b_step:.2f} ({BALANCED_ENTRY_STEP_PCT}%)")

            # Получить текущие цены из orderbook
            p_u = await self._get_current_price("UP")
            p_d = await self._get_current_price("DOWN")

            if not p_u or not p_d:
                logger.warning(f"[{self.market_id}] Не удалось получить цены UP/DOWN, пропуск")
                return

            # Получить math_prob_up
            math_prob_up = self._get_math_prob_up()

            # Рассчитать alpha_star
            alpha_up, alpha_down = self._calculate_alpha_star(p_u, p_d, math_prob_up)
            self.current_alpha_star_up = alpha_up
            self.current_alpha_star_down = alpha_down

            # Целевые суммы
            amount_up = b_step * alpha_up
            amount_down = b_step * alpha_down

            logger.info(f"   🧮 math_prob_up: {math_prob_up:.3f}")
            logger.info(f"   🧮 alpha_star: UP={alpha_up:.3f}, DOWN={alpha_down:.3f}")
            logger.info(f"   💵 Суммы: UP=${amount_up:.2f}, DOWN=${amount_down:.2f}")
            logger.info(f"   💰 Цены: UP=${p_u:.4f}, DOWN=${p_d:.4f}")

            # Выполнить покупки (обе стороны)
            bought_up = False
            bought_down = False

            if amount_up >= BALANCED_ENTRY_MIN_TRADE_USD:
                await self._enter_position("UP", amount_up, p_u, "BALANCED_INITIAL")
                bought_up = True
            else:
                logger.info(f"   ⏭️ UP: ${amount_up:.2f} < мин ${BALANCED_ENTRY_MIN_TRADE_USD}, пропуск")

            if amount_down >= BALANCED_ENTRY_MIN_TRADE_USD:
                await self._enter_position("DOWN", amount_down, p_d, "BALANCED_INITIAL")
                bought_down = True
            else:
                logger.info(f"   ⏭️ DOWN: ${amount_down:.2f} < мин ${BALANCED_ENTRY_MIN_TRADE_USD}, пропуск")

            if bought_up or bought_down:
                self.initial_entry_done = True
                self.entry_step_count = 1
                self.last_buy_time = datetime.now(timezone.utc)
                logger.info(f"✅ [{self.market_id}] Начальный вход выполнен (шаг 1/{BALANCED_ENTRY_MAX_STEPS})")
            else:
                logger.warning(f"[{self.market_id}] Не удалось выполнить начальный вход")

        except Exception as exc:
            logger.error(f"[{self.market_id}] Ошибка при начальном входе: {exc}", exc_info=True)

    # ──────────────────────────────────────────────
    #  Перебалансировка
    # ──────────────────────────────────────────────

    async def _rebalance_step(self) -> None:
        """
        Иерархическая машина принятия решений.

        СЛОЙ 0: Сбор данных
        СЛОЙ 1: Арбитраж (Priority #1) - если возможно, игнорируем всё остальное
        СЛОЙ 2: Edge фильтр - преимущество над рынком
        СЛОЙ 3: Price фильтр - выгодная цена
        СЛОЙ 4: Execution - динамический размер по уверенности
        """
        try:
            # === СЛОЙ 0: СБОР ДАННЫХ ===
            # Обновляем данные каждую секунду
            await self._update_probabilities()

            p_u = await self._get_current_price("UP")
            p_d = await self._get_current_price("DOWN")

            if not p_u or not p_d:
                return  # Тихо пропускаем если нет данных

            # Текущие позиции и затраты
            pos_up_shares = sum(p.total_volume for p in self.positions_up)
            pos_down_shares = sum(p.total_volume for p in self.positions_down)
            total_spent = sum(p.total_cost_usd for p in self.positions) if self.positions else 0

            # Средние цены входа
            avg_entry_up = 0
            avg_entry_down = 0
            if self.positions_up:
                total_vol_up = sum(p.total_volume for p in self.positions_up)
                avg_entry_up = sum(p.entry_price_avg * p.total_volume for p in self.positions_up) / total_vol_up
            if self.positions_down:
                total_vol_down = sum(p.total_volume for p in self.positions_down)
                avg_entry_down = sum(p.entry_price_avg * p.total_volume for p in self.positions_down) / total_vol_down

            # === СЛОЙ 1: АРБИТРАЖ (Priority #1) ===
            logger.info(f"🎯 [{self.market_id}] АРБИТРАЖ (Priority #1)")
            logger.info(f"   📊 Данные: UP={pos_up_shares:.2f}шт(${total_spent/2:.2f}), DOWN={pos_down_shares:.2f}шт(${total_spent/2:.2f}), Итого=${total_spent:.2f}")
            logger.info(f"   💰 Цены: UP=${p_u:.4f}, DOWN=${p_d:.4f}")

            arb_result = self.calculate_arbitrage_close_sum(
                pos_up_shares, pos_down_shares, total_spent, p_u, p_d
            )

            if arb_result["is_possible"] and arb_result["amount_usd"] >= BALANCED_ENTRY_MIN_TRADE_USD:
                logger.info(f"   ✅ Арбитраж: {arb_result['side']} ${arb_result['amount_usd']:.2f} ({arb_result['shares_to_buy']:.1f}шт) - ВОЗМОЖЕН!")
                logger.info(f"   💵 Гарантированная прибыль: ${arb_result['amount_usd'] * (BALANCED_ARBITRAGE_TARGET_PROFIT_PCT / 100.0):.2f}")

                await self._enter_position(
                    arb_result["side"],
                    arb_result["amount_usd"],
                    p_u if arb_result["side"] == "UP" else p_d,
                    "ARBITRAGE_CLOSE"
                )

                # Пауза после арбитража
                await asyncio.sleep(5)
                return  # АРБИТРАЖ ИМЕЕТ ВЫСШИЙ ПРИОРИТЕТ
            else:
                logger.info(f"   ❌ Арбитраж: {arb_result['side']} ${arb_result['amount_usd']:.2f} - НЕВОЗМОЖЕН")

            # === СЛОЙ 2: РАСЧЁТ ЦЕЛЕВЫХ ВЕСОВ ===
            math_prob_up = self._get_math_prob_up()
            math_prob_down = 1.0 - math_prob_up

            alpha_star, alpha_neutral, alpha_pure = self.calculate_target_alpha(
                p_u, p_d, math_prob_up, math_prob_down, BALANCED_ENTRY_LAMBDA
            )

            # === СЛОЙ 3: ФИЛЬТР EDGE ===
            logger.info(f"📊 [{self.market_id}] EDGE ФИЛЬТР")
            alpha_neutral_up = p_u / (p_u + p_d)
            alpha_neutral_down = 1.0 - alpha_neutral_up
            edge_up = abs(alpha_star - alpha_neutral_up)
            edge_down = abs((1-alpha_star) - alpha_neutral_down)
            edge = max(edge_up, edge_down)  # Используем максимальный edge

            logger.info(f"   🧮 Alpha*: UP={alpha_star:.3f}, DOWN={1-alpha_star:.3f}")
            logger.info(f"   🛡️ Neutral: UP={alpha_neutral_up:.3f}, DOWN={alpha_neutral_down:.3f}")
            logger.info(f"   📈 Edge: UP={edge_up:.3f}, DOWN={edge_down:.3f}, Max={edge:.3f} < {BALANCED_STRATEGY_MIN_EDGE}")

            if edge < BALANCED_STRATEGY_MIN_EDGE:
                logger.info(f"   ❌ Edge: {edge:.3f} < {BALANCED_STRATEGY_MIN_EDGE} - ЖДЁМ СИГНАЛА")
                return
            else:
                logger.info(f"   ✅ Edge: {edge:.3f} >= {BALANCED_STRATEGY_MIN_EDGE} - ПРОХОДИМ")

            # === СЛОЙ 4: ФИЛЬТР ЦЕНЫ ===
            logger.info(f"💰 [{self.market_id}] PRICE ФИЛЬТР")

            price_ok = self._is_price_good_for_entry(p_u, p_d, avg_entry_up, avg_entry_down, edge)

            if self.positions_up and avg_entry_up > 0:
                price_improvement_up = ((avg_entry_up - p_u) / avg_entry_up) * 100
                logger.info(f"   📈 UP: avg=${avg_entry_up:.4f}, current=${p_u:.4f} → {price_improvement_up:+.2f}% ≥ {BALANCED_STRATEGY_MIN_PRICE_IMPROVEMENT_PCT}%")

            if self.positions_down and avg_entry_down > 0:
                price_improvement_down = ((avg_entry_down - p_d) / avg_entry_down) * 100
                logger.info(f"   📉 DOWN: avg=${avg_entry_down:.4f}, current=${p_d:.4f} → {price_improvement_down:+.2f}% ≥ {BALANCED_STRATEGY_MIN_PRICE_IMPROVEMENT_PCT}%")

            if not price_ok:
                logger.info(f"   ❌ Price: НЕУДОБНАЯ ЦЕНА - ЖДЁМ ОТКАТА")
                return
            else:
                logger.info(f"   ✅ Price: ЦЕНА ПОДХОДИТ")

            # === СЛОЙ 5: ИСПОЛНЕНИЕ С ДИНАМИЧЕСКИМ РАЗМЕРОМ ===

            # Проверки лимитов
            if self.entry_step_count >= BALANCED_ENTRY_MAX_STEPS:
                return

            if self.last_buy_time:
                elapsed = (datetime.now(timezone.utc) - self.last_buy_time).total_seconds()
                if elapsed < BALANCED_ENTRY_COOLDOWN_AFTER_BUY:
                    return

            # Расчёт дельт и динамического размера
            confidence = self._get_confidence_factor(edge)
            delta_up, delta_down = self._calculate_rebalance_deltas(
                alpha_star, p_u, p_d, confidence
            )

            # Детальные логи при входе
            logger.info(f"⚡ [{self.market_id}] EXECUTION")
            logger.info(f"   🎯 Alpha Star: UP={alpha_star:.3f}, DOWN={1-alpha_star:.3f}")
            logger.info(f"   📊 Edge: {edge:.3f}, Confidence: {confidence:.2f}")
            logger.info(f"   💰 Цены: UP=${p_u:.4f}, DOWN=${p_d:.4f}")

            # Показываем расчёт капитала
            capital_up = sum(p.total_cost_usd for p in self.positions_up)
            capital_down = sum(p.total_cost_usd for p in self.positions_down)
            b_current = capital_up + capital_down
            balance = self.order_manager.get_balance()
            max_budget = balance * (BALANCED_ENTRY_MAX_BUDGET_PCT / 100.0)
            b_step = max_budget * (BALANCED_ENTRY_STEP_PCT / 100.0)
            b_target = b_current + b_step

            logger.info(f"   💵 Капитал: UP=${capital_up:.2f}, DOWN=${capital_down:.2f}, Итого=${b_current:.2f}")
            logger.info(f"   🎯 Target: UP=${b_target * alpha_star:.2f}, DOWN=${b_target * (1-alpha_star):.2f}, Итого=${b_target:.2f}")
            logger.info(f"   🔥 Confidence: {confidence:.2f} → Final: UP=${delta_up:.2f}, DOWN=${delta_down:.2f}")
            logger.info(f"   💵 Min trade: ${BALANCED_ENTRY_MIN_TRADE_USD}")

            executed = False

            if delta_up >= BALANCED_ENTRY_MIN_TRADE_USD:
                logger.info(f"   📈 ВХОД UP: ${delta_up:.2f}")
                await self._enter_position("UP", delta_up, p_u, "BALANCED_REBALANCE")
                executed = True

            if delta_down >= BALANCED_ENTRY_MIN_TRADE_USD:
                logger.info(f"   📉 ВХОД DOWN: ${delta_down:.2f}")
                await self._enter_position("DOWN", delta_down, p_d, "BALANCED_REBALANCE")
                executed = True

            if executed:
                self.entry_step_count += 1
                self.last_buy_time = datetime.now(timezone.utc)
                logger.info(f"   ✅ Шаг {self.entry_step_count}/{BALANCED_ENTRY_MAX_STEPS} выполнен")

                # Пауза после входа
                await asyncio.sleep(5)

        except Exception as exc:
            logger.error(f"[{self.market_id}] Ошибка в иерархическом цикле: {exc}", exc_info=True)

    def _calculate_edge(self, alpha_star: float, p_u: float, p_d: float) -> float:
        """Расчёт преимущества над рынком."""
        alpha_neutral = p_u / (p_u + p_d)  # Рыночная вероятность UP
        return abs(alpha_star - alpha_neutral)

    def _is_price_good_for_entry(self, p_u: float, p_d: float,
                               avg_entry_up: float, avg_entry_down: float, edge: float) -> bool:
        """Умный фильтр цены для входа."""
        # Если ещё не входили - любая цена ок
        if not self.positions_up and not self.positions_down:
            return True

        # Проверяем UP
        if self.positions_up and avg_entry_up > 0:
            price_improvement_up = ((avg_entry_up - p_u) / avg_entry_up) * 100
            if price_improvement_up < BALANCED_STRATEGY_MIN_PRICE_IMPROVEMENT_PCT:
                return False

        # Проверяем DOWN
        if self.positions_down and avg_entry_down > 0:
            price_improvement_down = ((avg_entry_down - p_d) / avg_entry_down) * 100
            if price_improvement_down < BALANCED_STRATEGY_MIN_PRICE_IMPROVEMENT_PCT:
                return False

        return True

    def _get_confidence_factor(self, edge: float) -> float:
        """Динамическая агрессия на основе edge."""
        # Edge = 0.04 (слабый) → Confidence = 0.2
        # Edge = 0.15 (сильный) → Confidence = 1.0
        min_edge = BALANCED_STRATEGY_MIN_EDGE
        max_edge = 0.20  # Максимальный edge для полной уверенности

        if edge <= min_edge:
            return 0.2
        elif edge >= max_edge:
            return 1.0
        else:
            # Линейная интерполяция
            return 0.2 + (edge - min_edge) / (max_edge - min_edge) * 0.8

    def _calculate_rebalance_deltas(self, alpha_star: float, p_u: float, p_d: float, confidence: float) -> Tuple[float, float]:
        """Расчёт дельт для приближения к целевым весам."""
        # Текущий капитал
        capital_up = sum(p.total_cost_usd for p in self.positions_up)
        capital_down = sum(p.total_cost_usd for p in self.positions_down)
        b_current = capital_up + capital_down

        # Бюджет на шаг
        balance = self.order_manager.get_balance()
        max_budget = balance * (BALANCED_ENTRY_MAX_BUDGET_PCT / 100.0)
        b_step = max_budget * (BALANCED_ENTRY_STEP_PCT / 100.0)

        # Целевой капитал
        b_target = b_current + b_step
        target_up = b_target * alpha_star
        target_down = b_target * (1.0 - alpha_star)

        # Дельты с учётом уверенности
        delta_up = max(0.0, (target_up - capital_up) * confidence)
        delta_down = max(0.0, (target_down - capital_down) * confidence)

        return delta_up, delta_down

    # ──────────────────────────────────────────────
    #  Арбитраж
    # ──────────────────────────────────────────────

    def _check_arbitrage_opportunity(self) -> None:
        """
        Проверить, достигнут ли арбитраж (avg_UP + avg_DOWN < 1).

        Если да — позиции гарантированно прибыльны независимо от исхода.
        """
        if not self.positions_up or not self.positions_down:
            return

        try:
            total_cost_up = sum(p.total_cost_usd for p in self.positions_up)
            total_vol_up = sum(p.total_volume for p in self.positions_up)
            avg_up = total_cost_up / total_vol_up if total_vol_up > 0 else 0

            total_cost_down = sum(p.total_cost_usd for p in self.positions_down)
            total_vol_down = sum(p.total_volume for p in self.positions_down)
            avg_down = total_cost_down / total_vol_down if total_vol_down > 0 else 0

            total_avg = avg_up + avg_down

            if total_avg < BALANCED_ENTRY_TARGET_SUM:
                # Гарантированный арбитраж!
                profit_per_token = 1.0 - total_avg
                min_tokens = min(total_vol_up, total_vol_down)
                guaranteed_profit = profit_per_token * min_tokens
                logger.info(
                    f"🏆 [{self.market_id}] АРБИТРАЖ ДОСТИГНУТ! "
                    f"avg_UP={avg_up:.4f} + avg_DOWN={avg_down:.4f} = {total_avg:.4f} < {BALANCED_ENTRY_TARGET_SUM} "
                    f"| Гарантированная прибыль: ~${guaranteed_profit:.2f}"
                )

        except Exception as exc:
            logger.error(f"[{self.market_id}] Ошибка при проверке арбитража: {exc}")

    # ──────────────────────────────────────────────
    #  Утилиты: вероятности и цены
    # ──────────────────────────────────────────────

    def _get_math_prob_up(self) -> float:
        """Получить текущую math_prob_up из рассчитанных вероятностей."""
        if self.current_probabilities:
            up = self.current_probabilities.get("up_probability", 0.5)
            down = self.current_probabilities.get("down_probability", 0.5)
            total = up + down
            if total > 0:
                return up / total
        return 0.5

    async def _wait_for_data(self) -> None:
        """Подождать, пока появятся данные (цены, вероятности)."""
        for attempt in range(10):
            await self._update_probabilities()
            p_u = await self._get_current_price("UP")
            p_d = await self._get_current_price("DOWN")

            if self.current_probabilities and p_u and p_d:
                logger.info(f"✅ [{self.market_id}] Данные получены (попытка {attempt + 1})")
                return

            logger.debug(f"[{self.market_id}] Ожидание данных... (попытка {attempt + 1}/10)")
            await asyncio.sleep(2)

        logger.warning(f"[{self.market_id}] Данные не получены за 10 попыток, продолжаем с дефолтами")

    async def _get_symbol_from_cache(self) -> str:
        """Получить символ из PriceToBeatService."""
        try:
            symbol = await self.price_to_beat_service.get_symbol(self.market_id)
            if symbol:
                return symbol
        except Exception as exc:
            logger.error(f"Ошибка при получении symbol для {self.market_id}: {exc}")
        return "BTCUSDT"

    async def _update_probabilities(self) -> None:
        """
        Обновить текущие вероятности для рынка.
        Аналогично PositionManagerSoftTrading._update_probabilities().
        """
        try:
            # Обновить символ из кэша
            if self.symbol == "BTCUSDT":
                self.symbol = await self._get_symbol_from_cache()
                if self.symbol != "BTCUSDT":
                    logger.info(f"🔄 [{self.market_id}] Символ обновлён: {self.symbol}")

            # price_to_beat
            price_to_beat = await self.price_to_beat_service.get_price_to_beat(self.market_id)
            if price_to_beat is None:
                logger.debug(f"[{self.market_id}] Не удалось получить price_to_beat")
                return

            # Текущая цена актива
            current_price = self.price_monitor.get_price(self.symbol)
            if not current_price:
                logger.debug(f"[{self.market_id}] Не удалось получить цену {self.symbol}")
                return

            # Волатильность
            volatility = self.price_monitor.get_volatility(self.symbol)
            if not volatility:
                logger.debug(f"[{self.market_id}] Не удалось получить волатильность")
                return

            # Продолжительность рынка
            market_duration = await self.price_to_beat_service.get_market_duration(self.market_id)
            if not market_duration:
                market_duration = "15m"

            if market_duration == "15m":
                vol_pct = volatility.get("15m") or volatility.get("5m") or volatility.get("1h") or 1.0
                vol_period_minutes = 15.0
            else:
                vol_pct = volatility.get("1h") or volatility.get("15m") or volatility.get("5m") or 1.0
                vol_period_minutes = 60.0

            vol_pct_decimal = vol_pct / 100.0

            # ATR
            stats = self.price_monitor.get_stats(self.symbol)
            atr = stats.get("atr") if stats else None

            # Probability analyzer (lazy init)
            if not hasattr(self, "probability_analyzer"):
                from analysis.probability import PostEntryProbabilityAnalyzer
                self.probability_analyzer = PostEntryProbabilityAnalyzer()

            # Гибридная волатильность
            vol_for_kf, _, _ = self.probability_analyzer.calculate_hybrid_volatility(
                vol_pct_decimal, atr, current_price
            )

            market_direction = "UP" if current_price < price_to_beat else "DOWN"

            # Orderbook цены
            orderbook_prices = self.order_manager.orderbook_analyzer.get_market_prices(self.market_id) or {}
            current_price_up = orderbook_prices.get("up_ask", 0.5)
            current_price_down = orderbook_prices.get("down_ask", 0.5)

            time_remaining_minutes = 60  # TODO: рассчитывать точно

            prob_up = self.probability_analyzer.analyze_opposite_side_buy(
                current_price_btc=current_price,
                market_target=price_to_beat,
                market_direction=market_direction,
                opposite_side="UP",
                volatility_pct=vol_pct_decimal,
                time_remaining_minutes=time_remaining_minutes,
                current_price_up=current_price_up,
                current_price_down=current_price_down,
                atr=atr,
                vol_period_minutes=vol_period_minutes,
            )

            prob_down = self.probability_analyzer.analyze_opposite_side_buy(
                current_price_btc=current_price,
                market_target=price_to_beat,
                market_direction=market_direction,
                opposite_side="DOWN",
                volatility_pct=vol_pct_decimal,
                time_remaining_minutes=time_remaining_minutes,
                current_price_up=current_price_up,
                current_price_down=current_price_down,
                atr=atr,
                vol_period_minutes=vol_period_minutes,
            )

            self.current_probabilities = {
                "up_probability": prob_up.reach_probability,
                "down_probability": prob_down.reach_probability,
                "timestamp": datetime.now(timezone.utc),
            }

            logger.debug(
                f"[{self.market_id}] Вероятности: UP={prob_up.reach_probability:.3f}, "
                f"DOWN={prob_down.reach_probability:.3f}"
            )

        except Exception as exc:
            logger.error(f"[{self.market_id}] Ошибка при обновлении вероятностей: {exc}")
            self.current_probabilities = None

    async def _get_current_price(self, side: str) -> Optional[float]:
        """Получить текущую ask цену для стороны (UP или DOWN)."""
        try:
            if hasattr(self.order_manager, "orderbook_analyzer"):
                prices = self.order_manager.orderbook_analyzer.get_market_prices(self.market_id)
                if prices:
                    key = "up_ask" if side == "UP" else "down_ask"
                    price = prices.get(key)
                    if price and price > 0:
                        return price

            # Fallback: orderbook напрямую
            orderbook = self.order_manager.orderbook_analyzer.get_orderbook(self.market_id)
            if orderbook and "orderbooks" in orderbook:
                outcome_key = "outcome_0" if side == "UP" else "outcome_1"
                if outcome_key in orderbook["orderbooks"]:
                    outcome_data = orderbook["orderbooks"][outcome_key]
                    if "asks" in outcome_data and outcome_data["asks"]:
                        asks = sorted(outcome_data["asks"], key=lambda x: float(x["price"]))
                        return float(asks[0]["price"])

            return None

        except Exception as exc:
            logger.error(f"Ошибка при получении цены для {side}: {exc}")
            return None

    # ──────────────────────────────────────────────
    #  Вход в позицию
    # ──────────────────────────────────────────────

    async def _enter_position(
        self, side: str, amount: float, price: float, entry_reason: str
    ) -> None:
        """Разместить ордер и создать позицию."""
        try:
            result = self.order_manager.buy_outcome(
                market_id=self.market_id,
                side=side,
                amount_usdc=amount,
                price=price,
            )

            if result and result.get("success"):
                # Получить title из кэша
                minfo = self.price_to_beat_service.get_market_info(self.market_id)
                mtitle = minfo.get("title", f"Market {self.market_id}") if minfo else f"Market {self.market_id}"

                position = Position(
                    position_id=f"pos_{self.market_id}_{int(datetime.now(timezone.utc).timestamp())}_{side.lower()}",
                    market_id=self.market_id,
                    market_title=mtitle,
                    symbol=self.symbol,
                    side=side,
                    entry_time=datetime.now(timezone.utc),
                    entry_price_avg=price,
                    total_volume=amount / price if price > 0 else 0,
                    total_cost_usd=amount,
                    entry_reason=entry_reason,
                    market_start_time=None,
                    minutes_until_start=0,
                )

                self.positions.append(position)
                position_storage.add_position(position)

                if side == "UP":
                    self.positions_up.append(position)
                else:
                    self.positions_down.append(position)

                logger.info(
                    f"✅ [{self.market_id}] {side} ${amount:.2f} @ ${price:.4f} ({entry_reason}) "
                    f"| UP:{len(self.positions_up)} DOWN:{len(self.positions_down)}"
                )
            else:
                logger.warning(f"❌ [{self.market_id}] Не удалось купить {side} ${amount:.2f}")

        except Exception as exc:
            logger.error(f"[{self.market_id}] Ошибка при входе в позицию {side}: {exc}")

    # ──────────────────────────────────────────────
    #  Проверка рынка
    # ──────────────────────────────────────────────

    def _market_active(self) -> bool:
        """Проверить, активен ли рынок."""
        try:
            market_data = self.pm_client.get_market_data(self.market_id)
            if not market_data:
                return False

            state = market_data.get("state", "").lower()
            if state in ("closed", "resolved", "cancelled"):
                logger.info(f"[{self.market_id}] Рынок закрыт (статус: {state})")
                return False

            end_date = market_data.get("endDate")
            if end_date:
                end_dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
                if end_dt < datetime.now(timezone.utc):
                    logger.info(f"[{self.market_id}] Рынок уже закончился")
                    return False

            return True

        except Exception as exc:
            logger.warning(f"[{self.market_id}] Ошибка проверки рынка: {exc}")
            return False

    # ──────────────────────────────────────────────
    #  Логирование
    # ──────────────────────────────────────────────

    async def merge_positions_by_side(self, side: str) -> bool:
        """
        Объединить все позиции по указанной стороне в одну с средневзвешенной ценой входа.

        Args:
            side: "UP" или "DOWN"

        Returns:
            True если объединение произошло, False если позиций <= 1
        """
        try:
            if side not in ["UP", "DOWN"]:
                logger.error(f"[{self.market_id}] Неверная сторона для объединения: {side}")
                return False

            # Получить список позиций по стороне
            positions_list = self.positions_up if side == "UP" else self.positions_down

            if len(positions_list) <= 1:
                logger.info(f"[{self.market_id}] Мало позиций для объединения {side}: {len(positions_list)}")
                return False

            logger.info(f"🔄 [{self.market_id}] ОБЪЕДИНЕНИЕ {len(positions_list)} ПОЗИЦИЙ {side}")

            # Рассчитать общие метрики
            total_cost = sum(p.total_cost_usd for p in positions_list)
            total_volume = sum(p.total_volume for p in positions_list)

            if total_volume <= 0:
                logger.error(f"[{self.market_id}] Нулевой объем позиций {side}, объединение невозможно")
                return False

            # Средневзвешенная цена входа
            weighted_avg_price = total_cost / total_volume

            # Определить earliest_entry_time (самая ранняя позиция)
            earliest_entry_time = min(p.entry_time for p in positions_list)

            # Создать объединенную позицию
            merged_position = Position(
                position_id=f"pos_{self.market_id}_{int(datetime.now(timezone.utc).timestamp())}_{side.lower()}_merged",
                market_id=self.market_id,
                market_title=positions_list[0].market_title,  # Берем из первой позиции
                symbol=positions_list[0].symbol,
                side=side,
                entry_time=earliest_entry_time,  # Самая ранняя дата входа
                entry_price_avg=weighted_avg_price,
                total_volume=total_volume,
                total_cost_usd=total_cost,
                entry_reason="MERGED_POSITIONS",  # Новый тип причины
                market_start_time=positions_list[0].market_start_time,
                minutes_until_start=positions_list[0].minutes_until_start,
                start_price=positions_list[0].start_price,  # Price to beat
            )

            # Детальный лог объединения
            logger.info(f"   📊 Статистика объединения:")
            logger.info(f"      Общий объем: {total_volume:.4f} tokens")
            logger.info(f"      Общая стоимость: ${total_cost:.2f}")
            logger.info(f"      Средневзвешенная цена: ${weighted_avg_price:.4f}")
            logger.info(f"      Самая ранняя позиция: {earliest_entry_time}")

            # Показать детали по каждой позиции
            for i, pos in enumerate(positions_list):
                logger.info(f"      {i+1}. ${pos.total_cost_usd:.2f} @ ${pos.entry_price_avg:.4f} ({pos.entry_reason})")

            # Удалить старые позиции из хранилища и списков
            for old_pos in positions_list[:]:  # Копия списка для безопасной итерации
                # Удалить из глобального хранилища
                position_storage.positions.pop(old_pos.position_id, None)

                # Удалить из локальных списков
                if old_pos in self.positions:
                    self.positions.remove(old_pos)
                if old_pos in positions_list:
                    positions_list.remove(old_pos)

                logger.debug(f"      ❌ Удалена позиция {old_pos.position_id}")

            # Добавить новую объединенную позицию
            self.positions.append(merged_position)
            positions_list.append(merged_position)
            position_storage.add_position(merged_position)

            logger.info(f"   ✅ Создана объединенная позиция {merged_position.position_id}")
            logger.info(f"   📂 Итого позиций после объединения: UP={len(self.positions_up)}, DOWN={len(self.positions_down)}")

            # Сохранить изменения
            position_storage._save_positions()

            return True

        except Exception as exc:
            logger.error(f"[{self.market_id}] Ошибка при объединении позиций {side}: {exc}", exc_info=True)
            return False

    async def _log_status(self) -> None:
        """Логировать статус каждые ~10 секунд."""
        try:
            capital_up = sum(p.total_cost_usd for p in self.positions_up)
            capital_down = sum(p.total_cost_usd for p in self.positions_down)
            capital_total = capital_up + capital_down

            logger.info(f"📊 [{self.market_id}] СТАТУС BALANCED TRADING (шаг {self.entry_step_count}/{BALANCED_ENTRY_MAX_STEPS})")
            logger.info(f"   ⚖️ Alpha*: UP={self.current_alpha_star_up:.3f}, DOWN={self.current_alpha_star_down:.3f}")
            logger.info(f"   💰 Капитал: UP=${capital_up:.2f}, DOWN=${capital_down:.2f}, ИТОГО=${capital_total:.2f}")
            logger.info(f"   📂 Позиции: UP={len(self.positions_up)}, DOWN={len(self.positions_down)}")

            # Средние цены и арбитражный прогресс
            if self.positions_up and self.positions_down:
                vol_up = sum(p.total_volume for p in self.positions_up)
                vol_down = sum(p.total_volume for p in self.positions_down)
                avg_up = capital_up / vol_up if vol_up > 0 else 0
                avg_down = capital_down / vol_down if vol_down > 0 else 0
                total_avg = avg_up + avg_down

                status = "✅ АРБИТРАЖ" if total_avg < BALANCED_ENTRY_TARGET_SUM else "⏳ В ПРОЦЕССЕ"
                logger.info(f"   💎 Avg: UP=${avg_up:.4f} + DOWN=${avg_down:.4f} = ${total_avg:.4f} {status}")

            # Текущие цены
            p_u = await self._get_current_price("UP")
            p_d = await self._get_current_price("DOWN")
            if p_u and p_d:
                logger.info(f"   📈 Рыночные цены: UP=${p_u:.4f}, DOWN=${p_d:.4f}")

            # Вероятности
            if self.current_probabilities:
                up_p = self.current_probabilities.get("up_probability", 0)
                down_p = self.current_probabilities.get("down_probability", 0)
                logger.info(f"   🧮 Вероятности: UP={up_p:.3f}, DOWN={down_p:.3f}")

        except Exception as exc:
            logger.error(f"[{self.market_id}] Ошибка при логировании: {exc}")


# ──────────────────────────────────────────────
#  Глобальный реестр
# ──────────────────────────────────────────────

_position_managers_balanced: Dict[str, PositionManagerBalancedTrading] = {}


def get_position_manager_balanced(market_id: str) -> Optional[PositionManagerBalancedTrading]:
    """Получить balanced trading менеджер для рынка."""
    return _position_managers_balanced.get(market_id)


def create_position_manager_balanced(
    market_id: str,
    polymarket_client: PolymarketClient,
    order_manager: OrderManager,
    price_monitor: PriceMonitor,
) -> PositionManagerBalancedTrading:
    """Создать balanced trading менеджер для рынка."""
    if market_id in _position_managers_balanced:
        return _position_managers_balanced[market_id]

    manager = PositionManagerBalancedTrading(market_id, polymarket_client, order_manager, price_monitor)
    _position_managers_balanced[market_id] = manager
    return manager


def stop_all_position_managers_balanced() -> None:
    """Остановить все balanced trading менеджеры."""
    for manager in _position_managers_balanced.values():
        manager.stop_management()
    _position_managers_balanced.clear()
    logger.info("Все менеджеры balanced trading остановлены")
