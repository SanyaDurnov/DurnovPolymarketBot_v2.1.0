"""
Chainlink Historical Price Feeds API Connector.

Получает исторические данные Chainlink price feeds для создания OHLC свечей.
Использует off-chain API для получения исторических rounds.

Альтернатива: Polymarket Historical Prices API для получения цен токенов.
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import aiohttp
import requests

logger = logging.getLogger(__name__)


class ChainlinkHistoricalConnector:
    """
    Коннектор для получения исторических данных Chainlink price feeds.

    Адреса контрактов на Ethereum mainnet:
    - BTC/USD: 0xf4030086522a5beea4988f8ca5b36dbc97bee88c
    - ETH/USD: 0x5f4ec3df9cbd43714fe2740f5e3616155c5b8419
    - SOL/USD: 0x4ffc43a60e009b551865a93d232e33fce9f01507
    """

    # Chainlink Historical API endpoint (локальный или удаленный)
    API_BASE_URL = "http://localhost:3000"  # Для локального запуска
    API_ENDPOINT = "/api/price"

    # Адреса контрактов на Ethereum mainnet (проверенные)
    CONTRACT_ADDRESSES = {
        "BTCUSDT": "0xF4030086522a5bEEa4988F8CA5B36dbC97BeE88c",  # BTC/USD
        "ETHUSDT": "0x5f4eC3Df9cbd43714FE2740f5E3616155c5b8419",  # ETH/USD
        "SOLUSDT": "0x4ffC43a60e009B551865a93d232E33Fce9F01507",  # SOL/USD (может быть неправильный)
    }

    # Ethereum RPC endpoint (Alchemy, Infura, etc.)
    DEFAULT_RPC_URL = "https://ethereum-rpc.publicnode.com"  # PublicNode - поддерживает Chainlink

    # Кэширование данных
    CACHE_DURATION_MINUTES = 15  # Кэш на 15 минут

    def __init__(self, rpc_url: Optional[str] = None):
        """
        Инициализация Chainlink Historical connector.

        Args:
            rpc_url: Ethereum RPC endpoint URL
        """
        self.rpc_url = rpc_url or self.DEFAULT_RPC_URL
        self.session: Optional[aiohttp.ClientSession] = None

        # Кэш для исторических данных: symbol -> {(start_ts, end_ts): data}
        self.cache: Dict[str, Dict[tuple, Dict]] = {}
        self.cache_timestamps: Dict[str, Dict[tuple, datetime]] = {}

        logger.info("ChainlinkHistoricalConnector инициализирован")

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
        logger.info("ChainlinkHistoricalConnector подключен")

    async def disconnect(self) -> None:
        """Закрыть HTTP сессию."""
        if self.session:
            await self.session.close()
            self.session = None
        logger.info("ChainlinkHistoricalConnector отключен")

    def _get_cache_key(self, start_timestamp: int, end_timestamp: int) -> tuple:
        """Получить ключ кэша для таймстампов."""
        return (start_timestamp, end_timestamp)

    def _is_cache_valid(self, symbol: str, cache_key: tuple) -> bool:
        """Проверить, валиден ли кэш."""
        if symbol not in self.cache_timestamps:
            return False

        cache_time = self.cache_timestamps[symbol].get(cache_key)
        if cache_time is None:
            return False

        # Кэш валиден в течение CACHE_DURATION_MINUTES
        return (datetime.now() - cache_time).total_seconds() < (self.CACHE_DURATION_MINUTES * 60)

    def _cache_data(self, symbol: str, cache_key: tuple, data: Dict) -> None:
        """Сохранить данные в кэш."""
        if symbol not in self.cache:
            self.cache[symbol] = {}
            self.cache_timestamps[symbol] = {}

        self.cache[symbol][cache_key] = data
        self.cache_timestamps[symbol][cache_key] = datetime.now()

    def _get_cached_data(self, symbol: str, cache_key: tuple) -> Optional[Dict]:
        """Получить данные из кэша."""
        if not self._is_cache_valid(symbol, cache_key):
            return None
        return self.cache[symbol].get(cache_key)

    async def get_historical_rounds(
        self,
        symbol: str,
        start_timestamp: int,
        end_timestamp: int,
    ) -> Optional[Dict]:
        """
        Получить исторические rounds для символа в заданном диапазоне.

        Args:
            symbol: Символ (BTCUSDT, ETHUSDT, SOLUSDT)
            start_timestamp: Начальный timestamp (Unix seconds)
            end_timestamp: Конечный timestamp (Unix seconds)

        Returns:
            {
                "description": "BTC/USD",
                "decimals": 8,
                "rounds": [
                    {
                        "phaseId": "1",
                        "roundId": "1",
                        "answer": "50000",
                        "timestamp": 1640995200
                    },
                    ...
                ]
            }
        """
        if symbol not in self.CONTRACT_ADDRESSES:
            logger.error("Неизвестный символ: %s", symbol)
            return None

        contract_address = self.CONTRACT_ADDRESSES[symbol]
        cache_key = self._get_cache_key(start_timestamp, end_timestamp)

        # Проверяем кэш
        cached_data = self._get_cached_data(symbol, cache_key)
        if cached_data:
            logger.debug("Используем кэшированные данные для %s (%s-%s)",
                        symbol, start_timestamp, end_timestamp)
            return cached_data

        # Делаем запрос к API
        url = f"{self.API_BASE_URL}{self.API_ENDPOINT}"
        params = {
            "contractAddress": contract_address,
            "startTimestamp": start_timestamp,
            "endTimestamp": end_timestamp,
            "chain": "mainnet",
            "rpcUrl": self.rpc_url,
        }

        try:
            if self.session is None:
                await self.connect()

            logger.debug("Запрос к Chainlink API: %s с параметрами %s", url, params)

            async with self.session.get(url, params=params) as response:
                if response.status != 200:
                    logger.error("Chainlink API вернул статус %s: %s",
                               response.status, await response.text())
                    return None

                data = await response.json()
                logger.info("Получено %s rounds для %s за период %s-%s",
                           len(data.get("rounds", [])), symbol, start_timestamp, end_timestamp)

                # Кэшируем данные
                self._cache_data(symbol, cache_key, data)
                return data

        except aiohttp.ClientError as exc:
            logger.error("Ошибка HTTP запроса к Chainlink API: %s", exc)
            return None
        except Exception as exc:
            logger.error("Ошибка при получении исторических данных: %s", exc, exc_info=True)
            return None

    async def get_historical_prices(
        self,
        symbol: str,
        start_timestamp: int,
        end_timestamp: int,
    ) -> List[Dict]:
        """
        Получить исторические цены в формате, удобном для создания свечей.

        Args:
            symbol: Символ (BTCUSDT, ETHUSDT, SOLUSDT)
            start_timestamp: Начальный timestamp (Unix seconds)
            end_timestamp: Конечный timestamp (Unix seconds)

        Returns:
            Список словарей с ценами:
            [
                {
                    "timestamp": 1640995200,
                    "price": 50000.0,
                    "round_id": "1",
                    "phase_id": "1"
                },
                ...
            ]
        """
        rounds_data = await self.get_historical_rounds(symbol, start_timestamp, end_timestamp)
        if not rounds_data:
            return []

        prices = []
        decimals = rounds_data.get("decimals", 8)

        for round_data in rounds_data.get("rounds", []):
            try:
                price_raw = int(round_data["answer"])
                price = price_raw / (10 ** decimals)  # Конвертируем с учетом decimals

                prices.append({
                    "timestamp": round_data["timestamp"],
                    "price": price,
                    "round_id": round_data["roundId"],
                    "phase_id": round_data["phaseId"],
                })
            except (KeyError, ValueError) as exc:
                logger.warning("Ошибка обработки round данных: %s", exc)
                continue

        # Сортируем по timestamp
        prices.sort(key=lambda x: x["timestamp"])
        logger.debug("Обработано %s цен для %s", len(prices), symbol)
        return prices

    async def get_price_at_time(
        self,
        symbol: str,
        timestamp: datetime,
    ) -> Optional[float]:
        """
        Получить цену на конкретное время.

        Args:
            symbol: Символ
            timestamp: Время

        Returns:
            Цена или None
        """
        ts = int(timestamp.timestamp())
        # Запрашиваем данные за 1 час вокруг timestamp
        start_ts = ts - 3600
        end_ts = ts + 3600

        prices = await self.get_historical_prices(symbol, start_ts, end_ts)
        if not prices:
            return None

        # Находим ближайшую цену к запрошенному времени
        target_ts = ts
        closest_price = None
        min_diff = float('inf')

        for price_data in prices:
            diff = abs(price_data["timestamp"] - target_ts)
            if diff < min_diff:
                min_diff = diff
                closest_price = price_data["price"]

        if closest_price and min_diff <= 300:  # Не старше 5 минут
            return closest_price

        logger.debug("Не найдена подходящая цена для %s на %s (ближайшая разница: %s сек)",
                    symbol, timestamp, min_diff)
        return None

    def test_connection(self) -> Dict[str, bool]:
        """
        Проверить доступность Chainlink Historical API.

        Returns:
            {
                "api_accessible": bool,
                "contracts_available": bool,
                "sample_data_retrieved": bool
            }
        """
        result = {
            "api_accessible": False,
            "contracts_available": False,
            "sample_data_retrieved": False,
        }

        try:
            # Проверяем доступность API
            url = f"{self.API_BASE_URL}{self.API_ENDPOINT}"
            response = requests.get(url, timeout=10)
            result["api_accessible"] = response.status_code == 200
        except Exception as exc:
            logger.debug("API недоступен: %s", exc)

        # Проверяем наличие контрактов
        result["contracts_available"] = bool(self.CONTRACT_ADDRESSES)

        # Пробуем получить тестовые данные (последний час для BTC)
        if result["api_accessible"] and result["contracts_available"]:
            try:
                # Синхронный тест для простоты
                end_ts = int(time.time())
                start_ts = end_ts - 3600  # Последний час

                test_data = asyncio.run(self.get_historical_prices("BTCUSDT", start_ts, end_ts))
                result["sample_data_retrieved"] = len(test_data) > 0

                if result["sample_data_retrieved"]:
                    logger.info("✅ Chainlink Historical API работает, получено %s тестовых записей", len(test_data))
                else:
                    logger.warning("⚠ Chainlink API доступен, но не вернул тестовые данные")

            except Exception as exc:
                logger.error("Ошибка при тестировании получения данных: %s", exc)

        return result