"""
Position Manager - управление позициями после первого входа.

Отслеживает открытые позиции в рынке и принимает решения о дополнительных входах
для создания хеджированных позиций с гарантированной прибылью.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from app.config import (
    MATH_PROB_FOR_OPPOSITE,
    PRICE_ENTRY_FOR_OPPOSITE,
    PERCENT_FOR_PRICE_REDUCE,
    SIM_MODE
)
from polymarket.client import PolymarketClient
from monitoring.price_monitor import PriceMonitor
from trading.order_manager import OrderManager
from trading.position import Position, position_storage
from trading.position_calculator import PositionCalculator
from analysis.price_to_beat_service import PriceToBeatService

logger = logging.getLogger(__name__)


class PositionManager:
    """
    Управляет позициями в конкретном рынке после первого входа.

    Основные функции:
    1. Отслеживание открытых позиций
    2. Проверка условий для входа в противоположную сторону
    3. Рассчитать оптимальных сумм для дополнительных входов
    4. Мониторинг рынка и принятие решений
    """

    def __init__(
        self,
        market_id: str,
        polymarket_client: PolymarketClient,
        order_manager: OrderManager,
        price_monitor: PriceMonitor
    ):
        """
        Args:
            market_id: ID рынка для управления
            polymarket_client: Клиент Polymarket
            order_manager: Менеджер ордеров
            price_monitor: Монитор цен
        """
        self.market_id = market_id
        self.pm_client = polymarket_client
        self.order_manager = order_manager
        self.price_monitor = price_monitor

        # Позиции в этом рынке
        self.positions: List[Position] = []
        self.is_active = False

        # Текущие рассчитанные вероятности
        self.current_probabilities = None

        # Единый сервис для получения price_to_beat
        self.price_to_beat_service = PriceToBeatService(price_monitor, polymarket_client)

        # Определяем символ для рынка (BTC/ETH/SOL) из кэша PriceToBeatService
        # Используем fallback значение, так как инициализация происходит синхронно
        self.symbol = "BTCUSDT"  # Будет обновлен при первом вызове _get_symbol_from_cache()

        # Кешируем неизменяемые данные (определяются один раз и не меняются)
        self._cached_price_to_beat = None
        self._cached_market_duration = None

        # Счетчики для логирования
        self._log_counter = 0  # Для статуса (каждые 15 сек)
        self._probability_log_counter = 0  # Для расчета вероятности (каждые 30 сек)

        logger.info(f"PositionManager инициализирован для рынка {market_id} (symbol: {self.symbol})")

    async def _get_symbol_from_cache(self) -> str:
        """
        Получить символ из PriceToBeatService (из кэша).
        
        Returns:
            Символ в формате для Binance (BTCUSDT/ETHUSDT/SOLUSDT)
        """
        try:
            symbol = await self.price_to_beat_service.get_symbol(self.market_id)
            if symbol:
                logger.debug(f"💾 Symbol для рынка {self.market_id} из кэша: {symbol}")
                return symbol
            else:
                logger.warning(f"❌ Symbol не найден для рынка {self.market_id}, используем BTCUSDT")
                return "BTCUSDT"
                
        except Exception as exc:
            logger.error(f"Ошибка при получении symbol для {self.market_id}: {exc}")
            return "BTCUSDT"

    async def start_management(self, initial_position: Position) -> None:
        """
        Запустить управление позициями для рынка.

        Args:
            initial_position: Первая позиция в рынке
        """
        self.positions = [initial_position]
        self.is_active = True

        logger.info(f"🚀 Начато управление позициями для рынка {self.market_id}")

        try:
            while self.is_active and self._market_active():
                # Обновляем вероятности каждую секунду
                await self._update_probabilities()

                await self._check_opposite_entry()
                await self._check_additional_entry()

                # Периодическое логирование каждые 15 секунд
                self._log_counter += 1
                if self._log_counter >= 15:
                    await self._log_status()
                    self._log_counter = 0

                await asyncio.sleep(1)  # Быстрая проверка каждую секунду

        except Exception as exc:
            logger.error(f"Ошибка в управлении позициями рынка {self.market_id}: {exc}")
        finally:
            self.is_active = False
            logger.info(f"🛑 Управление позициями остановлено для рынка {self.market_id}")

    def stop_management(self) -> None:
        """Остановить управление позициями."""
        self.is_active = False
        logger.info(f"Остановка управления позициями для рынка {self.market_id}")

    def _market_active(self) -> bool:
        """
        Проверить, активен ли еще рынок.

        Returns:
            True если рынок еще активен
        """
        try:
            # Получить информацию о рынке
            market_data = self.pm_client.get_market_data(self.market_id)
            if not market_data:
                return False

            # Проверить статус рынка
            market_state = market_data.get("state", "").lower()
            if market_state in ["closed", "resolved", "cancelled"]:
                logger.info(f"Рынок {self.market_id} закрыт (статус: {market_state})")
                # Рынок закрыт - закрываем позиции и останавливаемся
                # ЗАКОММЕНТИРОВАНО: self._close_positions_on_market_end(market_data)
                return False

            # Проверить время до окончания
            end_date = market_data.get("endDate")
            if end_date:
                end_datetime = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                if end_datetime < datetime.now(timezone.utc):
                    logger.info(f"Рынок {self.market_id} уже закончился")
                    # Рынок закончился - закрываем позиции и останавливаемся
                    # ЗАКОММЕНТИРОВАНО: self._close_positions_on_market_end(market_data)
                    return False

            return True

        except Exception as exc:
            logger.warning(f"Ошибка при проверке статуса рынка {self.market_id}: {exc}")
            return False

    async def _update_probabilities(self) -> None:
        """
        Обновить текущие вероятности для рынка.
        Рассчитывает вероятности заново каждую секунду.
        """
        try:
            # Обновить символ из кэша (если еще не обновлен) - ОДИН РАЗ
            if self.symbol == "BTCUSDT":  # Если еще не обновлен
                self.symbol = await self._get_symbol_from_cache()
                logger.debug(f"🔄 Обновлен символ для рынка {self.market_id}: {self.symbol}")

            # Получаем price_to_beat - КЕШИРУЕМ, не меняется для рынка!
            if self._cached_price_to_beat is None:
                self._cached_price_to_beat = await self.price_to_beat_service.get_price_to_beat(self.market_id)
                if self._cached_price_to_beat is None:
                    logger.warning(f"[{self.market_id}] Не удалось получить price_to_beat")
                    return
                logger.debug(f"[{self.market_id}] 💾 Закеширован price_to_beat: {self._cached_price_to_beat}")

            price_to_beat = self._cached_price_to_beat
            logger.debug(f"[{self.market_id}] Price to beat: {price_to_beat}")

            # Получить текущую цену актива
            symbol = self.symbol
            logger.debug(f"📊 [{self.market_id}] Запрашиваем цену для символа: {symbol}")
            current_price = self.price_monitor.get_price(symbol)
            if not current_price:
                logger.warning(f"[{self.market_id}] Не удалось получить текущую цену для {symbol}")
                return
            logger.debug(f"✅ [{self.market_id}] Получена цена {symbol}: ${current_price}")
            logger.debug(f"[{self.market_id}] Текущая цена {symbol}: {current_price}")

            # Получить волатильность
            volatility = self.price_monitor.get_volatility(symbol)
            if not volatility:
                logger.warning(f"[{self.market_id}] Не удалось получить волатильность для {symbol}")
                return
            logger.debug(f"[{self.market_id}] Волатильность: {volatility}")

            # Получить market_duration - КЕШИРУЕМ, не меняется для рынка!
            if self._cached_market_duration is None:
                self._cached_market_duration = await self.price_to_beat_service.get_market_duration(self.market_id)
                if not self._cached_market_duration:
                    logger.warning(f"[{self.market_id}] Не удалось получить market_duration, используем 15m")
                    self._cached_market_duration = "15m"
                logger.debug(f"[{self.market_id}] 💾 Закеширована market_duration: {self._cached_market_duration}")

            market_duration = self._cached_market_duration
            logger.debug(f"📊 [{self.market_id}] Market duration: {market_duration}")

            # Выбрать волатильность на основе продолжительности рынка
            if market_duration == "15m":
                vol_pct = volatility.get("15m") or volatility.get("5m") or volatility.get("1h") or 1.0
                vol_period_minutes = 15.0
            else:  # 1h
                vol_pct = volatility.get("1h") or volatility.get("15m") or volatility.get("5m") or 1.0
                vol_period_minutes = 60.0

            vol_pct_decimal = vol_pct / 100.0  # Конвертируем в десятичную форму (0.2939% → 0.002939)
            logger.debug(f"[{self.market_id}] Волатильность для расчетов: {vol_pct_decimal} (period: {vol_period_minutes} мин)")

            # Получить ATR
            stats = self.price_monitor.get_stats(symbol)
            atr = stats.get("atr") if stats else None
            logger.debug(f"[{self.market_id}] ATR: {atr}")

            # Создать экземпляр probability_analyzer если нужно
            if not hasattr(self, 'probability_analyzer'):
                from analysis.probability import PostEntryProbabilityAnalyzer
                self.probability_analyzer = PostEntryProbabilityAnalyzer()
                logger.debug(f"[{self.market_id}] Создан probability_analyzer")

            # Рассчитать вероятности
            vol_for_kf, _, _ = self.probability_analyzer.calculate_hybrid_volatility(
                vol_pct_decimal, atr, current_price
            )
            logger.debug(f"[{self.market_id}] Гибридная волатильность: {vol_for_kf}")

            # Рассчитать вероятности для UP и DOWN
            market_direction = "UP" if current_price < price_to_beat else "DOWN"
            logger.debug(f"[{self.market_id}] Направление рынка: {market_direction} (current={current_price}, target={price_to_beat})")

            # Получить orderbook цены
            orderbook_prices = self.order_manager.orderbook_analyzer.get_market_prices(self.market_id) or {}
            current_price_up = orderbook_prices.get("up_ask", 0.5)
            current_price_down = orderbook_prices.get("down_ask", 0.5)
            logger.debug(f"[{self.market_id}] Orderbook цены: UP={current_price_up}, DOWN={current_price_down}")

            # Рассчитать время до окончания рынка
            market_data = self.price_to_beat_service.get_market_info(self.market_id)

            if market_data:
                # Получить end_time из market_data (уже в ISO формате)
                end_time_str = market_data.get("end_time")
                if end_time_str:
                    try:
                        end_time_dt = datetime.fromisoformat(end_time_str.replace('Z', '+00:00'))
                        now = datetime.now(timezone.utc)
                        time_remaining_seconds = (end_time_dt - now).total_seconds()
                        time_remaining_minutes = max(0, time_remaining_seconds / 60.0)  # В минутах
                        logger.debug(f"[{self.market_id}] ⏰ Время до окончания: {time_remaining_minutes:.1f} мин (end_time: {end_time_dt})")
                    except Exception as e:
                        logger.warning(f"[{self.market_id}] Ошибка парсинга end_time: {e}, используем fallback")
                        time_remaining_minutes = 60  # Fallback
                else:
                    logger.warning(f"[{self.market_id}] end_time не найден в market_data, используем fallback")
                    time_remaining_minutes = 60  # Fallback
            else:
                logger.warning(f"[{self.market_id}] market_data не получен, используем fallback")
                time_remaining_minutes = 60  # Fallback

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

            # ДЕТАЛЬНЫЕ ЛОГИ РАСЧЕТА ВЕРОЯТНОСТИ (показать формулу + параметры)
            # Логируем раз в 30 секунд
            self._probability_log_counter += 1
            if self._probability_log_counter >= 30:
                logger.info(f"🧮 [{self.market_id}] РАСЧЕТ ВЕРОЯТНОСТИ:")
                logger.info(f"   📍 Текущая цена {symbol}: ${current_price:.2f}")
                logger.info(f"   🎯 Price to beat (target): ${price_to_beat:.2f}")
                logger.info(f"   📊 Направление рынка: {market_direction}")
                logger.info(f"   📈 Волатильность: {vol_pct_decimal*100:.2f}% ({vol_period_minutes:.0f} мин)")
                logger.info(f"   ⏰ Время до окончания: {time_remaining_minutes:.0f} мин")
                logger.info(f"   💹 ATR: {atr if atr else 'N/A'}")
                logger.info(f"   💰 Текущие цены: UP=${current_price_up:.4f}, DOWN=${current_price_down:.4f}")

                # ФОРМУЛЫ РАСЧЕТА (для UP)
                if prob_up.std_dev_pct is not None:
                    import math
                    time_ratio = time_remaining_minutes / vol_period_minutes
                    logger.info(f"   🔢 Формула std_dev для UP:")
                    logger.info(f"      std_dev = volatility × √(time_remaining / vol_period)")
                    logger.info(f"      std_dev = {vol_pct_decimal:.4f} × √({time_remaining_minutes:.0f} / {vol_period_minutes:.0f})")
                    logger.info(f"      std_dev = {vol_pct_decimal:.4f} × {math.sqrt(time_ratio):.4f} = {prob_up.std_dev_pct:.4f}")
                if prob_up.z_score is not None:
                    logger.info(f"      z_score = (target - current) / (current × std_dev)")
                    logger.info(f"      z_score = ({price_to_beat:.2f} - {current_price:.2f}) / ({current_price:.2f} × {prob_up.std_dev_pct:.4f}) = {prob_up.z_score:.4f}")
                    # Показываем как z_score переводится в вероятность через CDF
                    logger.info(f"   🎲 Формула вероятности:")
                    logger.info(f"      prob_UP = 1 - CDF(z_score_UP) = 1 - CDF({prob_up.z_score:.4f}) = {prob_up.reach_probability:.3f}")
                    if prob_down.z_score is not None:
                        logger.info(f"      prob_DOWN = CDF(z_score_DOWN) = CDF({prob_down.z_score:.4f}) = {prob_down.reach_probability:.3f}")

                logger.info(f"   ➡️  Результат: UP prob={prob_up.reach_probability:.3f}, DOWN prob={prob_down.reach_probability:.3f}")

                self._probability_log_counter = 0  # Сбросить счетчик

            # Сохранить рассчитанные вероятности
            self.current_probabilities = {
                "up_probability": prob_up.reach_probability,
                "down_probability": prob_down.reach_probability,
                "timestamp": datetime.now(timezone.utc),
            }

            logger.debug(f"[{self.market_id}] Вероятности рассчитаны: UP={prob_up.reach_probability:.3f}, DOWN={prob_down.reach_probability:.3f}")

        except Exception as exc:
            logger.error(f"[{self.market_id}] Ошибка при обновлении вероятностей: {exc}")
            self.current_probabilities = None

    async def _log_status(self) -> None:
        """
        Логировать текущий статус position manager каждые 15 секунд.
        Показывает позиции, текущие цены, вероятности и причины решений.
        """
        try:
            logger.info(f"📊 [{self.market_id}] СТАТУС POSITION MANAGER (каждые 15 сек)")

            # Информация о позициях
            logger.info(f"   📂 Позиций: {len(self.positions)}")
            for i, pos in enumerate(self.positions):
                logger.info(f"      {i+1}. {pos.side} ${pos.total_cost_usd:.2f} по ${pos.entry_price_avg:.4f} ({pos.entry_reason})")

            # Текущие вероятности
            if self.current_probabilities:
                up_prob = self.current_probabilities.get("up_probability", 0)
                down_prob = self.current_probabilities.get("down_probability", 0)
                logger.info(f"   📈 Вероятности: UP={up_prob:.3f}, DOWN={down_prob:.3f}")
            else:
                logger.info("   📈 Вероятности: недоступны")

            # Текущие цены
            up_price = await self._get_current_price("UP")
            down_price = await self._get_current_price("DOWN")
            if up_price and down_price:
                logger.info(f"   💰 Цены: UP=${up_price:.4f}, DOWN=${down_price:.4f}")
            else:
                logger.info("   💰 Цены: недоступны")

            # Логика принятия решений
            if len(self.positions) == 1:
                initial_pos = self.positions[0]
                opposite_side = "UP" if initial_pos.side == "DOWN" else "DOWN"

                # Проверяем условия для opposite entry
                can_enter_opposite = False
                reasons = []

                if self.current_probabilities:
                    opposite_prob = self.current_probabilities.get(f"{opposite_side.lower()}_probability", 0)
                    if opposite_prob >= MATH_PROB_FOR_OPPOSITE:
                        reasons.append(f"вероятность {opposite_prob:.3f} >= {MATH_PROB_FOR_OPPOSITE}")
                    else:
                        reasons.append(f"вероятность {opposite_prob:.3f} < {MATH_PROB_FOR_OPPOSITE}")

                opposite_price = await self._get_current_price(opposite_side)
                if opposite_price and opposite_price < PRICE_ENTRY_FOR_OPPOSITE:
                    reasons.append(f"цена {opposite_price:.4f} < {PRICE_ENTRY_FOR_OPPOSITE}")
                elif opposite_price:
                    reasons.append(f"цена {opposite_price:.4f} >= {PRICE_ENTRY_FOR_OPPOSITE}")

                can_enter_opposite = len(reasons) >= 2 and all(">" in r or "<" in r for r in reasons[:2])

                logger.info(f"   🎯 Opposite entry ({opposite_side}): {'ГОТОВ' if can_enter_opposite else 'НЕ ГОТОВ'}")
                for reason in reasons:
                    logger.info(f"      • {reason}")

            elif len(self.positions) == 2:
                initial_pos = self.positions[0]
                current_price = await self._get_current_price(initial_pos.side)

                if current_price:
                    # ИСПРАВЛЕНИЕ: Рассчитываем снижение по модулю
                    price_change_pct = ((current_price - initial_pos.entry_price_avg) / initial_pos.entry_price_avg) * 100
                    price_reduction_pct = abs(price_change_pct)
                    required_reduction = PERCENT_FOR_PRICE_REDUCE

                    can_enter_additional = price_reduction_pct >= required_reduction and price_change_pct < 0

                    # Определяем направление движения цены и причину
                    if price_change_pct > 0:
                        # Цена выросла - не можем входить
                        reason = f"цена ВЫРОСЛА на {price_reduction_pct:.1f}% (с ${initial_pos.entry_price_avg:.4f} до ${current_price:.4f})"
                    elif price_reduction_pct < required_reduction:
                        # Цена упала, но недостаточно
                        reason = f"снижение {price_reduction_pct:.1f}% < {required_reduction}% (недостаточно)"
                    else:
                        # Готов к входу
                        reason = f"цена УПАЛА на {price_reduction_pct:.1f}% (с ${initial_pos.entry_price_avg:.4f} до ${current_price:.4f})"

                    logger.info(f"   📈 Additional entry ({initial_pos.side}): {'ГОТОВ' if can_enter_additional else 'НЕ ГОТОВ'}")
                    logger.info(f"      • {reason}")

            logger.info(f"   ⏰ Активен: {self._market_active()}")
            logger.info(f"   🔄 Следующий статус через 15 секунд")

        except Exception as exc:
            logger.error(f"[{self.market_id}] Ошибка при логировании статуса: {exc}")

    async def _check_opposite_entry(self) -> None:
        """
        Проверить условия для входа в противоположную сторону.

        Алгоритм:
        1. Если есть только одна позиция
        2. Проверить вероятность противоположной стороны > MATH_PROB_FOR_OPPOSITE
        3. Проверить цену противоположной стороны < PRICE_ENTRY_FOR_OPPOSITE
        4. Рассчитать сумму входа для гарантии прибыли W1_PROFIT_PCT
        """
        if len(self.positions) != 1:
            logger.debug(f"[{self.market_id}] Пропуск проверки opposite entry: {len(self.positions)} позиций (нужна 1)")
            return  # Уже есть противоположная позиция

        initial_position = self.positions[0]
        opposite_side = "UP" if initial_position.side == "DOWN" else "DOWN"

        try:
            # Использовать текущие рассчитанные вероятности
            if not self.current_probabilities:
                logger.debug(f"[{self.market_id}] Пропуск opposite entry: вероятности не рассчитаны")
                return

            opposite_prob = self.current_probabilities.get(f"{opposite_side.lower()}_probability", 0)
            logger.debug(f"[{self.market_id}] Проверка opposite entry {opposite_side}: prob={opposite_prob:.3f}, threshold={MATH_PROB_FOR_OPPOSITE}")

            if opposite_prob < MATH_PROB_FOR_OPPOSITE:
                logger.info(f"❌ [{self.market_id}] Opposite entry {opposite_side} пропущен: вероятность {opposite_prob:.3f} < {MATH_PROB_FOR_OPPOSITE} (порог)")
                return

            # Получить текущую цену противоположной стороны
            opposite_price = await self._get_current_price(opposite_side)
            if opposite_price is None:
                logger.debug(f"[{self.market_id}] Пропуск opposite entry {opposite_side}: не удалось получить цену")
                return

            logger.debug(f"[{self.market_id}] Проверка opposite entry {opposite_side}: цена={opposite_price:.4f}, threshold={PRICE_ENTRY_FOR_OPPOSITE}")

            if opposite_price >= PRICE_ENTRY_FOR_OPPOSITE:
                logger.info(f"❌ [{self.market_id}] Opposite entry {opposite_side} пропущен: цена ${opposite_price:.4f} >= ${PRICE_ENTRY_FOR_OPPOSITE:.2f} (слишком дорого)")
                return

            # Рассчитать сумму для входа
            entry_amount = PositionCalculator.calculate_opposite_entry_amount(
                initial_position.total_cost_usd,
                initial_position.entry_price_avg,
                opposite_price
            )

            if entry_amount <= 0:
                logger.info(f"❌ [{self.market_id}] Opposite entry {opposite_side} пропущен: расчетная сумма входа ${entry_amount:.2f} <= 0 (неприбыльно)")
                return

            logger.info(f"🎯 [{self.market_id}] УСЛОВИЯ ДЛЯ ВХОДА В {opposite_side} ВЫПОЛНЕНЫ!")
            logger.info(f"   📊 Вероятность: {opposite_prob:.3f} > {MATH_PROB_FOR_OPPOSITE} ✓")
            logger.info(f"   💰 Цена: {opposite_price:.4f} < {PRICE_ENTRY_FOR_OPPOSITE} ✓")
            logger.info(f"   💵 Сумма входа: ${entry_amount:.2f}")
            logger.info(f"   🎲 Гарантированная прибыль: обеспечена хеджированием")

            # Войти в противоположную позицию
            await self._enter_position(opposite_side, entry_amount, opposite_price, "OPPOSITE_ENTRY")

        except Exception as exc:
            logger.error(f"[{self.market_id}] Ошибка при проверке противоположного входа: {exc}")

    async def _check_additional_entry(self) -> None:
        """
        Проверить условия для дополнительного входа в исходную сторону.

        Алгоритм:
        1. Если есть две позиции (исходная + противоположная)
        2. Проверить снижение цены исходной стороны на PERCENT_FOR_PRICE_REDUCE
        3. Рассчитать сумму для гарантии прибыли W1_PROFIT_PCT + W2_ADDITIONAL_PROFIT_PCT
        """
        if len(self.positions) != 2:
            logger.debug(f"[{self.market_id}] Пропуск проверки additional entry: {len(self.positions)} позиций (нужны 2)")
            return  # Нужно ровно две позиции

        # Найти исходную позицию (первая)
        initial_position = self.positions[0]
        opposite_position = self.positions[1]

        try:
            # Получить текущую цену исходной стороны
            current_price = await self._get_current_price(initial_position.side)
            if not current_price:
                logger.debug(f"[{self.market_id}] Пропуск additional entry: не удалось получить цену для {initial_position.side}")
                return

            # Проверяем, что цена снизилась (а не выросла)
            if current_price > initial_position.entry_price_avg:
                price_change_pct = ((current_price - initial_position.entry_price_avg) / initial_position.entry_price_avg) * 100
                logger.info(f"❌ [{self.market_id}] Additional entry {initial_position.side} пропущен: цена ВЫРОСЛА на {price_change_pct:.1f}% (с ${initial_position.entry_price_avg:.4f} до ${current_price:.4f})")
                return

            # Проверить снижение цены (ИСПРАВЛЕНИЕ: используем модуль)
            price_reduction_pct = abs((current_price - initial_position.entry_price_avg) / initial_position.entry_price_avg) * 100
            required_reduction = PERCENT_FOR_PRICE_REDUCE

            logger.debug(f"[{self.market_id}] Проверка additional entry {initial_position.side}: снижение={price_reduction_pct:.1f}%, требуется={required_reduction}%")

            if price_reduction_pct < required_reduction:
                logger.info(f"❌ [{self.market_id}] Additional entry {initial_position.side} пропущен: снижение цены {price_reduction_pct:.1f}% < {required_reduction}% (недостаточно)")
                return

            # Рассчитать сумму для дополнительного входа
            additional_amount = PositionCalculator.calculate_additional_entry_amount(
                self.positions,
                current_price
            )

            if additional_amount <= 0:
                logger.debug(f"[{self.market_id}] Пропуск additional entry {initial_position.side}: расчетная сумма <= 0")
                return

            logger.info(f"📈 [{self.market_id}] УСЛОВИЯ ДЛЯ ДОПОЛНИТЕЛЬНОГО ВХОДА В {initial_position.side} ВЫПОЛНЕНЫ!")
            logger.info(f"   📉 Снижение цены: {price_reduction_pct:.1f}% >= {required_reduction}% ✓")
            logger.info(f"   💵 Сумма входа: ${additional_amount:.2f}")
            logger.info(f"   🎯 Цель: усилить позицию для большей прибыли")

            # Войти дополнительно в исходную позицию
            await self._enter_position(initial_position.side, additional_amount, current_price, "ADDITIONAL_ENTRY")

        except Exception as exc:
            logger.error(f"[{self.market_id}] Ошибка при проверке дополнительного входа: {exc}")

    async def _get_current_probabilities(self) -> Optional[Dict[str, float]]:
        """
        Получить текущие математические вероятности для рынка.
        Использует market_analyzer для расчета наших вероятностей.

        Returns:
            Dict с вероятностями или None
        """
        try:
            # Импортируем market_analyzer (глобальный экземпляр)
            from web.app import market_analyzer
            if not market_analyzer:
                logger.debug("Market analyzer не доступен")
                return None

            # Получить анализ рынка
            analysis = await market_analyzer.analyze_market(self.market_id)
            if not analysis or "probabilities" not in analysis:
                logger.debug("Не удалось получить анализ рынка")
                return None

            probabilities = analysis["probabilities"]

            return {
                "up_probability": probabilities.get("up", {}).get("math_probability", 0.5),
                "down_probability": probabilities.get("down", {}).get("math_probability", 0.5)
            }

        except Exception as exc:
            logger.error(f"Ошибка при получении вероятностей: {exc}")
            return None

    async def _get_current_price(self, side: str) -> Optional[float]:
        """
        Получить текущую ask цену для указанной стороны.
        Использует orderbook с правильным mapping сторон.

        Args:
            side: "UP" или "DOWN"

        Returns:
            Ask цена или None
        """
        try:
            # Использовать orderbook для получения цены
            if hasattr(self.order_manager, 'orderbook_analyzer'):
                # Получить распарсенные цены из orderbook
                prices = self.order_manager.orderbook_analyzer.get_market_prices(self.market_id)
                if prices:
                    if side == "UP":
                        return prices.get("up_ask")
                    elif side == "DOWN":
                        return prices.get("down_ask")

            # Fallback: использовать orderbook напрямую
            orderbook = self.order_manager.orderbook_analyzer.get_orderbook(self.market_id)
            if orderbook and 'orderbooks' in orderbook:
                # Найти лучшую ask цену для нужной стороны
                # В Polymarket orderbook: outcome_0 обычно UP, outcome_1 обычно DOWN
                if side == "UP" and 'outcome_0' in orderbook['orderbooks']:
                    outcome_data = orderbook['orderbooks']['outcome_0']
                    if 'asks' in outcome_data and outcome_data['asks']:
                        # Сортируем asks по цене (наименьшая цена первая)
                        asks = sorted(outcome_data['asks'], key=lambda x: float(x['price']))
                        return float(asks[0]['price'])

                elif side == "DOWN" and 'outcome_1' in orderbook['orderbooks']:
                    outcome_data = orderbook['orderbooks']['outcome_1']
                    if 'asks' in outcome_data and outcome_data['asks']:
                        # Сортируем asks по цене (наименьшая цена первая)
                        asks = sorted(outcome_data['asks'], key=lambda x: float(x['price']))
                        return float(asks[0]['price'])

            # Последний fallback на API
            market_data = self.pm_client.get_market_data(self.market_id)
            if market_data and 'bestBid' in market_data:
                return float(market_data['bestBid'])

            return None

        except Exception as exc:
            logger.error(f"Ошибка при получении цены для {side}: {exc}")
            return None



    async def _enter_position(
        self,
        side: str,
        amount: float,
        price: float,
        entry_reason: str
    ) -> None:
        """
        Войти в позицию.

        Args:
            side: Сторона входа
            amount: Сумма входа
            price: Цена входа
            entry_reason: Причина входа
        """
        try:
            logger.info(f"💰 Вход в позицию {side} на сумму ${amount:.2f} по цене ${price:.4f}")

            # Разместить ордер
            result = self.order_manager.buy_outcome(
                market_id=self.market_id,
                side=side,
                amount_usdc=amount,
                price=price
            )

            if result and result.get("success"):
                # Получить price_to_beat для позиции
                price_to_beat = await self.price_to_beat_service.get_price_to_beat(self.market_id)

                # Получить market_title из кэша
                market_data = self.price_to_beat_service.get_market_info(self.market_id)
                market_title = market_data.get("title") or market_data.get("question") or f"Market {self.market_id}" if market_data else f"Market {self.market_id}"

                # Создать объект позиции
                position = Position(
                    position_id=f"pos_{self.market_id}_{int(datetime.now(timezone.utc).timestamp())}_{entry_reason.lower()}",
                    market_id=self.market_id,
                    market_title=market_title,  # Из кэша PriceToBeatService
                    symbol=self.symbol,  # Из self.symbol (обновляется из кэша)
                    side=side,
                    entry_time=datetime.now(timezone.utc),
                    entry_price_avg=price,
                    total_volume=amount / price if price > 0 else 0,
                    total_cost_usd=amount,
                    entry_reason=entry_reason,
                    market_start_time=None,  # Рынок уже активен
                    minutes_until_start=0,
                    start_price=price_to_beat,  # Price to beat при входе
                )

                # Добавить позицию
                self.positions.append(position)
                position_storage.add_position(position)

                logger.info(f"✅ Успешный вход в позицию {position.position_id} ({entry_reason})")
            else:
                logger.warning(f"❌ Не удалось войти в позицию {side}")

        except Exception as exc:
            logger.error(f"Ошибка при входе в позицию: {exc}")

    # Удален дублированный код - теперь используется PriceToBeatService



# Глобальный реестр менеджеров позиций
_position_managers: Dict[str, PositionManager] = {}


def get_position_manager(market_id: str) -> Optional[PositionManager]:
    """Получить менеджер позиций для рынка."""
    return _position_managers.get(market_id)


def create_position_manager(
    market_id: str,
    polymarket_client: PolymarketClient,
    order_manager: OrderManager,
    price_monitor: PriceMonitor
) -> PositionManager:
    """Создать менеджер позиций для рынка."""
    if market_id in _position_managers:
        return _position_managers[market_id]

    manager = PositionManager(market_id, polymarket_client, order_manager, price_monitor)
    _position_managers[market_id] = manager

    return manager


def stop_all_position_managers() -> None:
    """Остановить все менеджеры позиций."""
    for manager in _position_managers.values():
        manager.stop_management()
    _position_managers.clear()
    logger.info("Все менеджеры позиций остановлены")