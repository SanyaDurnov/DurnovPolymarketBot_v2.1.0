#!/usr/bin/env python3
"""
Тест для проверки асинхронных методов PriceToBeatService с реальными примерами названий рынков.
"""

import asyncio
import logging
from unittest.mock import Mock
from datetime import datetime, timezone, timedelta

from analysis.price_to_beat_service import PriceToBeatService

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_real_market_titles():
    """Тест асинхронных методов PriceToBeatService с реальными примерами названий рынков."""
    
    # Создаем моки
    mock_price_monitor = Mock()
    mock_pm_client = Mock()
    
    # Настраиваем моки
    mock_price_monitor.chainlink_collector = Mock()
    mock_price_monitor.chainlink_collector.get_price_at_time = Mock(return_value=50000.0)
    mock_price_monitor.get_price = Mock(return_value=51000.0)
    mock_price_monitor.get_volatility = Mock(return_value={"15m": 2.5, "1h": 5.0})
    mock_price_monitor.get_stats = Mock(return_value={"atr": 1000.0})
    
    # Реальные примеры названий рынков
    market_15m_title = "Bitcoin Up or Down February 7, 8:45AM-9AM ET"
    market_1h_title = "Bitcoin Up or Down February 7, 9AM ET"
    
    # Настраиваем моки для get_market_data
    mock_pm_client.get_market_data = Mock(side_effect=lambda market_id: {
        "test_market_15m": {
            "question": market_15m_title,
            "title": market_15m_title,
            "createdAt": "2025-01-01T12:00:00Z"
        },
        "test_market_1h": {
            "question": market_1h_title,
            "title": market_1h_title,
            "createdAt": "2025-01-01T12:00:00Z"
        }
    }.get(market_id, {}))
    
    # Настраиваем моки для get_market_start_time и get_market_end_time
    # Для 15-минутного рынка: 8:45AM
    start_time_15m = datetime(2025, 2, 7, 8, 45, tzinfo=timezone.utc)
    end_time_15m = start_time_15m + timedelta(minutes=15)
    
    # Для 1-часового рынка: 9:00AM
    start_time_1h = datetime(2025, 2, 7, 9, 0, tzinfo=timezone.utc)
    end_time_1h = start_time_1h + timedelta(hours=1)
    
    mock_pm_client.get_market_start_time = Mock(side_effect=lambda title: {
        market_15m_title: start_time_15m,
        market_1h_title: start_time_1h
    }.get(title, None))
    
    mock_pm_client.get_market_end_time = Mock(side_effect=lambda title: {
        market_15m_title: end_time_15m,
        market_1h_title: end_time_1h
    }.get(title, None))
    
    # Создаем сервис
    service = PriceToBeatService(mock_price_monitor, mock_pm_client)
    
    # Тестируем 15-минутный рынок
    print("Тестируем 15-минутный рынок...")
    symbol_15m = await service.get_symbol("test_market_15m")
    duration_15m = await service.get_market_duration("test_market_15m")
    price_to_beat_15m = await service.get_price_to_beat("test_market_15m")
    
    print(f"15m - Символ: {symbol_15m}")
    print(f"15m - Продолжительность: {duration_15m}")
    print(f"15m - Price_to_beat: {price_to_beat_15m}")
    
    # Проверяем результаты для 15-минутного рынка
    assert symbol_15m == "BTCUSDT", f"Ожидался BTCUSDT, получено {symbol_15m}"
    assert duration_15m == "15m", f"Ожидалась 15m, получено {duration_15m}"
    assert price_to_beat_15m == 50000.0, f"Ожидался 50000.0, получено {price_to_beat_15m}"
    
    # Тестируем 1-часовой рынок
    print("\nТестируем 1-часовой рынок...")
    symbol_1h = await service.get_symbol("test_market_1h")
    duration_1h = await service.get_market_duration("test_market_1h")
    price_to_beat_1h = await service.get_price_to_beat("test_market_1h")
    
    print(f"1h - Символ: {symbol_1h}")
    print(f"1h - Продолжительность: {duration_1h}")
    print(f"1h - Price_to_beat: {price_to_beat_1h}")
    
    # Проверяем результаты для 1-часового рынка
    assert symbol_1h == "BTCUSDT", f"Ожидался BTCUSDT, получено {symbol_1h}"
    assert duration_1h == "1h", f"Ожидалась 1h, получено {duration_1h}"
    assert price_to_beat_1h == 50000.0, f"Ожидался 50000.0, получено {price_to_beat_1h}"
    
    # Проверяем кэш
    print("\nПроверяем кэш...")
    cache_stats = service.get_cache_stats()
    print(f"Статистика кэша: {cache_stats}")
    assert cache_stats["cached_markets"] == 2, "Ожидалось 2 закэшированных рынка"
    
    # Проверяем, что данные в кэше
    cached_data_15m = service.cache.get("test_market_15m")
    cached_data_1h = service.cache.get("test_market_1h")
    
    assert cached_data_15m is not None, "Данные 15m не найдены в кэше"
    assert cached_data_1h is not None, "Данные 1h не найдены в кэше"
    
    assert cached_data_15m["symbol"] == "BTCUSDT", "Неверный символ 15m в кэше"
    assert cached_data_15m["market_duration"] == "15m", "Неверная продолжительность 15m в кэше"
    assert cached_data_1h["symbol"] == "BTCUSDT", "Неверный символ 1h в кэше"
    assert cached_data_1h["market_duration"] == "1h", "Неверная продолжительность 1h в кэше"
    
    print("\n✅ Все асинхронные методы работают корректно с реальными названиями рынков!")


async def main():
    """Запуск теста."""
    print("🚀 Запуск теста PriceToBeatService с реальными названиями рынков...")
    
    try:
        await test_real_market_titles()
        print("\n🎉 Тест пройден успешно!")
        
    except Exception as e:
        print(f"\n❌ Ошибка в тесте: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())