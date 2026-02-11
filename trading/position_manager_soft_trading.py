"""
Position Manager Soft Trading - мягкая стратегия управления позициями.

ОТЛИЧИЯ ОТ СТАНДАРТНОЙ СТРАТЕГИИ:
=====================================

СТАНДАРТНАЯ СТРАТЕГИЯ (position_manager.py):
- Работает вместе с auto_entry системой
- Автоматический вход за минуту до старта рынка
- Агрессивное хеджирование с противоположными позициями
- Дополнительные входы при снижении цены на 15%
- Цель: максимизация прибыли через хеджирование

SOFT TRADING СТРАТЕГИЯ (этот файл):
- Работает БЕЗ auto_entry системы
- Ручной или выборочный вход в рынки
- Более консервативные условия входа
- Гибкие параметры управления рисками
- Цель: стабильная прибыль с меньшими рисками

КАК ИСПОЛЬЗОВАТЬ:
- В config.py установите: TRADING_STRATEGY = "soft_trading"
- Или в .env файле: TRADING_STRATEGY=soft_trading
- Перезапустите бота

TODO: Здесь будет реализована ваша альтернативная логика!
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from app.config import (
    SIM_MODE,
    SOFT_TRADE_EDGE_ENTER,
    SOFT_TRADE_FIRST_POSITION_USD,
    SOFT_TRADE_MAX_LOSS_PCT,
    SOFT_TRADE_MIN_IMPROVEMENT_PCT,
    SOFT_TRADE_CHECK_INTERVAL,
    SOFT_TRADE_TARGET_SUM,
    SOFT_TRADE_COOLDOWN_AFTER_BUY
)
from polymarket.client import PolymarketClient
from monitoring.price_monitor import PriceMonitor
from trading.order_manager import OrderManager
from trading.position import Position, position_storage
from trading.position_calculator import PositionCalculator
from analysis.price_to_beat_service import PriceToBeatService

logger = logging.getLogger(__name__)


class PositionManagerSoftTrading:
    """
    Мягкая стратегия управления позициями (без auto_entry).

    Альтернативный подход:
    1. Более консервативные условия входа
    2. Другая логика управления рисками
    3. Измененные параметры для хеджирования
    4. Гибкий мониторинг рынка
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

        # Отдельный трекинг для UP и DOWN позиций (для soft trading)
        self.positions_up: List[Position] = []  # Только UP позиции
        self.positions_down: List[Position] = []  # Только DOWN позиции

        # Время последней покупки (для cooldown)
        self.last_buy_time: Optional[datetime] = None

        # Текущие рассчитанные вероятности
        self.current_probabilities = None

        # Единый сервис для получения price_to_beat
        self.price_to_beat_service = PriceToBeatService(price_monitor, polymarket_client)

        # Определяем символ для рынка (BTC/ETH/SOL) из кэша PriceToBeatService
        # Используем fallback значение, так как инициализация происходит синхронно
        self.symbol = "BTCUSDT"  # Будет обновлен при первом вызове _get_symbol_from_cache()

        logger.info(f"PositionManagerSoftTrading инициализирован для рынка {market_id} (symbol: {self.symbol})")

    async def _get_symbol_from_cache(self) -> str:
        """
        Получить символ из PriceToBeatService (из кэша).
        
        Returns:
            Символ в формате для Binance (BTCUSDT/ETHUSDT/SOLUSDT)
        """
        try:
            symbol = await self.price_to_beat_service.get_symbol(self.market_id)
            if symbol:
                logger.info(f"💾 Symbol для рынка {self.market_id} из кэша: {symbol}")
                return symbol
            else:
                logger.warning(f"❌ Symbol не найден для рынка {self.market_id}, используем BTCUSDT")
                return "BTCUSDT"
                
        except Exception as exc:
            logger.error(f"Ошибка при получении symbol для {self.market_id}: {exc}")
            return "BTCUSDT"

    async def start_management(self, initial_position: Optional[Position] = None) -> None:
        """
        Запустить управление позициями для рынка (SOFT TRADING).

        Args:
            initial_position: Начальная позиция (опционально, для совместимости с auto_entry)
        """
        if initial_position:
            self.positions = [initial_position]
            # Разделяем по сторонам
            if initial_position.side == "UP":
                self.positions_up = [initial_position]
            else:
                self.positions_down = [initial_position]
        else:
            self.positions = []
            self.positions_up = []
            self.positions_down = []

        self.is_active = True
        self._log_counter = 0  # Счетчик для периодического логирования

        logger.info(f"🚀 Начато управление позициями SOFT TRADING для рынка {self.market_id}")
        if initial_position:
            logger.info(f"   📊 Начальная позиция: {initial_position.side} ${initial_position.total_cost_usd:.2f}")
        else:
            logger.info(f"   📊 Без начальной позиции, мониторим рынок")

        try:
            while self.is_active and self._market_active():
                # Обновляем вероятности каждую секунду
                await self._update_probabilities()

                # Проверяем возможности входа (новая логика soft trading)
                await self._check_entry_opportunities()

                # Периодическое логирование каждые 5 секунд
                self._log_counter += 1
                if self._log_counter >= 5:
                    await self._log_status()
                    self._log_counter = 0

                # Проверяем по интервалу из config
                await asyncio.sleep(SOFT_TRADE_CHECK_INTERVAL)

        except Exception as exc:
            logger.error(f"Ошибка в управлении позициями рынка {self.market_id}: {exc}")
        finally:
            self.is_active = False
            logger.info(f"🛑 Управление позициями SOFT TRADING остановлено для рынка {self.market_id}")

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
            # Обновить символ из кэша (если еще не обновлен)
            if self.symbol == "BTCUSDT":  # Если еще не обновлен
                self.symbol = await self._get_symbol_from_cache()
                logger.info(f"🔄 Обновлен символ для рынка {self.market_id}: {self.symbol}")

            # Получаем price_to_beat из единого сервиса (асинхронно)
            price_to_beat = await self.price_to_beat_service.get_price_to_beat(self.market_id)
            if price_to_beat is None:
                logger.warning(f"[{self.market_id}] Не удалось получить price_to_beat")
                return

            logger.debug(f"[{self.market_id}] Price to beat: {price_to_beat}")

            # Получить текущую цену актива
            symbol = self.symbol
            logger.info(f"📊 [{self.market_id}] Запрашиваем цену для символа: {symbol}")
            current_price = self.price_monitor.get_price(symbol)
            if not current_price:
                logger.warning(f"[{self.market_id}] Не удалось получить текущую цену для {symbol}")
                return
            logger.info(f"✅ [{self.market_id}] Получена цена {symbol}: ${current_price}")
            logger.debug(f"[{self.market_id}] Текущая цена {symbol}: {current_price}")

            # Получить волатильность
            volatility = self.price_monitor.get_volatility(symbol)
            if not volatility:
                logger.warning(f"[{self.market_id}] Не удалось получить волатильность для {symbol}")
                return
            logger.debug(f"[{self.market_id}] Волатильность: {volatility}")

            # Получить market_duration из кэша PriceToBeatService
            market_duration = await self.price_to_beat_service.get_market_duration(self.market_id)
            if not market_duration:
                logger.warning(f"[{self.market_id}] Не удалось получить market_duration, используем 15m")
                market_duration = "15m"

            logger.info(f"📊 [{self.market_id}] Market duration: {market_duration}")

            # Выбрать волатильность на основе продолжительности рынка
            if market_duration == "15m":
                vol_pct = volatility.get("15m") or volatility.get("5m") or volatility.get("1h") or 1.0
                vol_period_minutes = 15.0
            else:  # 1h
                vol_pct = volatility.get("1h") or volatility.get("15m") or volatility.get("5m") or 1.0
                vol_period_minutes = 60.0

            vol_pct_decimal = vol_pct / 100.0  # Конвертировать в десятичную форму
            logger.debug(f"[{self.market_id}] Волатильность для расчетов: {vol_pct}% -> {vol_pct_decimal} (period: {vol_period_minutes} мин)")

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

            # Рассчитать время до окончания (примерно)
            time_remaining_minutes = 60  # TODO: рассчитывать точно
            logger.debug(f"[{self.market_id}] Время до окончания: {time_remaining_minutes} мин")

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
        Логировать текущий статус position manager каждые 5 секунд.
        Показывает позиции, текущие цены, вероятности и причины решений.
        """
        try:
            logger.info(f"📊 [{self.market_id}] СТАТУС SOFT TRADING MANAGER (каждые 5 сек)")

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

            # SOFT TRADING: Показать средние цены и целевую сумму
            if self.positions_up or self.positions_down:
                # Рассчитать средние цены
                if self.positions_up:
                    total_cost_up = sum(p.total_cost_usd for p in self.positions_up)
                    total_volume_up = sum(p.total_volume for p in self.positions_up)
                    avg_price_up = total_cost_up / total_volume_up if total_volume_up > 0 else 0
                else:
                    avg_price_up = 0

                if self.positions_down:
                    total_cost_down = sum(p.total_cost_usd for p in self.positions_down)
                    total_volume_down = sum(p.total_volume for p in self.positions_down)
                    avg_price_down = total_cost_down / total_volume_down if total_volume_down > 0 else 0
                else:
                    avg_price_down = 0

                # Рассчитать целевую сумму
                total_avg = avg_price_up + avg_price_down

                logger.info(f"   💎 SOFT TRADING:")
                if self.positions_up:
                    logger.info(f"      UP: {len(self.positions_up)} поз, avg=${avg_price_up:.4f}")
                else:
                    logger.info(f"      UP: нет позиций")

                if self.positions_down:
                    logger.info(f"      DOWN: {len(self.positions_down)} поз, avg=${avg_price_down:.4f}")
                else:
                    logger.info(f"      DOWN: нет позиций")

                if self.positions_up and self.positions_down:
                    status = "✅ ПРИБЫЛЬ" if total_avg < 1.0 else "⏳ В ПРОЦЕССЕ"
                    target_diff = (SOFT_TRADE_TARGET_SUM - total_avg) * 100
                    logger.info(f"      СУММА: ${total_avg:.4f} {status}")
                    logger.info(f"      До цели ({SOFT_TRADE_TARGET_SUM}): {target_diff:+.2f}%")

            logger.info(f"   ⏰ Активен: {self._market_active()}")
            logger.info(f"   🔄 Следующий статус через 5 секунд")

        except Exception as exc:
            logger.error(f"[{self.market_id}] Ошибка при логировании статуса: {exc}")

    async def _check_entry_opportunities(self) -> None:
        """
        SOFT TRADING: Проверить возможности входа для обеих сторон.

        Логика:
        1. Рассчитать edge для UP и DOWN (уже есть в current_probabilities)
        2. Если edge_UP > порог И цена улучшает среднюю → купить UP
        3. Если edge_DOWN > порог И цена улучшает среднюю → купить DOWN
        4. Рассчитать безопасную сумму с учетом риска
        """
        try:
            # Проверка cooldown после последней покупки
            if self.last_buy_time:
                time_since_buy = (datetime.now(timezone.utc) - self.last_buy_time).total_seconds()
                if time_since_buy < SOFT_TRADE_COOLDOWN_AFTER_BUY:
                    logger.debug(f"[{self.market_id}] Cooldown: {time_since_buy:.1f}s / {SOFT_TRADE_COOLDOWN_AFTER_BUY}s")
                    return

            # Проверить, что вероятности рассчитаны
            if not self.current_probabilities:
                logger.debug(f"[{self.market_id}] Пропуск: вероятности не рассчитаны")
                return

            # Получить edge для UP и DOWN из current_probabilities
            # Edge уже рассчитан в _update_probabilities через probability_analyzer
            up_prob = self.current_probabilities.get("up_probability", 0)
            down_prob = self.current_probabilities.get("down_probability", 0)

            # В вероятностном анализе, если вероятность > 0.5, есть положительный edge
            # Рассчитаем edge как превышение над 50%
            up_edge_pct = (up_prob - 0.5) * 100 if up_prob > 0.5 else 0
            down_edge_pct = (down_prob - 0.5) * 100 if down_prob > 0.5 else 0

            logger.debug(f"[{self.market_id}] Edge: UP={up_edge_pct:.2f}%, DOWN={down_edge_pct:.2f}% (порог={SOFT_TRADE_EDGE_ENTER}%)")

            # Проверяем UP
            if up_edge_pct >= SOFT_TRADE_EDGE_ENTER:
                await self._try_buy_side("UP", up_edge_pct)

            # Проверяем DOWN
            if down_edge_pct >= SOFT_TRADE_EDGE_ENTER:
                await self._try_buy_side("DOWN", down_edge_pct)

        except Exception as exc:
            logger.error(f"[{self.market_id}] Ошибка при проверке возможностей входа: {exc}")

    async def _try_buy_side(self, side: str, edge_pct: float) -> None:
        """
        Попытаться купить указанную сторону (UP или DOWN).

        Args:
            side: "UP" или "DOWN"
            edge_pct: Edge в процентах
        """
        try:
            # Получить текущую цену
            current_price = await self._get_current_price(side)
            if not current_price:
                logger.debug(f"[{self.market_id}] Пропуск {side}: не удалось получить цену")
                return

            # Получить позиции этой стороны
            side_positions = self.positions_up if side == "UP" else self.positions_down

            # Рассчитать среднюю цену текущих позиций этой стороны
            if side_positions:
                total_cost = sum(p.total_cost_usd for p in side_positions)
                total_volume = sum(p.total_volume for p in side_positions)
                avg_price = total_cost / total_volume if total_volume > 0 else 0

                # Проверить улучшение цены
                price_improvement = ((avg_price - current_price) / avg_price) * 100 if avg_price > 0 else 100

                logger.debug(f"[{self.market_id}] {side}: avg=${avg_price:.4f}, current=${current_price:.4f}, improvement={price_improvement:.2f}%")

                if price_improvement < SOFT_TRADE_MIN_IMPROVEMENT_PCT:
                    logger.debug(f"[{self.market_id}] Пропуск {side}: улучшение {price_improvement:.2f}% < {SOFT_TRADE_MIN_IMPROVEMENT_PCT}%")
                    return

                # Рассчитать безопасную сумму для докупки
                amount = self._calculate_safe_amount(side, current_price, side_positions)
            else:
                # Первая позиция этой стороны
                amount = SOFT_TRADE_FIRST_POSITION_USD
                logger.info(f"[{self.market_id}] {side}: Первая позиция, сумма=${amount:.2f}")

            if amount <= 0:
                logger.debug(f"[{self.market_id}] Пропуск {side}: рассчитанная сумма <= 0")
                return

            logger.info(f"🎯 [{self.market_id}] ПОКУПКА {side}!")
            logger.info(f"   📊 Edge: {edge_pct:.2f}% > {SOFT_TRADE_EDGE_ENTER}%")
            logger.info(f"   💰 Цена: ${current_price:.4f}")
            logger.info(f"   💵 Сумма: ${amount:.2f}")

            # Войти в позицию
            await self._enter_position(side, amount, current_price, "SOFT_TRADE_ENTRY")

        except Exception as exc:
            logger.error(f"[{self.market_id}] Ошибка при попытке купить {side}: {exc}")

    def _calculate_safe_amount(
        self,
        side: str,
        new_price: float,
        existing_positions: List[Position]
    ) -> float:
        """
        Рассчитать безопасную сумму для докупки с учетом риска.

        Args:
            side: "UP" или "DOWN"
            new_price: Новая цена для покупки
            existing_positions: Существующие позиции этой стороны

        Returns:
            Безопасная сумма для входа ($)
        """
        if not existing_positions:
            return SOFT_TRADE_FIRST_POSITION_USD

        # Рассчитать текущие инвестиции
        total_invested = sum(p.total_cost_usd for p in existing_positions)

        # Максимально допустимый убыток при проигрыше этой стороны
        max_loss_allowed = total_invested * (SOFT_TRADE_MAX_LOSS_PCT / 100.0)

        # При проигрыше этой стороны мы теряем всю сумму
        # Поэтому новая сумма не должна превышать max_loss_allowed
        safe_amount = min(max_loss_allowed, SOFT_TRADE_FIRST_POSITION_USD * 2)

        logger.debug(f"[{self.market_id}] Safe amount для {side}: invested=${total_invested:.2f}, max_loss=${max_loss_allowed:.2f}, safe=${safe_amount:.2f}")

        return safe_amount

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
                # Создать объект позиции
                # Получить title из кэша PriceToBeatService
                _minfo = self.price_to_beat_service.get_market_info(self.market_id)
                _mtitle = _minfo.get("title", f"Market {self.market_id}") if _minfo else f"Market {self.market_id}"

                position = Position(
                    position_id=f"pos_{self.market_id}_{int(datetime.now(timezone.utc).timestamp())}_{entry_reason.lower()}",
                    market_id=self.market_id,
                    market_title=_mtitle,
                    symbol=self.symbol,
                    side=side,
                    entry_time=datetime.now(timezone.utc),
                    entry_price_avg=price,
                    total_volume=amount / price if price > 0 else 0,
                    total_cost_usd=amount,
                    entry_reason=entry_reason,
                    market_start_time=None,  # Рынок уже активен
                    minutes_until_start=0,
                )

                # Добавить позицию
                self.positions.append(position)
                position_storage.add_position(position)

                # Обновить трекинг для soft trading
                if side == "UP":
                    self.positions_up.append(position)
                else:
                    self.positions_down.append(position)

                # Обновить время последней покупки
                self.last_buy_time = datetime.now(timezone.utc)

                logger.info(f"✅ Успешный вход в позицию {position.position_id} ({entry_reason})")
                logger.info(f"   📊 Позиций UP: {len(self.positions_up)}, DOWN: {len(self.positions_down)}")
            else:
                logger.warning(f"❌ Не удалось войти в позицию {side}")

        except Exception as exc:
            logger.error(f"Ошибка при входе в позицию: {exc}")

    # Удален дублированный код - теперь используется PriceToBeatService

    def _close_positions_on_market_end(self, market_data: Dict) -> None:
        """
        Закрыть все позиции по рынку при его завершении.

        Args:
            market_data: Данные о рынке из API
        """
        try:
            from trading.position import position_storage, determine_market_outcome

            # Проверяем есть ли открытые позиции по этому рынку
            open_positions = [pos for pos in position_storage.get_open_positions()
                            if pos.market_id == self.market_id]

            if not open_positions:
                logger.debug(f"Нет открытых позиций для закрытия в рынке {self.market_id}")
                return

            logger.info(f"🎯 Закрываем {len(open_positions)} позиций при завершении рынка {self.market_id}")

            # Проверяем статус рынка более детально
            market_state = market_data.get("state", "").lower()
            end_date = market_data.get("endDate")
            
            logger.info(f"📊 Рынок {self.market_id}: статус={market_state}, end_date={end_date}")

            # Проверяем время окончания рынка
            end_time = None
            if end_date:
                try:
                    end_time = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                    current_time = datetime.now(timezone.utc)
                    
                    logger.info(f"⏰ Рынок {self.market_id}: end_time={end_time}, current_time={current_time}")
                    
                    if end_time > current_time:
                        logger.info(f"⏳ Рынок {self.market_id} еще не завершился (осталось {(end_time - current_time).total_seconds():.0f} сек)")
                        return
                        
                except Exception as e:
                    logger.error(f"Ошибка парсинга времени окончания рынка {self.market_id}: {e}")
                    return

            # Получаем price_to_beat из единого сервиса (синхронно)
            price_to_beat = self.price_to_beat_service.cache.get(self.market_id)
            if not price_to_beat:
                # Fallback: используем текущую цену
                price_to_beat = self.price_monitor.get_price(self.symbol) or 1.0
                logger.warning(f"Price_to_beat не найден для {self.market_id}, используем текущую цену ${price_to_beat}")

            # Получаем цену на конец рынка из коллектора
            # Используем новый метод из PriceToBeatService для получения end_price
            end_price = self.price_to_beat_service.get_end_price(self.market_id)

            if not end_price or end_price <= 0:
                logger.warning(f"Не удалось получить цену на конец рынка {self.market_id}, используем текущую цену")
                end_price = self.price_monitor.get_price(self.symbol) or price_to_beat

            logger.info(f"📊 Рынок {self.market_id}: price_to_beat=${price_to_beat:.2f}, end_price=${end_price:.2f}")

            # Определяем исход рынка
            outcome = determine_market_outcome(price_to_beat, end_price)
            outcome_str = outcome.get("outcome", "UNKNOWN") if isinstance(outcome, dict) else str(outcome)
            logger.info(f"🏆 Исход рынка {self.market_id}: {outcome_str} (end_price ${end_price:.2f} {'<' if end_price < price_to_beat else '>='} price_to_beat ${price_to_beat:.2f})")

            # Закрываем все позиции по рынку
            closed_positions = position_storage.close_market_positions(self.market_id, outcome, end_price)

            if closed_positions:
                logger.info(f"✅ Закрыто {len(closed_positions)} позиций при завершении рынка {self.market_id}")
                for pos in closed_positions:
                    logger.info(f"   📝 Закрыта позиция {pos.position_id}: {pos.side} → {outcome}, P&L=${pos.pnl_usd:.2f} ({pos.pnl_pct:.2f}%)")
            else:
                logger.warning(f"Не удалось закрыть позиции при завершении рынка {self.market_id}")

        except Exception as exc:
            logger.error(f"Ошибка при закрытии позиций рынка {self.market_id}: {exc}")


# Глобальный реестр менеджеров позиций (soft trading)
_position_managers_soft: Dict[str, PositionManagerSoftTrading] = {}


def get_position_manager_soft(market_id: str) -> Optional[PositionManagerSoftTrading]:
    """Получить менеджер позиций soft trading для рынка."""
    return _position_managers_soft.get(market_id)


def create_position_manager_soft(
    market_id: str,
    polymarket_client: PolymarketClient,
    order_manager: OrderManager,
    price_monitor: PriceMonitor
) -> PositionManagerSoftTrading:
    """Создать менеджер позиций soft trading для рынка."""
    if market_id in _position_managers_soft:
        return _position_managers_soft[market_id]

    manager = PositionManagerSoftTrading(market_id, polymarket_client, order_manager, price_monitor)
    _position_managers_soft[market_id] = manager

    return manager


def stop_all_position_managers_soft() -> None:
    """Остановить все менеджеры позиций soft trading."""
    for manager in _position_managers_soft.values():
        manager.stop_management()
    _position_managers_soft.clear()
    logger.info("Все менеджеры позиций soft trading остановлены")