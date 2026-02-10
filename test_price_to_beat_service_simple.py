#!/usr/bin/env python3
"""
Простой тест для проверки асинхронных методов PriceToBeatService.
"""

import asyncio
import logging
from unittest.mock import Mock

from analysis.price_to_beat_service import PriceToBeatService

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_simple():
    """Простой тест асинхронных методов PriceToBeatService."""
    
    # Создаем моки
    mock_price_monitor = Mock()
    mock_pm_client = Mock()
    
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
    mock_pm_client.get_market_start_time = Mock(return_value=1735686000.0)
    mock_pm_client.get_market_end_time = Mock(return_value=1735689600.0)
    
    # Создаем сервис
    service = PriceToBeatService(mock_price_monitor, mock_pm_client)
    
    # Тестируем get_symbol()
    print("Тестируем get_symbol()...")
    symbol = await service.get_symbol("test_market_id")
    print(f"Получен символ: {symbol}")
    
    # Тестируем get_market_duration()
    print("Тестируем get_market_duration()...")
    duration = await service.get_market_duration("test_market_id")
    print(f"Получена продолжительность: {duration}")
    
    # Тестируем get_price_to_beat()
    print("Тестируем get_price_to_beat()...")
    price_to_beat = await service.get_price_to_beat("test_market_id")
    print(f"Получен price_to_beat: {price_to_beat}")
    
    # Проверяем кэш
    print("Проверяем кэш...")
    cache_stats = service.get_cache_stats()
    print(f"Статистика кэша: {cache_stats}")
    
    print("✅ Тест завершен!")


async def main():
    """Запуск теста."""
    print("🚀 Запуск простого теста PriceToBeatService...")
    
    try:
        await test_simple()
        print("\n🎉 Тест пройден успешно!")
        
    except Exception as e:
        print(f"\n❌ Ошибка в тесте: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())