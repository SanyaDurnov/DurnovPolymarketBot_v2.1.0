#!/usr/bin/env python3
"""
Test script for Chainlink Price Collector.

Тестирует функциональность сбора цен из Chainlink.
Запуск: python3 test_chainlink_collector.py
"""

import asyncio
import sys
import time
from datetime import datetime

# Добавляем корневую директорию в путь
sys.path.insert(0, '/Users/sanyadurnov/Documents/Polymarket_bot_V2')

from app.connectors.chainlink_price_collector import ChainlinkPriceCollector


async def test_get_current_prices():
    """Тестируем получение текущих цен из Chainlink."""
    print("🧪 Тестирование получения текущих цен из Chainlink...")

    collector = ChainlinkPriceCollector()

    try:
        await collector.connect()

        print("Получаем цены для BTC, ETH, SOL...")

        # Тестируем получение цен
        btc_price = await collector._get_current_price('BTCUSDT')
        eth_price = await collector._get_current_price('ETHUSDT')
        sol_price = await collector._get_current_price('SOLUSDT')

        print("Результаты:")
        print(f"  BTC: ${btc_price:.2f}" if btc_price else "  BTC: None")
        print(f"  ETH: ${eth_price:.2f}" if eth_price else "  ETH: None")
        print(f"  SOL: ${sol_price:.2f}" if sol_price else "  SOL: None")

        success = all([btc_price, eth_price, sol_price])
        print(f"✅ Тест пройден!" if success else "❌ Тест не пройден")

        return success

    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False
    finally:
        await collector.disconnect()


async def test_collect_prices():
    """Тестируем сбор цен в буферы."""
    print("\n🧪 Тестирование сбора цен в буферы...")

    collector = ChainlinkPriceCollector()

    try:
        await collector.connect()

        print("Собираем цены...")
        await collector._collect_prices()

        print("Проверяем буферы:")
        for symbol in ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']:
            buffer_len = len(collector.price_buffers[symbol])
            print(f"  {symbol}: {buffer_len} записей")

            if buffer_len > 0:
                last_entry = collector.price_buffers[symbol][-1]
                price = last_entry['price']
                timestamp = last_entry['timestamp']
                dt = datetime.fromtimestamp(timestamp)
                print(f"    Последняя цена: ${price:.2f} в {dt.strftime('%H:%M:%S')}")

        total_entries = sum(len(collector.price_buffers[symbol]) for symbol in collector.price_buffers)
        print(f"Всего собрано: {total_entries} записей")

        success = total_entries > 0
        print(f"✅ Тест пройден!" if success else "❌ Тест не пройден")

        return success

    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False
    finally:
        await collector.disconnect()


async def test_save_and_load():
    """Тестируем сохранение и загрузку данных."""
    print("\n🧪 Тестирование сохранения и загрузки данных...")

    collector = ChainlinkPriceCollector()

    try:
        await collector.connect()

        # Собираем данные
        print("Собираем данные...")
        await collector._collect_prices()

        # Сохраняем
        print("Сохраняем данные...")
        collector._save_data()

        # Проверяем файл
        import os
        if os.path.exists('data/chainlink_btc_prices.json'):
            file_size = os.path.getsize('data/chainlink_btc_prices.json')
            print(f"✅ Файл создан! Размер: {file_size} байт")

            # Создаем новый коллектор и загружаем данные
            print("Загружаем данные в новый экземпляр...")
            new_collector = ChainlinkPriceCollector()

            total_loaded = sum(len(new_collector.price_buffers[symbol]) for symbol in new_collector.price_buffers)
            print(f"Загружено записей: {total_loaded}")

            success = total_loaded > 0
            print(f"✅ Тест пройден!" if success else "❌ Тест не пройден")

            return success
        else:
            print("❌ Файл не создан")
            return False

    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False
    finally:
        await collector.disconnect()


async def test_get_price_at_time():
    """Тестируем получение цены на конкретное время."""
    print("\n🧪 Тестирование получения цены по времени...")

    collector = ChainlinkPriceCollector()

    try:
        await collector.connect()

        # Собираем данные
        await collector._collect_prices()

        # Тестируем получение цены минуту назад
        one_minute_ago = int(time.time()) - 60
        print(f"Получаем цены на timestamp {one_minute_ago} (минуту назад):")

        for symbol in ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']:
            price = collector.get_price_at_time(symbol, one_minute_ago)
            if price:
                print(f"  {symbol}: ${price:.2f}")
            else:
                print(f"  {symbol}: цена не найдена")

        # Тестируем получение цены сейчас
        now = int(time.time())
        print(f"\nПолучаем цены на timestamp {now} (сейчас):")

        for symbol in ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']:
            price = collector.get_price_at_time(symbol, now)
            if price:
                print(f"  {symbol}: ${price:.2f}")
            else:
                print(f"  {symbol}: цена не найдена")

        print("✅ Тест завершен")
        return True

    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False
    finally:
        await collector.disconnect()


async def main():
    """Основная функция тестирования."""
    print("🚀 Запуск комплексного тестирования Chainlink Price Collector")
    print("=" * 60)

    tests = [
        ("Получение текущих цен", test_get_current_prices),
        ("Сбор цен в буферы", test_collect_prices),
        ("Сохранение и загрузка", test_save_and_load),
        ("Получение цены по времени", test_get_price_at_time),
    ]

    results = []
    for test_name, test_func in tests:
        print(f"\n{'='*20} {test_name} {'='*20}")
        try:
            result = await test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ Критическая ошибка в тесте '{test_name}': {e}")
            results.append((test_name, False))

    # Итоги
    print("\n" + "=" * 60)
    print("📊 ИТОГИ ТЕСТИРОВАНИЯ:")
    print("=" * 60)

    passed = 0
    total = len(results)

    for test_name, result in results:
        status = "✅ ПРОЙДЕН" if result else "❌ НЕ ПРОЙДЕН"
        print(f"  {test_name}: {status}")
        if result:
            passed += 1

    print(f"\n🎯 Результат: {passed}/{total} тестов пройдено")

    if passed == total:
        print("🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ! Chainlink Price Collector работает корректно.")
    else:
        print("⚠️  Некоторые тесты не пройдены. Проверьте логи выше.")

    print("=" * 60)


if __name__ == "__main__":
    # Запуск тестирования
    asyncio.run(main())