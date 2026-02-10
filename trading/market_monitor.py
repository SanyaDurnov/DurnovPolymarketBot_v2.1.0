"""
Market Monitor - фоновый процесс для мониторинга завершенных рынков.

Отдельный процесс, который каждые 15 минут проверяет все открытые позиции
и закрывает их при завершении рынков.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from app.config import MARKET_MONITOR_INTERVAL
from polymarket.client import PolymarketClient
from trading.position import position_storage, determine_market_outcome

logger = logging.getLogger(__name__)


class MarketMonitor:
    """
    Фоновый мониторинг завершенных рынков.
    
    Запускается как отдельная задача и каждые N минут проверяет:
    1. Статус всех открытых рынков
    2. Время окончания рынков
    3. Закрывает позиции при завершении рынка
    """

    def __init__(
        self,
        polymarket_client: PolymarketClient,
        price_monitor,
        position_storage_instance=None
    ):
        """
        Args:
            polymarket_client: Клиент Polymarket для получения данных рынка
            price_monitor: PriceMonitor для получения цен
            position_storage_instance: Хранилище позиций (если не указано, использует глобальное)
        """
        self.pm_client = polymarket_client
        self.price_monitor = price_monitor
        self.position_storage = position_storage_instance or position_storage
        self.is_running = False
        
        logger.info(f"MarketMonitor инициализирован (интервал: {MARKET_MONITOR_INTERVAL} мин)")

    async def start_monitoring(self) -> None:
        """
        Запустить фоновый мониторинг.
        """
        if self.is_running:
            logger.warning("MarketMonitor уже запущен")
            return

        self.is_running = True
        logger.info(f"🚀 Запущен MarketMonitor (интервал: {MARKET_MONITOR_INTERVAL} мин)")

        try:
            while self.is_running:
                await self._check_and_close_positions()
                await asyncio.sleep(MARKET_MONITOR_INTERVAL * 60)  # Интервал в секундах
        except Exception as exc:
            logger.error(f"Ошибка в фоновом мониторинге: {exc}")
        finally:
            self.is_running = False
            logger.info("🛑 MarketMonitor остановлен")

    def stop_monitoring(self) -> None:
        """Остановить фоновый мониторинг."""
        self.is_running = False
        logger.info("Остановка MarketMonitor")

    async def _check_and_close_positions(self) -> None:
        """
        Проверить все открытые позиции и закрыть при завершении рынка.
        """
        try:
            # Получить все открытые позиции
            open_positions = self.position_storage.get_open_positions()
            
            if not open_positions:
                logger.debug("Нет открытых позиций для проверки")
                return

            logger.info(f"🔍 Проверка {len(open_positions)} открытых позиций на завершение рынков")

            # Группируем позиции по рынкам
            markets_to_check = set(pos.market_id for pos in open_positions)
            
            for market_id in markets_to_check:
                await self._check_market_and_close_positions(market_id)

        except Exception as exc:
            logger.error(f"Ошибка при проверке позиций: {exc}")

    async def _check_market_and_close_positions(self, market_id: str) -> None:
        """
        Проверить конкретный рынок и закрыть позиции при необходимости.
        
        Args:
            market_id: ID рынка для проверки
        """
        try:
            # Получить информацию о рынке
            market_data = self.pm_client.get_market_data(market_id)
            if not market_data:
                logger.warning(f"Не удалось получить данные рынка {market_id}")
                return

            # Проверить статус рынка
            market_state = market_data.get("state", "").lower()
            end_date = market_data.get("endDate")
            
            logger.debug(f"📊 Рынок {market_id}: статус={market_state}, end_date={end_date}")

            # Определяем, завершен ли рынок
            is_market_closed = self._is_market_closed(market_state, end_date)
            
            if is_market_closed:
                await self._close_positions_for_market(market_id, market_data)
            else:
                logger.debug(f"⏳ Рынок {market_id} еще активен")

        except Exception as exc:
            logger.error(f"Ошибка при проверке рынка {market_id}: {exc}")

    def _is_market_closed(self, market_state: str, end_date: Optional[str]) -> bool:
        """
        Определить, завершен ли рынок.
        
        Args:
            market_state: Статус рынка
            end_date: Дата окончания рынка
            
        Returns:
            True если рынок завершен
        """
        # Проверка по статусу
        if market_state in ["closed", "resolved", "cancelled"]:
            logger.info(f"Рынок завершен по статусу: {market_state}")
            return True

        # Проверка по времени
        if end_date:
            try:
                end_datetime = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                current_time = datetime.now(timezone.utc)
                
                if end_datetime < current_time:
                    logger.info(f"Рынок завершен по времени: {end_datetime} < {current_time}")
                    return True
                    
            except Exception as e:
                logger.error(f"Ошибка парсинга времени окончания рынка: {e}")

        return False

    async def _close_positions_for_market(self, market_id: str, market_data: Dict) -> None:
        """
        Закрыть все позиции по конкретному рынку.
        
        Args:
            market_id: ID рынка
            market_data: Данные о рынке из API
        """
        try:
            # Получить все позиции по рынку
            market_positions = [
                pos for pos in self.position_storage.get_open_positions()
                if pos.market_id == market_id
            ]
            
            if not market_positions:
                logger.debug(f"Нет открытых позиций для рынка {market_id}")
                return

            logger.info(f"🎯 Закрываем {len(market_positions)} позиций для рынка {market_id}")

            # Определить исход рынка
            outcome = await self._determine_market_outcome(market_id, market_data)
            
            if outcome is None:
                logger.warning(f"Не удалось определить исход рынка {market_id}")
                return

            # Закрыть позиции
            closed_positions = self.position_storage.close_market_positions(
                market_id, outcome, outcome.get("end_price", 0)
            )

            if closed_positions:
                logger.info(f"✅ Закрыто {len(closed_positions)} позиций для рынка {market_id}")
                for pos in closed_positions:
                    logger.info(f"   📝 Закрыта позиция {pos.position_id}: {pos.side} → {outcome.get('outcome', 'UNKNOWN')}, P&L=${pos.pnl_usd:.2f} ({pos.pnl_pct:.2f}%)")
                
                # Очистить кэш для завершенного рынка
                from analysis.price_to_beat_service import PriceToBeatService
                price_to_beat_service = PriceToBeatService(self.price_monitor, self.pm_client)
                price_to_beat_service.clear_market_cache(market_id)
            else:
                logger.warning(f"Не удалось закрыть позиции для рынка {market_id}")

        except Exception as exc:
            logger.error(f"Ошибка при закрытии позиций рынка {market_id}: {exc}")

    async def _determine_market_outcome(self, market_id: str, market_data: Dict) -> Optional[Dict]:
        """
        Определить исход рынка.
        
        Args:
            market_id: ID рынка
            market_data: Данные о рынке из API
            
        Returns:
            Словарь с исходом рынка или None
        """
        try:
            # Получаем price_to_beat из PriceToBeatService
            from analysis.price_to_beat_service import PriceToBeatService
            price_to_beat_service = PriceToBeatService(self.price_monitor, self.pm_client)
            
            price_to_beat = await price_to_beat_service.get_price_to_beat(market_id)
            if not price_to_beat:
                logger.warning(f"Не удалось получить price_to_beat для рынка {market_id}")
                return None

            # Получаем end_price
            end_price = price_to_beat_service.get_end_price(market_id)
            if not end_price or end_price <= 0:
                logger.warning(f"Не удалось получить end_price для рынка {market_id}")
                return None

            # Добавляем подробные логи для диагностики
            logger.info(f"📊 Рынок {market_id}:")
            logger.info(f"   price_to_beat: ${price_to_beat:.4f}")
            logger.info(f"   end_price: ${end_price:.4f}")
            logger.info(f"   Разница: ${end_price - price_to_beat:.4f}")

            # Определяем исход
            outcome = determine_market_outcome(price_to_beat, end_price)
            
            logger.info(f"🏆 Исход рынка {market_id}: {outcome.get('outcome', 'UNKNOWN')} (end_price ${end_price:.2f} {'<' if end_price < price_to_beat else '>='} price_to_beat ${price_to_beat:.2f})")
            
            return outcome

        except Exception as exc:
            logger.error(f"Ошибка при определении исхода рынка {market_id}: {exc}")
            return None

    def get_monitoring_stats(self) -> Dict:
        """
        Получить статистику мониторинга.
        
        Returns:
            Словарь со статистикой
        """
        open_positions = self.position_storage.get_open_positions()
        
        return {
            "is_running": self.is_running,
            "open_positions_count": len(open_positions),
            "markets_being_monitored": len(set(pos.market_id for pos in open_positions)),
            "monitor_interval_minutes": MARKET_MONITOR_INTERVAL,
            "monitored_markets": list(set(pos.market_id for pos in open_positions))
        }