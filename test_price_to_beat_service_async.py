#!/usr/bin/env python3
"""
Тест для проверки асинхронных методов PriceToBeatService.
"""

import asyncio
import logging
from unittest.mock import Mock, AsyncMock

from analysis.price_to_beat_service import PriceToBeatService
from monitoring.price_monitor import PriceMonitor
from polymarket.client import PolymarketClient

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_async_methods():
    """Тест асинхронных методов PriceToBeatService."""
    
    # Создаем моки
    mock_price_monitor = Mock(spec=PriceMonitor)
    mock_pm_client = Mock(spec=PolymarketClient)
    
    # Настраиваем моки
    mock_price_monitor.chainlink_collector = Mock()
    mock_price_monitor.chainlink_collector.get_price_at_time = Mock(return_value=50000.0)
    mock_price_monitor.get_price = Mock(return_value=51000.0)
    mock_price_monitor.get_volatility = Mock(return_value={"15m": 2.5, "1h": 5.0})
    mock_price_monitor.get_stats = Mock(return_value={"atr": 1000.0})
    
    mock_pm_client.get_market_data = Mock(return_value={
        "question": "BTC price at 15:00 UTC",
        "title": "BTC price at 15:00 UTC",
        "createdAt": "2025-01-01T12:00:00Z"
    })
    
    # Настраиваем моки для get_market_start_time и get_market_end_time
    # Возвращаем timestamp напрямую, а не объект datetime
    mock_pm_client.get_market_start_time = Mock(return_value=1735686000.0)
    mock_pm_client.get_market_end_time = Mock(return_value=1735689600.0)
    
    # Создаем сервис
    service = PriceToBeatService(mock_price_monitor, mock_pm_client)
    
    # Тестируем get_symbol()
    print("Тестируем get_symbol()...")
    symbol = await service.get_symbol("test_market_id")
    print(f"Получен символ: {symbol}")
    assert symbol == "BTCUSDT", f"Ожидался BTCUSDT, получено {symbol}"
    
    # Тестируем get_market_duration()
    print("Тестируем get_market_duration()...")
    duration = await service.get_market_duration("test_market_id")
    print(f"Получена продолжительность: {duration}")
    assert duration == "15m", f"Ожидалась 15m, получено {duration}"
    
    # Тестируем get_price_to_beat()
    print("Тестируем get_price_to_beat()...")
    price_to_beat = await service.get_price_to_beat("test_market_id")
    print(f"Получен price_to_beat: {price_to_beat}")
    assert price_to_beat == 50000.0, f"Ожидался 50000.0, получено {price_to_beat}"
    
    # Проверяем кэш
    print("Проверяем кэш...")
    cache_stats = service.get_cache_stats()
    print(f"Статистика кэша: {cache_stats}")
    assert cache_stats["cached_markets"] == 1, "Ожидался 1 закэшированный рынок"
    
    # Проверяем, что данные в кэше
    cached_data = service.cache.get("test_market_id")
    assert cached_data is not None, "Данные не найдены в кэше"
    assert cached_data["symbol"] == "BTCUSDT", "Неверный символ в кэше"
    assert cached_data["market_duration"] == "15m", "Неверная продолжительность в кэше"
    assert cached_data["price_to_beat"] == 50000.0, "Неверный price_to_beat в кэше"
    
    print("✅ Все асинхронные методы работают корректно!")


async def test_fallback_logic():
    """Тест логики fallback при отсутствии данных в коллекторе."""
    
    # Создаем моки
    mock_price_monitor = Mock(spec=PriceMonitor)
    mock_pm_client = Mock(spec=PolymarketClient)
    
    # Настраиваем моки для fallback
    mock_price_monitor.chainlink_collector = Mock()
    mock_price_monitor.chainlink_collector.get_price_at_time = Mock(return_value=None)  # Нет данных в коллекторе
    mock_price_monitor.get_price = Mock(return_value=52000.0)  # Текущая цена для fallback
    mock_price_monitor.get_volatility = Mock(return_value={"15m": 2.5, "1h": 5.0})
    mock_price_monitor.get_stats = Mock(return_value={"atr": 1000.0})
    
    mock_pm_client.get_market_data = Mock(return_value={
        "question": "BTC price at 15:00 UTC",
        "title": "BTC price at 15:00 UTC",
        "createdAt": "2025-01-01T12:00:00Z"
    })
    
    # Создаем сервис
    service = PriceToBeatService(mock_price_monitor, mock_pm_client)
    
    # Тестируем get_price_to_beat() с fallback
    print("Тестируем get_price_to_beat() с fallback...")
    price_to_beat = await service.get_price_to_beat("test_market_id")
    print(f"Получен price_to_beat (fallback): {price_to_beat}")
    assert price_to_beat == 52000.0, f"Ожидался 52000.0 (fallback), получено {price_to_beat}"
    
    # Проверяем, что в кэше сохранены fallback данные
    cached_data = service.cache.get("test_market_id")
    assert cached_data is not None, "Данные не найдены в кэше"
    assert cached_data["price_to_beat"] == 52000.0, "Неверный price_to_beat в кэше (fallback)"
    
    print("✅ Логика fallback работает корректно!")


async def test_error_handling():
    """Тест обработки ошибок."""
    
    # Создаем моки
    mock_price_monitor = Mock(spec=PriceMonitor)
    mock_pm_client = Mock(spec=PolymarketClient)
    
    # Настраиваем моки для ошибки
    mock_price_monitor.chainlink_collector = Mock()
    mock_price_monitor.chainlink_collector.get_price_at_time = Mock(side_effect=Exception("Test error"))
    mock_price_monitor.get_price = Mock(return_value=53000.0)
    mock_price_monitor.get_volatility = Mock(return_value={"15m": 2.5, "1h": 5.0})
    mock_price_monitor.get_stats = Mock(return_value={"atr": 1000.0})
    
    mock_pm_client.get_market_data = Mock(return_value={
        "question": "BTC price at 15:00 UTC",
        "title": "BTC price at 15:00 UTC",
        "createdAt": "2025-01-01T12:00:00Z"
    })
    
    # Создаем сервис
    service = PriceToBeatService(mock_price_monitor, mock_pm_client)
    
    # Тестируем get_price_to_beat() с ошибкой
    print("Тестируем get_price_to_beat() с ошибкой...")
    price_to_beat = await service.get_price_to_beat("test_market_id")
    print(f"Получен price_to_beat (ошибка): {price_to_beat}")
    assert price_to_beat == 53000.0, f"Ожидался 53000.0 (fallback), получено {price_to_beat}"
    
    print("✅ Обработка ошибок работает корректно!")


async def main():
    """Запуск всех тестов."""
    print("🚀 Запуск тестов асинхронных методов PriceToBeatService...")
    
    try:
        await test_async_methods()
        await test_fallback_logic()
        await test_error_handling()
        
        print("\n🎉 Все тесты пройдены успешно!")
        
    except Exception as e:
        print(f"\n❌ Ошибка в тестах: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())