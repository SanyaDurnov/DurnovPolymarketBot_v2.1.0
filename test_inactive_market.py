#!/usr/bin/env python3
"""
Тест для проверки обработки неактивных рынков.
"""

import asyncio
import logging
from polymarket.client import PolymarketClient
from polymarket.orderbook import OrderbookAnalyzer
from analysis.market_analyzer import MarketAnalyzer
from monitoring.price_monitor import PriceMonitor

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_inactive_market():
    """Тестируем обработку неактивного рынка 1320780."""
    print("🚀 Запуск теста неактивного рынка...")

    try:
        # Создаем компоненты
        pm_client = PolymarketClient()
        orderbook_analyzer = OrderbookAnalyzer(pm_client)

        # Создаем price_monitor
        price_monitor = PriceMonitor()
        await price_monitor.start()

        market_analyzer = MarketAnalyzer(price_monitor, pm_client, orderbook_analyzer)

        # Тестируем анализ неактивного рынка
        print("📊 Тестируем анализ рынка 1320780...")
        result = await market_analyzer.analyze_market('1320780')

        print(f"✅ Результат: {result['status'] if result else 'None'}")
        print(f"📈 Количество активных рынков: {len(orderbook_analyzer.active_markets)}")

        if result and result['status'] == 'inactive':
            print("✅ Тест пройден: неактивный рынок обработан правильно")
        else:
            print("❌ Тест провален: рынок должен быть неактивным")

        # Останавливаем price_monitor
        await price_monitor.stop()

    except Exception as exc:
        print(f"❌ Ошибка при тестировании: {exc}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_inactive_market())