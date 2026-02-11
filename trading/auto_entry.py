"""
Auto-Entry System - автоматический вход в рынки перед их стартом.

Запускается по расписанию перед стартом рынков и постепенно входит в позиции
с распределением суммы по времени для усреднения цены.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional
import schedule
import time
from datetime import datetime as dt  # Для избежания конфликтов

from app.config import (
    FIRST_POSITION_SIZE_PCT,
    MAX_PRICE_FOR_FIRST_ENTRY,
    ENTER_TO_1H_MARKETS,
    ENTER_TO_15M_MARKETS,
    H1_MARKETS_NUMBER_TO_ENTER,
    M15_MARKETS_NUMBER_TO_ENTER,
    AMOUNT_OF_ONE_BUY_IN_LOOP,
    LOOP_DELAY,
    SIM_MODE,
    FIRST_ENTRY_MINUTES_BEFORE_START,
    FIRST_ENTRY_ITERATIONS,
    FIRST_ENTRY_ITERATION_DELAY,
    TRADING_STRATEGY
)
from analysis.market_pre_selector import MarketPreSelector
from analysis.price_to_beat_service import PriceToBeatService
from polymarket.client import PolymarketClient
from monitoring.price_monitor import PriceMonitor
from trading.order_manager import OrderManager
from trading.position import Position, position_storage

logger = logging.getLogger(__name__)


class AutoEntrySystem:
    """
    Система автоматического входа в рынки перед их стартом.

    Запускает сессии входа в определенное время перед стартом рынков,
    постепенно покупает позиции с распределением суммы.
    """

    def __init__(
        self,
        polymarket_client: PolymarketClient,
        price_monitor: PriceMonitor,
        order_manager: OrderManager
    ):
        """
        Args:
            polymarket_client: Клиент Polymarket
            price_monitor: Монитор цен
            order_manager: Менеджер ордеров
        """
        self.pm_client = polymarket_client
        self.price_monitor = price_monitor
        self.order_manager = order_manager
        self.market_pre_selector = MarketPreSelector(polymarket_client, price_monitor)
        self.price_to_beat_service = PriceToBeatService(price_monitor, polymarket_client)

        # Состояние системы
        self.is_running = False
        self.current_session = None
        self.event_loop = None  # Для межпоточного общения

        # Статистика для SIM режима
        self.total_cost = 0.0  # Общая стоимость покупок
        self.total_volume = 0.0  # Общий объем покупок
        self.average_price = 0.0  # Средняя цена покупки

    def start_scheduler(self):
        """Запустить планировщик автоматического входа."""
        logger.info("Запуск планировщика автоматического входа...")

        # Рассчитать времена запуска на основе настроек
        # Рынки стартуют в :00, :15, :30, :45 каждого часа
        market_start_minutes = [0, 15, 30, 45]

        for start_minute in market_start_minutes:
            # Время запуска = время старта рынка - минуты до старта
            launch_minute = (start_minute - FIRST_ENTRY_MINUTES_BEFORE_START) % 60
            launch_time = f":{launch_minute:02d}"

            schedule.every().hour.at(launch_time).do(self._run_entry_session)
            logger.debug("Запланирован запуск в %s (для рынка в :%02d)", launch_time, start_minute)

        logger.info("Планировщик запущен. Сессии входа будут запускаться за %s мин до старта рынков",
                   FIRST_ENTRY_MINUTES_BEFORE_START)

    def stop_scheduler(self):
        """Остановить планировщик."""
        logger.info("Остановка планировщика автоматического входа...")
        schedule.clear()
        self.is_running = False

    def _run_entry_session(self):
        """Запустить сессию автоматического входа."""
        if self.is_running:
            logger.warning("Предыдущая сессия еще не завершена, пропускаем новую")
            return

        try:
            self.is_running = True
            logger.info("🚀 Запуск сессии автоматического входа")

            # Запустить асинхронную сессию через event loop
            if self.event_loop:
                asyncio.run_coroutine_threadsafe(self._auto_entry_session(), self.event_loop)
            else:
                logger.error("Event loop не установлен, не можем запустить сессию")
                self.is_running = False

        except Exception as exc:
            logger.error("Ошибка при запуске сессии входа: %s", exc, exc_info=True)
            self.is_running = False

    async def _auto_entry_session(self):
        """Выполнить сессию автоматического входа."""
        try:
            session_start = datetime.now(timezone.utc)
            logger.info("📈 Начало сессии автоматического входа в %s", session_start)

            # Получить топ рынки для входа
            top_markets = self.market_pre_selector.select_best_momentum_markets(
                self.market_pre_selector.select_markets_starting_soon(),
                max_markets=10  # Берем топ-10 для выбора
            )

            # Выбрать рынки для входа
            markets_to_enter = self._select_markets_for_entry(top_markets)

            if not markets_to_enter:
                logger.info("Нет подходящих рынков для входа в этой сессии")
                return

            logger.info("Выбрано %s рынков для входа: %s",
                       len(markets_to_enter),
                       [m.get("title", "")[:60] for m in markets_to_enter])

            # Запустить параллельные входы в рынки
            tasks = []
            for market in markets_to_enter:
                task = asyncio.create_task(self._enter_market(market))
                tasks.append(task)

            # Дождаться завершения всех входов
            await asyncio.gather(*tasks, return_exceptions=True)

            session_duration = datetime.now(timezone.utc) - session_start
            logger.info("✅ Сессия автоматического входа завершена за %.1f сек",
                       session_duration.total_seconds())

        except Exception as exc:
            logger.error("Ошибка в сессии автоматического входа: %s", exc, exc_info=True)
        finally:
            self.is_running = False

    def _select_markets_for_entry(self, top_markets: Dict) -> List[Dict]:
        """Выбрать рынки для входа на основе настроек."""
        markets_to_enter = []

        # Добавить 15m рынки
        if ENTER_TO_15M_MARKETS and M15_MARKETS_NUMBER_TO_ENTER > 0:
            m15_markets = top_markets.get("15m_markets", [])[:M15_MARKETS_NUMBER_TO_ENTER]
            markets_to_enter.extend(m15_markets)
            logger.info("Выбрано %s 15m рынков для входа", len(m15_markets))

        # Добавить 1h рынки
        if ENTER_TO_1H_MARKETS and H1_MARKETS_NUMBER_TO_ENTER > 0:
            h1_markets = top_markets.get("1h_markets", [])[:H1_MARKETS_NUMBER_TO_ENTER]
            markets_to_enter.extend(h1_markets)
            logger.info("Выбрано %s 1h рынков для входа", len(h1_markets))

        return markets_to_enter

    async def _enter_market(self, market: Dict):
        """Войти в конкретный рынок с постепенной покупкой."""
        try:
            market_id = market.get("market_id")
            title = market.get("title", "")
            side = market.get("recommended_side", "UP")

            logger.info("🎯 Начинаем вход в рынок %s (%s): %s",
                       market_id, side, title[:50])

            # Рассчитать общую сумму для входа
            total_amount = self._calculate_entry_amount()

            if total_amount <= 0:
                logger.warning("Сумма для входа <= 0, пропускаем рынок %s", market_id)
                return

            logger.info("💰 Сумма для входа: $%.2f (%s)",
                       total_amount, "SIM" if SIM_MODE else "REAL")

            # Выполнить постепенную покупку
            market_start_time = market.get("start_time")
            await self._buy_position_gradually(market_id, side, total_amount, market_start_time)

            logger.info("✅ Вход в рынок %s завершен", market_id)

        except Exception as exc:
            logger.error("Ошибка при входе в рынок %s: %s",
                        market.get("market_id"), exc, exc_info=True)

    def _calculate_entry_amount(self) -> float:
        """Рассчитать сумму для входа (% от баланса)."""
        try:
            # Получить текущий баланс
            if SIM_MODE:
                # В симуляции используем начальный баланс
                from app.config import SIMULATION_INITIAL_BALANCE
                balance = SIMULATION_INITIAL_BALANCE
            else:
                # В реальном режиме получаем баланс из order_manager
                balance = self.order_manager.get_balance()

            # Рассчитать сумму как процент от баланса
            amount = balance * (FIRST_POSITION_SIZE_PCT / 100.0)

            logger.debug("Расчет суммы входа: баланс=$%.2f, процент=%.1f%%, сумма=$%.2f",
                        balance, FIRST_POSITION_SIZE_PCT, amount)

            return amount

        except Exception as exc:
            logger.error("Ошибка при расчете суммы входа: %s", exc)
            return 0.0

    async def _buy_position_gradually(
        self,
        market_id: str,
        side: str,
        total_amount: float,
        market_start_time: Optional[datetime] = None,
        iterations: int = FIRST_ENTRY_ITERATIONS,
        iteration_delay: float = FIRST_ENTRY_ITERATION_DELAY
    ):
        """
        Постепенно купить позицию с распределением по времени.

        Args:
            market_id: ID рынка
            side: Сторона входа ("UP" или "DOWN")
            total_amount: Общая сумма для входа
            iterations: Количество итераций (6 по умолчанию)
            iteration_delay: Задержка между итерациями (30 сек)
        """
        logger.info("🛒 Начинаем постепенную покупку позиции %s %s на сумму $%.2f",
                   market_id, side, total_amount)

        # Рассчитать сумму на одну итерацию (равномерное распределение)
        amount_per_iteration = total_amount / iterations

        # Получить ордербук для логирования
        orderbook = None
        if hasattr(self.order_manager, 'orderbook_analyzer'):
            orderbook = self.order_manager.orderbook_analyzer.get_orderbook(market_id)

        for iteration in range(1, iterations + 1):
            try:
                # Проверить, не прошло ли больше 3 минут с момента старта рынка
                if market_start_time:
                    time_since_start = datetime.now(timezone.utc) - market_start_time
                    if time_since_start > timedelta(minutes=3):
                        logger.info("⏰ Рынок %s уже стартовал >3 мин назад (%s), прекращаем покупки",
                                   market_id, time_since_start)
                        break

                if iteration == 1:
                    logger.info("🎯 FIRST ITERATION STARTED AT %s", datetime.now(timezone.utc).strftime("%H:%M:%S"))

                    # Выведем полный ордербук перед первой итерацией
                    if orderbook and 'orderbooks' in orderbook:
                        logger.info(f"=== ORDERBOOK DUMP FOR MARKET {market_id} BEFORE FIRST ITERATION ===")
                        for outcome_key, outcome_data in orderbook['orderbooks'].items():
                            logger.info(f"Outcome {outcome_key}:")
                            if 'bids' in outcome_data and outcome_data['bids']:
                                bids_sorted = sorted(outcome_data['bids'], key=lambda x: float(x['price']), reverse=True)  # Highest first
                                logger.info(f"  BIDS (top 5, highest first): {bids_sorted[:5]}")
                            if 'asks' in outcome_data and outcome_data['asks']:
                                asks_sorted = sorted(outcome_data['asks'], key=lambda x: float(x['price']))  # Lowest first
                                logger.info(f"  ASKS (top 5, lowest first): {asks_sorted[:5]}")
                        logger.info("=== END ORDERBOOK DUMP ===")
                    else:
                        logger.warning(f"No orderbook data available for market {market_id}")

                logger.info("🔄 Итерация %s/%s: покупка $%.2f",
                           iteration, iterations, amount_per_iteration)

                # Проверить текущую цену для нужной стороны
                current_price = await self._get_current_price(market_id, side)
                if current_price >= MAX_PRICE_FOR_FIRST_ENTRY:
                    logger.info("💸 Цена %.4f >= лимита %.4f, пропускаем итерацию %s",
                               current_price, MAX_PRICE_FOR_FIRST_ENTRY, iteration)
                    await asyncio.sleep(iteration_delay)
                    continue

                # Купить часть позиции
                await self._buy_amount(market_id, side, amount_per_iteration)

                # Задержка перед следующей итерацией
                if iteration < iterations:
                    logger.debug("⏳ Ожидание %.1f сек перед следующей итерацией", iteration_delay)
                    await asyncio.sleep(iteration_delay)

            except Exception as exc:
                logger.error("Ошибка в итерации %s: %s", iteration, exc)
                continue

        # Создать объект позиции после завершения всех итераций покупки
        minutes_until_start = 0
        if market_start_time:
            if market_start_time > datetime.now(timezone.utc):
                # Рынок еще не стартовал
                minutes_until_start = (market_start_time - datetime.now(timezone.utc)).total_seconds() / 60
            else:
                # Рынок уже стартовал
                minutes_until_start = 0

        # Получить price_to_beat (цена актива на момент старта рынка)
        price_to_beat = await self.price_to_beat_service.get_price_to_beat(market_id)
        if price_to_beat:
            logger.info(f"💾 Price to beat для позиции {market_id}: ${price_to_beat:.2f}")
        else:
            logger.warning(f"⚠️  Не удалось получить price_to_beat для {market_id}")

        # Получить symbol и title из кэша PriceToBeatService
        market_info = self.price_to_beat_service.get_market_info(market_id)
        market_symbol = market_info.get("symbol", "UNKNOWN") if market_info else "UNKNOWN"
        market_title = market_info.get("title", f"Market {market_id}") if market_info else f"Market {market_id}"

        position = Position(
            position_id=f"pos_{market_id}_{int(datetime.now(timezone.utc).timestamp())}",
            market_id=market_id,
            market_title=market_title,
            symbol=market_symbol,
            side=side,
            entry_time=datetime.now(timezone.utc),
            entry_price_avg=self.average_price if SIM_MODE else current_price,
            total_volume=self.total_volume if SIM_MODE else amount_per_iteration * iterations,
            total_cost_usd=total_amount,
            entry_reason="FIRST_ENTRY",
            market_start_time=market_start_time,
            minutes_until_start=round(minutes_until_start, 1),
            start_price=price_to_beat,  # Добавлено: price to beat (цена актива на момент старта рынка)
            momentum_score=None,  # market.get("momentum_score"),  # Упростим
            momentum_data={},  # market.get("momentum_data", {}),  # Упростим
            trend_direction=None,  # market.get("trend_direction"),  # Упростим
            math_probability=None,  # market.get("math_probability"),  # Упростим
            edge=None,  # market.get("edge"),  # Упростим
            recommended_side=None,  # market.get("recommended_side"),  # Упростим
            confidence_score=None  # market.get("confidence_score")  # Упростим
        )

        position_storage.add_position(position)
        logger.info(f"📝 Создана позиция {position.position_id} с причиной FIRST_ENTRY")

        # ЗАПУСТИТЬ POSITION MANAGER для управления позицией после первого входа
        # Выбор стратегии на основе настройки TRADING_STRATEGY
        if TRADING_STRATEGY == "soft_trading":
            logger.info(f"🎯 Создание PositionManagerSoftTrading для рынка {market_id}")
            from trading.position_manager_soft_trading import create_position_manager_soft
            position_manager = create_position_manager_soft(
                market_id=market_id,
                polymarket_client=self.pm_client,
                order_manager=self.order_manager,
                price_monitor=self.price_monitor
            )
            logger.info(f"✅ PositionManagerSoftTrading создан для рынка {market_id}")
        else:
            logger.info(f"🎯 Создание PositionManager (default) для рынка {market_id}")
            from trading.position_manager import create_position_manager
            position_manager = create_position_manager(
                market_id=market_id,
                polymarket_client=self.pm_client,
                order_manager=self.order_manager,
                price_monitor=self.price_monitor
            )
            logger.info(f"✅ PositionManager (default) создан для рынка {market_id}")

        # Запустить управление в фоне
        logger.info(f"🚀 Запуск управления позициями для рынка {market_id} (стратегия: {TRADING_STRATEGY})")
        asyncio.create_task(position_manager.start_management(position))
        logger.info(f"🚀 PositionManager запущен для рынка {market_id}")

        logger.info("🏁 Постепенная покупка позиции %s завершена", market_id)

    async def _get_current_price(self, market_id: str, side: str = "UP") -> float:
        """
        Получить текущую цену для конкретной стороны (UP/DOWN).

        Args:
            market_id: ID рынка
            side: "UP" или "DOWN" - определяет какой outcome использовать
        """
        try:
            # Определяем outcome: 0 = UP, 1 = DOWN
            target_outcome = 0 if side.upper() == "UP" else 1
            target_outcome_key = f"outcome_{target_outcome}"

            # Используем orderbook для получения лучшей цены
            if hasattr(self.order_manager, 'orderbook_analyzer'):
                orderbook = self.order_manager.orderbook_analyzer.get_orderbook(market_id)
                if orderbook and 'orderbooks' in orderbook:
                    # Polymarket формат: orderbooks для каждого outcome
                    best_price = 0.0
                    total_bids = 0
                    total_asks = 0

                    # Ищем цену для НУЖНОГО outcome
                    if target_outcome_key in orderbook['orderbooks']:
                        outcome_data = orderbook['orderbooks'][target_outcome_key]
                        if 'asks' in outcome_data and outcome_data['asks']:
                            # Берем минимальную ask цену для этого outcome
                            asks = [float(ask['price']) for ask in outcome_data['asks']]
                            best_price = min(asks) if asks else 0.0
                            total_asks = len(outcome_data['asks'])

                        if 'bids' in outcome_data and outcome_data['bids']:
                            total_bids = len(outcome_data['bids'])

                    if best_price > 0:
                        logger.info("📊 Ордербук %s %s (outcome_%d): best_ask=%.4f, bids=%s, asks=%s",
                                   market_id, side, target_outcome, best_price, total_bids, total_asks)
                        return best_price

                # Fallback: получить из API
                market_data = self.pm_client.get_market_data(market_id)
                if market_data and 'bestBid' in market_data:
                    best_bid = float(market_data['bestBid'])
                    logger.info("📊 API цена %s: best_bid=%.4f", market_id, best_bid)
                    return best_bid

            logger.warning("Не удалось получить текущую цену для рынка %s", market_id)
            return 1.0  # Безопасное значение

        except Exception as exc:
            logger.error("Ошибка при получении цены рынка %s: %s", market_id, exc)
            return 1.0

    async def _buy_amount(self, market_id: str, side: str, amount: float):
        """
        Купить указанную сумму постепенно (по 1$ каждую секунду).

        Args:
            market_id: ID рынка
            side: Сторона ("UP" или "DOWN")
            amount: Сумма для покупки
        """
        logger.info("💰 Покупка $%.2f для %s %s", amount, market_id, side)

        remaining = amount
        total_bought = 0.0

        while remaining > 0:
            try:
                # Определить сумму для этой покупки
                buy_amount = min(AMOUNT_OF_ONE_BUY_IN_LOOP, remaining)

                # Получить текущую цену для нужной стороны
                current_price = await self._get_current_price(market_id, side)

                # Рассчитать количество outcome tokens
                outcome_amount = buy_amount / current_price

                logger.info("🛒 Покупка %s: %.6f outcome tokens по цене %.4f ($%.2f)",
                           side, outcome_amount, current_price, buy_amount)

                # Разместить ордер
                if SIM_MODE:
                    # В симуляции ведем учет средней цены
                    self.total_cost += buy_amount
                    self.total_volume += outcome_amount
                    self.average_price = self.total_cost / self.total_volume if self.total_volume > 0 else 0

                    logger.info("🎭 SIM %s: Куплено %.6f tokens по цене %.4f | Средняя цена: %.4f",
                               side, outcome_amount, current_price, self.average_price)
                else:
                    # В реальном режиме размещаем ордер
                    result = self.order_manager.buy_outcome(
                        market_id=market_id,
                        side=side,
                        amount_usdc=buy_amount,
                        price=current_price
                    )
                    if result:
                        logger.info("✅ REAL %s: Ордер размещен - %s", side, result)
                    else:
                        logger.warning("❌ REAL %s: Не удалось разместить ордер", side)

                # Обновить счетчики
                total_bought += buy_amount
                remaining -= buy_amount

                logger.info("📊 Прогресс: куплено $%.2f из $%.2f, осталось $%.2f",
                           total_bought, amount, remaining)

                # Задержка перед следующей покупкой
                if remaining > 0:
                    await asyncio.sleep(LOOP_DELAY)

            except Exception as exc:
                logger.error("Ошибка при покупке: %s", exc)
                break

        logger.info("✅ Покупка суммы $%.2f завершена, всего куплено $%.2f",
                   amount, total_bought)


# Глобальный экземпляр системы авто-входа
auto_entry_system: Optional[AutoEntrySystem] = None


def get_auto_entry_system() -> AutoEntrySystem:
    """Получить глобальный экземпляр системы авто-входа."""
    return auto_entry_system


def init_auto_entry_system(
    polymarket_client: PolymarketClient,
    price_monitor: PriceMonitor,
    order_manager: OrderManager
) -> AutoEntrySystem:
    """Инициализировать систему авто-входа."""
    global auto_entry_system
    auto_entry_system = AutoEntrySystem(polymarket_client, price_monitor, order_manager)

    # Установить event loop для межпоточного общения
    try:
        auto_entry_system.event_loop = asyncio.get_running_loop()
        logger.info("Event loop установлен для системы авто-входа")
    except RuntimeError:
        # Если нет running loop, попробуем получить event loop позже
        logger.warning("Не удалось получить running event loop, будет установлен позже")

    return auto_entry_system
