"""
Balanced Trading Entry System - запуск balanced trading менеджеров для выбранных рынков.

Аналог soft_trading_entry, но запускает PositionManagerBalancedTrading
вместо PositionManagerSoftTrading.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Dict, Optional
import schedule

from app.config import (
    ENTER_TO_1H_MARKETS,
    ENTER_TO_15M_MARKETS,
    H1_MARKETS_NUMBER_TO_ENTER,
    M15_MARKETS_NUMBER_TO_ENTER,
    FIRST_ENTRY_MINUTES_BEFORE_START,
)
from analysis.market_pre_selector import MarketPreSelector
from polymarket.client import PolymarketClient
from monitoring.price_monitor import PriceMonitor
from trading.order_manager import OrderManager
from trading.position_manager_balanced_trading import create_position_manager_balanced

logger = logging.getLogger(__name__)


class BalancedTradingEntrySystem:
    """
    Система запуска balanced trading менеджеров для выбранных рынков.

    Аналог SoftTradingEntrySystem:
    - Выбирает лучшие рынки через MarketPreSelector
    - Запускает PositionManagerBalancedTrading за N минут до старта
    - Менеджер сам выполняет двусторонний вход и перебалансировку
    """

    def __init__(
        self,
        polymarket_client: PolymarketClient,
        price_monitor: PriceMonitor,
        order_manager: OrderManager,
    ):
        self.pm_client = polymarket_client
        self.price_monitor = price_monitor
        self.order_manager = order_manager
        self.market_pre_selector = MarketPreSelector(polymarket_client, price_monitor)

        self.is_running = False
        self.current_session = None
        self.event_loop = None

    def start_scheduler(self):
        """Запустить планировщик balanced trading."""
        logger.info("⚖️ Запуск планировщика Balanced Trading...")

        market_start_minutes = [0, 15, 30, 45]

        for start_minute in market_start_minutes:
            launch_minute = (start_minute - FIRST_ENTRY_MINUTES_BEFORE_START) % 60
            launch_time = f":{launch_minute:02d}"
            schedule.every().hour.at(launch_time).do(self._run_entry_session)
            logger.debug(f"⚖️ Запланирован запуск в {launch_time} (для рынка в :{start_minute:02d})")

        logger.info(
            f"✅ Планировщик Balanced Trading запущен. "
            f"Сессии за {FIRST_ENTRY_MINUTES_BEFORE_START} мин до старта рынков"
        )

    def stop_scheduler(self):
        """Остановить планировщик."""
        logger.info("🛑 Остановка планировщика Balanced Trading...")
        schedule.clear()
        self.is_running = False

    def _run_entry_session(self):
        """Запустить сессию."""
        if self.is_running:
            logger.warning("⚠️ Предыдущая сессия еще не завершена, пропускаем")
            return

        try:
            self.is_running = True
            logger.info("🚀 Запуск сессии Balanced Trading Entry")

            if self.event_loop:
                asyncio.run_coroutine_threadsafe(self._balanced_entry_session(), self.event_loop)
            else:
                logger.error("❌ Event loop не установлен")
                self.is_running = False

        except Exception as exc:
            logger.error(f"Ошибка при запуске сессии balanced trading: {exc}", exc_info=True)
            self.is_running = False

    async def _balanced_entry_session(self):
        """Выполнить сессию запуска balanced trading менеджеров."""
        try:
            session_start = datetime.now(timezone.utc)
            logger.info(f"📈 Начало сессии Balanced Trading Entry в {session_start}")

            top_markets = self.market_pre_selector.select_best_momentum_markets(
                self.market_pre_selector.select_markets_starting_soon(),
                max_markets=10,
            )

            markets_to_enter = self._select_markets_for_entry(top_markets)

            if not markets_to_enter:
                logger.info("ℹ️ Нет подходящих рынков для balanced trading")
                return

            logger.info(
                f"✅ Выбрано {len(markets_to_enter)} рынков для balanced trading: "
                f"{[m.get('title', '')[:60] for m in markets_to_enter]}"
            )

            for market in markets_to_enter:
                try:
                    market_id = market.get("market_id")
                    if not market_id:
                        continue

                    logger.info(f"⚖️ Запуск Balanced Trading для рынка {market_id}")

                    manager = create_position_manager_balanced(
                        market_id=market_id,
                        polymarket_client=self.pm_client,
                        order_manager=self.order_manager,
                        price_monitor=self.price_monitor,
                    )

                    asyncio.create_task(manager.start_management())
                    logger.info(f"✅ Balanced Trading менеджер запущен для рынка {market_id}")

                except Exception as exc:
                    logger.error(f"Ошибка при запуске balanced trading для {market.get('market_id')}: {exc}")

            session_duration = datetime.now(timezone.utc) - session_start
            logger.info(f"✅ Сессия Balanced Trading Entry завершена за {session_duration.total_seconds():.1f} сек")

        except Exception as exc:
            logger.error(f"Ошибка в сессии balanced trading entry: {exc}", exc_info=True)
        finally:
            self.is_running = False

    def _select_markets_for_entry(self, top_markets: Dict) -> List[Dict]:
        """Выбрать рынки для balanced trading."""
        markets_to_enter = []

        if ENTER_TO_15M_MARKETS and M15_MARKETS_NUMBER_TO_ENTER > 0:
            m15_markets = top_markets.get("15m_markets", [])[:M15_MARKETS_NUMBER_TO_ENTER]
            markets_to_enter.extend(m15_markets)
            logger.info(f"✅ Выбрано {len(m15_markets)} 15m рынков для balanced trading")

        if ENTER_TO_1H_MARKETS and H1_MARKETS_NUMBER_TO_ENTER > 0:
            h1_markets = top_markets.get("1h_markets", [])[:H1_MARKETS_NUMBER_TO_ENTER]
            markets_to_enter.extend(h1_markets)
            logger.info(f"✅ Выбрано {len(h1_markets)} 1h рынков для balanced trading")

        return markets_to_enter


# Глобальный экземпляр
balanced_trading_entry_system: Optional[BalancedTradingEntrySystem] = None


def get_balanced_trading_entry_system() -> Optional[BalancedTradingEntrySystem]:
    """Получить глобальный экземпляр."""
    return balanced_trading_entry_system


def init_balanced_trading_entry_system(
    polymarket_client: PolymarketClient,
    price_monitor: PriceMonitor,
    order_manager: OrderManager,
) -> BalancedTradingEntrySystem:
    """Инициализировать систему balanced trading entry."""
    global balanced_trading_entry_system
    balanced_trading_entry_system = BalancedTradingEntrySystem(
        polymarket_client, price_monitor, order_manager
    )

    try:
        balanced_trading_entry_system.event_loop = asyncio.get_running_loop()
        logger.info("✅ Event loop установлен для balanced trading entry")
    except RuntimeError:
        logger.warning("⚠️ Не удалось получить running event loop, будет установлен позже")

    return balanced_trading_entry_system
