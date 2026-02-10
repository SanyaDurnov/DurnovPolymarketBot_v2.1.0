#!/usr/bin/env python3
"""
Тест Chainlink Historical API интеграции.
"""

import asyncio
import logging
import sys
from datetime import datetime

# Настраиваем logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Добавляем текущую директорию в путь
sys.path.insert(0, '.')

from monitoring.price_monitor import PriceMonitor


async def test_chainlink():
    """Тестировать Chainlink интеграцию."""
    print("🚀 Тестирование Chainlink Historical API интеграции")
    print("=" * 60)

    # Создаем PriceMonitor
    monitor = PriceMonitor()

    try:
        # Меняем источник данных на Chainlink для тестирования
        from app.config import settings
        original_source = settings.data_source
        settings.data_source = "chainlink"

        print(f"📊 Текущий источник данных: {settings.data_source}")
        print(f"🔗 Chainlink RPC URL: {settings.chainlink_rpc_url}")

        # Запускаем монитор
        print("🔄 Запуск PriceMonitor...")
        await monitor.start()

        # Ждем инициализации
        await asyncio.sleep(5)

        # Тестируем интеграцию
        print("🧪 Тестирование Chainlink интеграции...")
        test_result = monitor.test_chainlink_integration()

        print("\n📋 Результаты тестирования:")
        print(f"  ✅ Chainlink доступен: {test_result['chainlink_available']}")

        if test_result['historical_api_status']:
            api_status = test_result['historical_api_status']
            print(f"  🌐 API доступен: {api_status.get('api_accessible', False)}")
            print(f"  📦 Контракты: {api_status.get('contracts_available', False)}")
            print(f"  📈 Данные получены: {api_status.get('sample_data_retrieved', False)}")

        if test_result['kline_provider_status']:
            kline_status = test_result['kline_provider_status']
            print(f"  📊 Данные доступны: {kline_status.get('data_available', False)}")
            print(f"  ⏱️  Частота обновлений: {kline_status.get('avg_update_frequency', 0):.1f} сек")
            print(f"  📈 Качество данных: {kline_status.get('quality_score', 0):.2f}")

        print(f"  💾 Данные загружены: {test_result['sample_data_loaded']}")
        print(f"  📈 Индикаторы рассчитаны: {test_result['indicators_calculated']}")

        # Тестируем получение статистики
        print("\n📊 Тестирование индикаторов для BTCUSDT...")
        stats = monitor.get_stats("BTCUSDT")
        if stats:
            print(f"  💰 Цена: ${stats.get('price', 0):.2f}")
            print(f"  📊 RSI: {stats.get('rsi_14', 'N/A')}")
            print(f"  📊 MACD: {stats.get('macd', {}).get('macd', 'N/A')}")
            print(f"  📊 ATR: {stats.get('atr', 'N/A')}")
            print(f"  📊 Волатильность: {stats.get('volatility', {})}")
        else:
            print("  ❌ Не удалось получить статистику")

        # Останавливаем монитор
        print("\n🔄 Остановка PriceMonitor...")
        await monitor.stop()

        # Восстанавливаем оригинальный источник
        settings.data_source = original_source

        print("\n✅ Тестирование завершено!")

    except Exception as exc:
        print(f"❌ Ошибка при тестировании: {exc}")
        import traceback
        traceback.print_exc()

