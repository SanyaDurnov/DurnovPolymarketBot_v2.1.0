"""
Polymarket Historical Prices API Connector.

Альтернатива Chainlink - получает исторические цены токенов напрямую из Polymarket API.
Использует /prices-history endpoint для получения timestamp/price pairs.
"""

import asyncio
import logging
import time
from datetime import datetime
from typing import Dict, List, Optional

import aiohttp
import requests

logger = logging.getLogger(__name__)


class PolymarketHistoricalConnector:
    """
    Коннектор для получения исторических цен токенов из Polymarket API.

    Использует endpoint: https://clob.polymarket.com/prices-history
    """

    # Polymarket CLOB API
    API_BASE_URL = "https://clob.polymarket.com"
    PRICES_HISTORY_ENDPOINT = "/prices-history"

    # Кэширование данных
    CACHE_DURATION_MINUTES = 15  # Кэш на 15 минут

    def __init__(self):
        """
        Инициализация Polymarket Historical connector.
        """
        self.session: Optional[aiohttp.ClientSession] = None

        # Кэш для исторических данных: token_id -> {(start_ts, end_ts, resolution): data}
        self.cache: Dict[str, Dict[tuple, List[Dict]]] = {}
        self.cache_timestamps: Dict[str, Dict[tuple, datetime]] = {}

        logger.info("PolymarketHistoricalConnector инициализирован")

    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.disconnect()

    async def connect(self) -> None:
        """Инициализировать HTTP сессию."""
        if self.session is None:
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30)
            )
        logger.info("PolymarketHistoricalConnector подключен")

    async def disconnect(self) -> None:
        """Закрыть HTTP сессию."""
        if self.session:
            await self.session.close()
            self.session = None
        logger.info("PolymarketHistoricalConnector отключен")

    def _get_cache_key(self, start_timestamp: int, end_timestamp: int, resolution: int) -> tuple:
        """Получить ключ кэша для параметров запроса."""
        return (start_timestamp, end_timestamp, resolution)

    def _is_cache_valid(self, token_id: str, cache_key: tuple) -> bool:
        """Проверить, валиден ли кэш."""
        if token_id not in self.cache_timestamps:
            return False

        cache_time = self.cache_timestamps[token_id].get(cache_key)
        if cache_time is None:
            return False

        # Кэш валиден в течение CACHE_DURATION_MINUTES
        return (datetime.now() - cache_time).total_seconds() < (self.CACHE_DURATION_MINUTES * 60)

    def _cache_data(self, token_id: str, cache_key: tuple, data: List[Dict]) -> None:
        """Сохранить данные в кэш."""
        if token_id not in self.cache:
            self.cache[token_id] = {}
            self.cache_timestamps[token_id] = {}

        self.cache[token_id][cache_key] = data
        self.cache_timestamps[token_id][cache_key] = datetime.now()

    def _get_cached_data(self, token_id: str, cache_key: tuple) -> Optional[List[Dict]]:
        """Получить данные из кэша."""
        if not self._is_cache_valid(token_id, cache_key):
            return None
        return self.cache[token_id].get(cache_key)

    async def get_token_price_history(
        self,
        token_id: str,
        start_timestamp: Optional[int] = None,
        end_timestamp: Optional[int] = None,
        resolution_minutes: int = 1,
    ) -> Optional[List[Dict]]:
        """
        Получить исторические цены токена из Polymarket API.

        Args:
            token_id: CLOB token ID (например: "70944558009936417588191677238704740580777628126353344136077216767009576863796")
            start_timestamp: Начальный timestamp (Unix seconds) или None для начала данных
            end_timestamp: Конечный timestamp (Unix seconds) или None для конца данных
            resolution_minutes: Разрешение в минутах (1, 5, 15, 60, etc.)

        Returns:
            Список словарей с ценами:
            [
                {
                    "t": 1640995200,  # timestamp
                    "p": 0.65         # price
                },
                ...
            ]
        """
        cache_key = self._get_cache_key(
            start_timestamp or 0,
            end_timestamp or int(time.time()),
            resolution_minutes
        )

        # Проверяем кэш
        cached_data = self._get_cached_data(token_id, cache_key)
        if cached_data:
            logger.debug("Используем кэшированные данные для token %s", token_id)
            return cached_data

        # Делаем запрос к API
        url = f"{self.API_BASE_URL}{self.PRICES_HISTORY_ENDPOINT}"

        params = {
            "token_id": token_id,
            "resolution": resolution_minutes,
        }

        # Добавляем временные параметры если указаны
        if start_timestamp:
            params["startTs"] = start_timestamp
        if end_timestamp:
            params["endTs"] = end_timestamp

        try:
            if self.session is None:
                await self.connect()

            logger.debug("Запрос к Polymarket API: %s с параметрами %s", url, params)

            async with self.session.get(url, params=params) as response:
                if response.status != 200:
                    logger.error("Polymarket API вернул статус %s: %s",
                               response.status, await response.text())
                    return None

                data = await response.json()
                logger.info("Получено %s записей цен для token %s", len(data), token_id)

                # Кэшируем данные
                self._cache_data(token_id, cache_key, data)
                return data

        except aiohttp.ClientError as exc:
            logger.error("Ошибка HTTP запроса к Polymarket API: %s", exc)
            return None
        except Exception as exc:
            logger.error("Ошибка при получении исторических данных: %s", exc, exc_info=True)
            return None

    async def get_price_at_time(
        self,
        token_id: str,
        timestamp: datetime,
        resolution_minutes: int = 1,
    ) -> Optional[float]:
        """
        Получить цену токена на конкретное время.

        Args:
            token_id: CLOB token ID
            timestamp: Время
            resolution_minutes: Разрешение в минутах

        Returns:
            Цена или None
        """
        ts = int(timestamp.timestamp())

        # Запрашиваем данные за 2 часа вокруг timestamp для надежности
        start_ts = ts - 7200  # -2 часа
        end_ts = ts + 7200    # +2 часа

        prices = await self.get_token_price_history(
            token_id, start_ts, end_ts, resolution_minutes
        )

        if not prices:
            return None

        # Находим ближайшую цену к запрошенному времени
        target_ts = ts
        closest_price = None
        min_diff = float('inf')

        for price_data in prices:
            try:
                price_ts = price_data["t"]
                price = price_data["p"]

                diff = abs(price_ts - target_ts)
                if diff < min_diff:
                    min_diff = diff
                    closest_price = price
            except (KeyError, ValueError) as exc:
                logger.warning("Ошибка обработки price данных: %s", exc)
                continue

        if closest_price is not None and min_diff <= 300:  # Не старше 5 минут
            logger.debug("Найдена цена %.4f для token %s на время %s (разница: %s сек)",
                        closest_price, token_id, timestamp, min_diff)
            return closest_price

        logger.debug("Не найдена подходящая цена для token %s на %s (ближайшая разница: %s сек)",
                    token_id, timestamp, min_diff)
        return None

    def test_connection(self) -> Dict[str, bool]:
        """
        Проверить доступность Polymarket Historical API.

        Returns:
            {
                "api_accessible": bool,
                "sample_data_retrieved": bool
            }
        """
        result = {
            "api_accessible": False,
            "sample_data_retrieved": False,
        }

        try:
            # Проверяем доступность API
            url = f"{self.API_BASE_URL}{self.PRICES_HISTORY_ENDPOINT}"
            response = requests.get(url, timeout=10)
            result["api_accessible"] = response.status_code == 200
        except Exception as exc:
            logger.debug("API недоступен: %s", exc)

        # Пробуем получить тестовые данные
        if result["api_accessible"]:
            try:
                # Синхронный тест для простоты
                # Используем тестовый token_id (нужен реальный)
                test_token = "70944558009936417588191677238704740580777628126353344136077216767009576863796"

                test_data = asyncio.run(self.get_token_price_history(test_token))
                result["sample_data_retrieved"] = test_data is not None and len(test_data) > 0

                if result["sample_data_retrieved"]:
                    logger.info("✅ Polymarket Historical API работает, получено %s тестовых записей", len(test_data))
                else:
                    logger.warning("⚠ Polymarket API доступен, но не вернул тестовые данные")

            except Exception as exc:
                logger.error("Ошибка при тестировании получения данных: %s", exc)

        return result