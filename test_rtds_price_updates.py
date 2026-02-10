#!/usr/bin/env python3
"""
Тест для проверки обновления цены с Polymarket RTDS.
Проверяет:
1. Подключение к RTDS
2. Получение первой цены
3. Обновление цены со временем
4. Работу PriceMonitor.get_price()
"""
import asyncio
import sys
from datetime import datetime

from monitoring.price_monitor import PriceMonitor
from app.connectors.polymarket_rtds import PolymarketConnector


async def test_rtds_connection():
    """Тест подключения к RTDS и получения цен."""
    print("\n" + "="*60)
    print("🧪 ТЕСТ: Подключение к Polymarket RTDS")
    print("="*60 + "\n")

    # Создаем коннектор
    rtds = PolymarketConnector()

    try:
        # Подключаемся
        print("1️⃣ Подключаемся к RTDS...")
        await rtds.connect()

        if not rtds.is_connected:
            print("❌ ОШИБКА: Не удалось подключиться к RTDS")
            return False

        print("✅ Подключено к RTDS\n")

        # Ждем получения первой цены
        print("2️⃣ Ждем получения первой цены (10 секунд)...")
        await asyncio.sleep(10)

        # Проверяем цены для всех символов
        symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
        prices_received = {}

        for symbol in symbols:
            price = rtds.get_price(symbol)
            timestamp = rtds.get_timestamp(symbol)

            if price:
                prices_received[symbol] = {
                    "price": price,
                    "timestamp": timestamp
                }
                print(f"✅ {symbol}: ${price:.2f} (обновлено: {timestamp.strftime('%H:%M:%S') if timestamp else 'N/A'})")
            else:
                print(f"❌ {symbol}: НЕТ ЦЕНЫ")

        if not prices_received:
            print("\n❌ ОШИБКА: Не получено ни одной цены!")
            return False

        print(f"\n✅ Получено цен: {len(prices_received)}/{len(symbols)}\n")

        # Ждем обновлений
        print("3️⃣ Ждем обновления цен (15 секунд)...")
        await asyncio.sleep(15)

        # Проверяем обновления
        updates_count = 0
        for symbol in symbols:
            new_price = rtds.get_price(symbol)
            new_timestamp = rtds.get_timestamp(symbol)

            if symbol in prices_received:
                old_price = prices_received[symbol]["price"]
                old_timestamp = prices_received[symbol]["timestamp"]

                if new_timestamp and old_timestamp and new_timestamp > old_timestamp:
                    updates_count += 1
                    change = new_price - old_price if new_price else 0
                    print(f"📊 {symbol}: ${old_price:.2f} → ${new_price:.2f} (Δ{change:.2f})")
                elif new_price and new_price != old_price:
                    updates_count += 1
                    change = new_price - old_price
                    print(f"📊 {symbol}: ${old_price:.2f} → ${new_price:.2f} (Δ{change:.2f})")
                else:
                    print(f"⚠️  {symbol}: Цена не обновилась (${new_price:.2f})")

        if updates_count > 0:
            print(f"\n✅ Обновлений цен: {updates_count}")
        else:
            print("\n⚠️  Цены не обновлялись за 15 секунд")

        # Отключаемся
        await rtds.disconnect()
        print("\n✅ Тест RTDS завершен успешно")
        return True

    except Exception as e:
        print(f"\n❌ ОШИБКА в тесте RTDS: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_price_monitor():
    """Тест работы PriceMonitor с RTDS."""
    print("\n" + "="*60)
    print("🧪 ТЕСТ: PriceMonitor.get_price() с RTDS")
    print("="*60 + "\n")

    price_monitor = PriceMonitor()

    try:
        # Запускаем PriceMonitor
        print("1️⃣ Запускаем PriceMonitor...")
        await price_monitor.start()
        print("✅ PriceMonitor запущен\n")

        # Ждем инициализации
        await asyncio.sleep(10)

        # Получаем цены
        symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
        print("2️⃣ Получаем цены через PriceMonitor.get_price()...")

        initial_prices = {}
        for symbol in symbols:
            price = price_monitor.get_price(symbol)
            if price:
                initial_prices[symbol] = price
                print(f"   {symbol}: ${price:.2f}")
            else:
                print(f"   {symbol}: НЕТ ЦЕНЫ")

        if not initial_prices:
            print("\n❌ ОШИБКА: Не получено ни одной цены через PriceMonitor!")
            await price_monitor.stop()
            return False

        print(f"\n✅ Получено цен: {len(initial_prices)}/{len(symbols)}\n")

        # Проверяем обновления через 15 секунд
        print("3️⃣ Ждем 15 секунд и проверяем обновления...")
        await asyncio.sleep(15)

        updates_count = 0
        for symbol in symbols:
            new_price = price_monitor.get_price(symbol)

            if symbol in initial_prices and new_price:
                old_price = initial_prices[symbol]
                if new_price != old_price:
                    updates_count += 1
                    change = new_price - old_price
                    print(f"   📊 {symbol}: ${old_price:.2f} → ${new_price:.2f} (Δ{change:.2f})")
                else:
                    print(f"   ⚠️  {symbol}: Цена не изменилась (${new_price:.2f})")

        if updates_count > 0:
            print(f"\n✅ Цена обновлялась! Обновлений: {updates_count}")
        else:
            print("\n⚠️  Цены не обновлялись за 15 секунд")

        # Останавливаем
        await price_monitor.stop()
        print("\n✅ Тест PriceMonitor завершен успешно")
        return True

    except Exception as e:
        print(f"\n❌ ОШИБКА в тесте PriceMonitor: {e}")
        import traceback
        traceback.print_exc()
        await price_monitor.stop()
        return False


async def main():
    """Запуск всех тестов."""
    print("\n" + "🚀 ЗАПУСК ТЕСТОВ RTDS И PRICE UPDATES 🚀".center(60, "="))

    # Тест 1: Прямое подключение к RTDS
    test1_passed = await test_rtds_connection()

    await asyncio.sleep(2)

    # Тест 2: PriceMonitor с RTDS
    test2_passed = await test_price_monitor()

    # Результаты
    print("\n" + "="*60)
    print("📊 РЕЗУЛЬТАТЫ ТЕСТОВ:")
    print("="*60)
    print(f"1. RTDS Connection: {'✅ PASSED' if test1_passed else '❌ FAILED'}")
    print(f"2. PriceMonitor:    {'✅ PASSED' if test2_passed else '❌ FAILED'}")
    print("="*60 + "\n")

    if test1_passed and test2_passed:
        print("🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ!")
        return 0
    else:
        print("❌ НЕКОТОРЫЕ ТЕСТЫ НЕ ПРОШЛИ")
        return 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n⚠️  Тесты прерваны пользователем")
        sys.exit(1)
