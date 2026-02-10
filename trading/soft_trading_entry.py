"""
Soft Trading Entry System - запуск soft trading менеджеров для выбранных рынков.

Аналог auto_entry, но вместо постепенной покупки запускает только PositionManagerSoftTrading.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional
import schedule
import time

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
from trading.position_manager_soft_trading import create_position_manager_soft

logger = logging.getLogger(__name__)


class SoftTradingEntrySystem:
    """
    Система запуска soft trading менеджеров для выбранных рынков.

    Аналог AutoEntrySystem, но вместо постепенной покупки:
    - Выбирает лучшие рынки через MarketPreSelector
    - Запускает PositionManagerSoftTrading за N минут до старта
    - Менеджер сам мониторит и покупает при условиях
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

        # Состояние системы
        self.is_running = False
        self.current_session = None
        self.event_loop = None

    def start_scheduler(self):
        """Запустить планировщик soft trading."""
        logger.info("🌙 Запуск планировщика Soft Trading...")

        # Рассчитать времена запуска на основе настроек
        # Рынки стартуют в :00, :15, :30, :45 каждого часа
        market_start_minutes = [0, 15, 30, 45]

        for start_minute in market_start_minutes:
            # Время запуска = время старта рынка - минуты до старта
            launch_minute = (start_minute - FIRST_ENTRY_MINUTES_BEFORE_START) % 60
            launch_time = f":{launch_minute:02d}"

            schedule.every().hour.at(launch_time).do(self._run_entry_session)
            logger.debug(f"🌙 Запланирован запуск в {launch_time} (для рынка в :{start_minute:02d})")

        logger.info(f"✅ Планировщик Soft Trading запущен. Сессии будут запускаться за {FIRST_ENTRY_MINUTES_BEFORE_START} мин до старта рынков")

    def stop_scheduler(self):
        """Остановить планировщик."""
        logger.info("🛑 Остановка планировщика Soft Trading...")
        schedule.clear()
        self.is_running = False

    def _run_entry_session(self):
        """Запустить сессию запуска soft trading менеджеров."""
        if self.is_running:
            logger.warning("⚠️ Предыдущая сессия еще не завершена, пропускаем новую")
            return

        try:
            self.is_running = True
            logger.info("🚀 Запуск сессии Soft Trading Entry")

            # Запустить асинхронную сессию через event loop
            if self.event_loop:
                asyncio.run_coroutine_threadsafe(self._soft_trading_entry_session(), self.event_loop)
            else:
                logger.error("❌ Event loop не установлен, не можем запустить сессию")
                self.is_running = False

        except Exception as exc:
            logger.error(f"Ошибка при запуске сессии soft trading: {exc}", exc_info=True)
            self.is_running = False

    async def _soft_trading_entry_session(self):
        """Выполнить сессию запуска soft trading менеджеров."""
        try:
            session_start = datetime.now(timezone.utc)
            logger.info(f"📈 Начало сессии Soft Trading Entry в {session_start}")

            # Получить топ рынки для входа
            top_markets = self.market_pre_selector.select_best_momentum_markets(
                self.market_pre_selector.select_markets_starting_soon(),
                max_markets=10  # Берем топ-10 для выбора
            )

            # Выбрать рынки для входа
            markets_to_enter = self._select_markets_for_entry(top_markets)

            if not markets_to_enter:
                logger.info("ℹ️ Нет подходящих рынков для soft trading в этой сессии")
                return

            logger.info(f"✅ Выбрано {len(markets_to_enter)} рынков для soft trading: {[m.get('title', '')[:60] for m in markets_to_enter]}")

            # Запустить менеджеры для выбранных рынков
            for market in markets_to_enter:
                try:
                    market_id = market.get("market_id")
                    if not market_id:
                        continue

                    logger.info(f"🌙 Запуск Soft Trading для рынка {market_id}")

                    # Создать менеджер
                    manager = create_position_manager_soft(
                        market_id=market_id,
                        polymarket_client=self.pm_client,
                        order_manager=self.order_manager,
                        price_monitor=self.price_monitor
                    )

                    # Запустить управление БЕЗ начальной позиции
                    # Менеджер сам будет мониторить и покупать при условиях
                    asyncio.create_task(manager.start_management())

                    logger.info(f"✅ Soft Trading менеджер запущен для рынка {market_id}")

                except Exception as exc:
                    logger.error(f"Ошибка при запуске soft trading для рынка {market.get('market_id')}: {exc}")

            session_duration = datetime.now(timezone.utc) - session_start
            logger.info(f"✅ Сессия Soft Trading Entry завершена за {session_duration.total_seconds():.1f} сек")

        except Exception as exc:
            logger.error(f"Ошибка в сессии soft trading entry: {exc}", exc_info=True)
        finally:
            self.is_running = False

    def _select_markets_for_entry(self, top_markets: Dict) -> List[Dict]:
        """Выбрать рынки для запуска soft trading на основе настроек."""
        markets_to_enter = []

        # Добавить 15m рынки
        if ENTER_TO_15M_MARKETS and M15_MARKETS_NUMBER_TO_ENTER > 0:
            m15_markets = top_markets.get("15m_markets", [])[:M15_MARKETS_NUMBER_TO_ENTER]
            markets_to_enter.extend(m15_markets)
            logger.info(f"✅ Выбрано {len(m15_markets)} 15m рынков для soft trading")

        # Добавить 1h рынки
        if ENTER_TO_1H_MARKETS and H1_MARKETS_NUMBER_TO_ENTER > 0:
            h1_markets = top_markets.get("1h_markets", [])[:H1_MARKETS_NUMBER_TO_ENTER]
            markets_to_enter.extend(h1_markets)
            logger.info(f"✅ Выбрано {len(h1_markets)} 1h рынков для soft trading")

        return markets_to_enter


# Глобальный экземпляр системы soft trading entry
soft_trading_entry_system: Optional[SoftTradingEntrySystem] = None


def get_soft_trading_entry_system() -> SoftTradingEntrySystem:
    """Получить глобальный экземпляр системы soft trading entry."""
    return soft_trading_entry_system


def init_soft_trading_entry_system(
    polymarket_client: PolymarketClient,
    price_monitor: PriceMonitor,
    order_manager: OrderManager
) -> SoftTradingEntrySystem:
    """Инициализировать систему soft trading entry."""
    global soft_trading_entry_system
    soft_trading_entry_system = SoftTradingEntrySystem(polymarket_client, price_monitor, order_manager)

    # Установить event loop для межпоточного общения
    try:
        soft_trading_entry_system.event_loop = asyncio.get_running_loop()
        logger.info("✅ Event loop установлен для системы soft trading entry")
    except RuntimeError:
        # Если нет running loop, попробуем получить event loop позже
        logger.warning("⚠️ Не удалось получить running event loop, будет установлен позже")

    return soft_trading_entry_system
