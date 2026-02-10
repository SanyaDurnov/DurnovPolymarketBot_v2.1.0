#!/usr/bin/env python3
"""
Тест для проверки получения Price to Beat из Chainlink.

Проверяет правильность получения цены на момент открытия рынка.
"""

import asyncio
import unittest
import sys
import os
sys.path.append(os.getcwd())

from analysis.market_analyzer import MarketAnalyzer
from monitoring.price_monitor import PriceMonitor
from polymarket.client import PolymarketClient
from polymarket.orderbook import OrderbookAnalyzer


class TestPriceToBeat(unittest.TestCase):
    """Тесты для получения Price to Beat."""

    def setUp(self):
        """Настройка тестов."""
        # Создаем mock объекты
        self.price_monitor = PriceMonitor()
        self.polymarket_client = PolymarketClient()
        self.orderbook_analyzer = OrderbookAnalyzer(self.polymarket_client)

        # Создаем MarketAnalyzer
        self.market_analyzer = MarketAnalyzer(
            self.price_monitor,
            self.polymarket_client,
            self.orderbook_analyzer
        )

    async def test_get_price_to_beat_for_market(self):
        """Тест получения Price to Beat для реального рынка."""
        # Тестовый market_id (возьмем из логов или известный)
        market_id = "1326048"  # Из логов видно этот ID

        # Получаем данные рынка
        market_data = self.polymarket_client.get_market_data(market_id)
        if not market_data:
            self.skipTest(f"Не удалось получить данные рынка {market_id}")

        # Определяем символ
        title = market_data.get("question", "")
        symbol = self.market_analyzer._infer_symbol(title)
        if not symbol:
            self.skipTest(f"Не удалось определить символ для рынка {market_id}")

        # Получаем текущую цену
        current_price = self.price_monitor.get_price(symbol)
        if not current_price:
            self.skipTest(f"Не удалось получить текущую цену для {symbol}")

        # Получаем временные метрики
        time_metrics = self.market_analyzer._get_time_metrics(title)

        print(f"Тестируем рынок {market_id}:")
        print(f"  Title: {title[:50]}...")
        print(f"  Symbol: {symbol}")
        print(f"  Current price: ${current_price:.2f}")
        print(f"  Time metrics: {time_metrics}")

        # Если start_time не найден, добавим его для теста
        if not time_metrics.get("start_time"):
            from datetime import datetime, timezone, timedelta
            # Добавим start_time за 15 минут до текущего времени
            time_metrics["start_time"] = datetime.now(timezone.utc) - timedelta(minutes=15)
            print(f"  Added start_time for test: {time_metrics['start_time']}")

        # Получаем Price to Beat
        price_to_beat = await self.market_analyzer._get_price_to_beat(
            market_id, symbol, current_price, time_metrics
        )

        print(f"  Price to Beat: ${price_to_beat:.2f}" if price_to_beat else "  Price to Beat: None")

        # Проверки
        if price_to_beat:
            # Price to Beat должен быть разумным (не слишком маленьким/большим)
            self.assertGreater(price_to_beat, 1000, "Price to Beat слишком маленький")
            self.assertLess(price_to_beat, 200000, "Price to Beat слишком большой")

            # Price to Beat должен быть близок к текущей цене (для BTC)
            price_diff_pct = abs(price_to_beat - current_price) / current_price
            self.assertLess(price_diff_pct, 0.5, f"Price to Beat отличается от текущей цены более чем на 50%: {price_diff_pct:.1%}")

            print(f"  ✓ Price to Beat в разумных пределах")
        else:
            self.fail("Price to Beat не получен")

    async def test_price_to_beat_cache(self):
        """Тест кэширования Price to Beat."""
        market_id = "1326048"
        symbol = "BTCUSDT"
        current_price = 75000.0

        # Очищаем кэш
        self.market_analyzer.price_to_beat_cache.clear()

        # Первый вызов
        time_metrics = {"minutes_since_open": 10, "start_time": None}
        price1 = await self.market_analyzer._get_price_to_beat(
            market_id, symbol, current_price, time_metrics
        )

        # Второй вызов (должен взять из кэша)
        price2 = await self.market_analyzer._get_price_to_beat(
            market_id, symbol, current_price, time_metrics
        )

        # Проверяем что значения одинаковые
        self.assertEqual(price1, price2, "Кэширование не работает")

        # Проверяем что в кэше есть значение
        self.assertIn(market_id, self.market_analyzer.price_to_beat_cache)

        print(f"Кэш работает: {price1} == {price2}")

    def test_infer_symbol(self):
        """Тест определения символа из названия."""
        test_cases = [
            ("Will Bitcoin be above $100,000 on January 1st?", "BTCUSDT"),
            ("Will Ethereum reach $5,000 this month?", "ETHUSDT"),
            ("Will Solana hit $200 in Q1?", "SOLUSDT"),
            ("Some other market", None),
        ]

        for title, expected in test_cases:
            result = self.market_analyzer._infer_symbol(title)
            self.assertEqual(result, expected, f"Для '{title}' ожидался {expected}, получен {result}")

    async def async_test_get_price_to_beat(self):
        """Асинхронный тест получения Price to Beat."""
        await self.test_get_price_to_beat_for_market()
        await self.test_price_to_beat_cache()

    def test_get_price_to_beat(self):
        """Основной тест."""
        asyncio.run(self.async_test_get_price_to_beat())


if __name__ == '__main__':
    unittest.main()