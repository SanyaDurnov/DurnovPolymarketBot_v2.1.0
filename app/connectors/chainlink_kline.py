"""
Chainlink Kline Provider - создает OHLC свечи из исторических данных Chainlink.

Преобразует исторические price rounds в свечи разных таймфреймов.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import pandas as pd

from app.connectors.chainlink_historical import ChainlinkHistoricalConnector

logger = logging.getLogger(__name__)


class ChainlinkKlineProvider:
    """
    Провайдер свечей на основе Chainlink исторических данных.

    Создает OHLC свечи из исторических price rounds.
    """

    def __init__(self, historical_connector: Optional[ChainlinkHistoricalConnector] = None):
        """
        Инициализация провайдера свечей.

        Args:
            historical_connector: Экземпляр ChainlinkHistoricalConnector
        """
        self.historical_connector = historical_connector or ChainlinkHistoricalConnector()
        logger.info("ChainlinkKlineProvider инициализирован")

    async def get_historical_klines(
        self,
        symbol: str,
        interval: str = "1m",
        limit: int = 100,
    ) -> List[Dict]:
        """
        Получить исторические свечи для символа.

        Args:
            symbol: Символ (BTCUSDT, ETHUSDT, SOLUSDT)
            interval: Интервал свечи ("1m", "5m", "15m", "1h")
            limit: Количество свечей

        Returns:
            Список свечей в формате Binance:
            [
                {
                    "timestamp": datetime,
                    "open": float,
                    "high": float,
                    "low": float,
                    "close": float,
                    "volume": float,  # Заглушка, Chainlink не предоставляет volume
                },
                ...
            ]
        """
        # Определяем период для запроса данных
        end_ts = int(datetime.now().timestamp())
        interval_seconds = self._interval_to_seconds(interval)
        total_seconds = limit * interval_seconds
        start_ts = end_ts - total_seconds

        # Получаем исторические цены
        prices_data = await self.historical_connector.get_historical_prices(
            symbol, start_ts, end_ts
        )

        if not prices_data:
            logger.warning("Нет исторических данных для %s", symbol)
            return []

        # Конвертируем в DataFrame
        df = pd.DataFrame(prices_data)
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s")
        df = df.set_index("timestamp")
        df = df.sort_index()

        # Ресамплируем в нужный таймфрейм
        klines_df = self._resample_prices_to_klines(df, interval)

        if klines_df.empty:
            logger.warning("Не удалось создать свечи для %s", symbol)
            return []

        # Конвертируем обратно в список словарей
        klines = []
        for timestamp, row in klines_df.iterrows():
            klines.append({
                "timestamp": timestamp.to_pydatetime(),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row.get("volume", 0)),  # Chainlink не предоставляет volume
            })

        # Берем последние N свечей
        klines = klines[-limit:] if len(klines) > limit else klines

        logger.info("Создано %s свечей %s для %s", len(klines), interval, symbol)
        return klines

    def _interval_to_seconds(self, interval: str) -> int:
        """Конвертировать интервал в секунды."""
        interval = interval.lower()

        if interval == "1m":
            return 60
        elif interval == "5m":
            return 300
        elif interval == "15m":
            return 900
        elif interval == "1h":
            return 3600
        else:
            logger.warning("Неизвестный интервал %s, используем 1m", interval)
            return 60

    def _resample_prices_to_klines(self, df: pd.DataFrame, interval: str) -> pd.DataFrame:
        """
        Ресамплировать цены в OHLC свечи.

        Args:
            df: DataFrame с колонкой 'price' и timestamp индексом
            interval: Интервал ("1m", "5m", "15m", "1h")

        Returns:
            DataFrame со свечами (open, high, low, close)
        """
        if df.empty or "price" not in df.columns:
            return pd.DataFrame()

        # Создаем OHLC из цены (поскольку у нас только одна цена на round)
        # Для каждого интервала берем:
        # - open: первая цена в интервале
        # - high: максимальная цена в интервале
        # - low: минимальная цена в интервале
        # - close: последняя цена в интервале

        # Группируем по интервалам
        if interval == "1m":
            freq = "1min"
        elif interval == "5m":
            freq = "5min"
        elif interval == "15m":
            freq = "15min"
        elif interval == "1h":
            freq = "1h"
        else:
            freq = "1min"

        try:
            # Ресамплируем
            resampled = df.resample(freq).agg({
                "price": ["first", "max", "min", "last"]
            })

            # Убираем мультииндекс колонок
            resampled.columns = ["open", "high", "low", "close"]

            # Удаляем NaN значения
            resampled = resampled.dropna()

            return resampled

        except Exception as exc:
            logger.error("Ошибка при ресамплинге свечей: %s", exc)
            return pd.DataFrame()

    async def get_price_at_time(
        self,
        symbol: str,
        timestamp: datetime,
        interval: str = "1m",
    ) -> Optional[float]:
        """
        Получить цену close для свечи, содержащей timestamp.

        Args:
            symbol: Символ
            timestamp: Время
            interval: Интервал свечи

        Returns:
            Цена close или None
        """
        # Получаем свечи за период вокруг timestamp
        interval_seconds = self._interval_to_seconds(interval)
        start_time = timestamp - timedelta(seconds=interval_seconds * 10)  # 10 свечей назад
        end_time = timestamp + timedelta(seconds=interval_seconds * 10)    # 10 свечей вперед

        klines = await self.get_historical_klines(
            symbol,
            interval,
            limit=20  # Достаточно для поиска
        )

        if not klines:
            return None

        # Находим свечу, которая содержит timestamp
        target_ts = timestamp
        for kline in klines:
            kline_start = kline["timestamp"]
            kline_end = kline_start + timedelta(seconds=interval_seconds)

            if kline_start <= target_ts < kline_end:
                return kline["close"]

        logger.debug("Не найдена свеча для %s на %s", symbol, timestamp)
        return None

    async def create_1m_dataframe(self, symbol: str, hours_back: int = 24) -> Optional[pd.DataFrame]:
        """
        Создать DataFrame с 1m свечами для расчетов индикаторов.

        Args:
            symbol: Символ
            hours_back: Сколько часов исторических данных получить

        Returns:
            DataFrame с колонками: timestamp, open, high, low, close, volume
        """
        # Получаем свечи
        limit = hours_back * 60  # Количество 1m свечей
        klines = await self.get_historical_klines(symbol, "1m", limit)

        if not klines:
            return None

        # Конвертируем в DataFrame
        df = pd.DataFrame(klines)
        df = df.set_index("timestamp")

        # Переименовываем колонки для совместимости с индикаторами
        df = df.rename(columns={
            "open": "open",
            "high": "high",
            "low": "low",
            "close": "close",
            "volume": "volume"
        })

        logger.info("Создан DataFrame с %s 1m свечами для %s", len(df), symbol)
        return df

    def test_data_quality(self, symbol: str = "BTCUSDT") -> Dict[str, any]:
        """
        Проверить качество данных Chainlink для создания свечей.

        Returns:
            {
                "data_available": bool,
                "recent_updates": int,  # Количество обновлений за последний час
                "avg_update_frequency": float,  # Средняя частота обновлений (сек)
                "data_gaps": int,  # Количество пропусков данных
                "quality_score": float,  # Оценка качества (0-1)
            }
        """
        result = {
            "data_available": False,
            "recent_updates": 0,
            "avg_update_frequency": 0.0,
            "data_gaps": 0,
            "quality_score": 0.0,
        }

        try:
            # Получаем данные за последний час
            end_ts = int(datetime.now().timestamp())
            start_ts = end_ts - 3600  # 1 час

            prices_data = asyncio.run(
                self.historical_connector.get_historical_prices(symbol, start_ts, end_ts)
            )

            if not prices_data:
                return result

            result["data_available"] = True
            result["recent_updates"] = len(prices_data)

            if len(prices_data) > 1:
                # Считаем среднюю частоту обновлений
                timestamps = [p["timestamp"] for p in prices_data]
                timestamps.sort()

                intervals = []
                for i in range(1, len(timestamps)):
                    intervals.append(timestamps[i] - timestamps[i-1])

                if intervals:
                    avg_interval = sum(intervals) / len(intervals)
                    result["avg_update_frequency"] = avg_interval

                    # Проверяем на пропуски (интервалы > 5 минут = пропуск)
                    gaps = sum(1 for interval in intervals if interval > 300)
                    result["data_gaps"] = gaps

                    # Оценка качества: меньше пропусков = выше качество
                    gap_penalty = min(gaps * 0.1, 1.0)  # Каждый пропуск снижает на 10%
                    frequency_bonus = min(avg_interval / 60, 1.0)  # Чем чаще обновления, тем лучше
                    result["quality_score"] = max(0, frequency_bonus - gap_penalty)

            logger.info("Качество данных Chainlink для %s: %s", symbol, result)

        except Exception as exc:
            logger.error("Ошибка при проверке качества данных: %s", exc)

        return result