#!/usr/bin/env python3
"""
Тест для проверки застывания цен RTDS.
Проверяет, обновляются ли цены регулярно или застывают на одном значении.
"""
import asyncio
import sys
from datetime import datetime
from monitoring.price_monitor import PriceMonitor

async def test_rtds_staleness():
    """Тест для проверки застывания цен RTDS."""
    print("=" * 70)
    print("🧪 ТЕСТ: Проверка застывания цен RTDS")
    print("=" * 70 + "\n")

    price_monitor = PriceMonitor()

    try:
        print("1️⃣ Запуск PriceMonitor...")
        await price_monitor.start()
        print("✅ PriceMonitor запущен\n")

        # Ждем первых цен
        await asyncio.sleep(10)

        symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

        # Мониторим цены в течение 3 минут
        print("2️⃣ Мониторинг цен в течение 3 минут (проверка каждые 5 секунд)...\n")

        price_history = {sym: [] for sym in symbols}
        stale_detected = {sym: False for sym in symbols}

        for i in range(36):  # 36 * 5 = 180 секунд = 3 минуты
            timestamp = datetime.now().strftime("%H:%M:%S")

            for symbol in symbols:
                price = price_monitor.get_price(symbol)
                if price:
                    price_history[symbol].append((timestamp, price))

                    # Проверяем, не застыла ли цена
                    if len(price_history[symbol]) >= 6:  # За последние 30 секунд (6 * 5 сек)
                        last_6 = [p for _, p in price_history[symbol][-6:]]
                        if len(set(last_6)) == 1:  # Все цены одинаковые
                            if not stale_detected[symbol]:
                                stale_detected[symbol] = True
                                print(f"⚠️  {timestamp} | {symbol}: ЦЕНА ЗАСТЫЛА на ${price:.2f} (последние 30 сек)")
                        else:
                            if stale_detected[symbol]:
                                stale_detected[symbol] = False
                                print(f"✅ {timestamp} | {symbol}: цена снова обновляется (${price:.2f})")

                    # Выводим каждую 12-ю проверку (каждую минуту)
                    if i % 12 == 0:
                        if len(price_history[symbol]) >= 2:
                            prev_price = price_history[symbol][-2][1]
                            change = price - prev_price
                            print(f"   {timestamp} | {symbol}: ${price:.2f} (Δ{change:+.2f})")
                        else:
                            print(f"   {timestamp} | {symbol}: ${price:.2f}")
                else:
                    print(f"   {timestamp} | {symbol}: НЕТ ЦЕНЫ ❌")

            await asyncio.sleep(5)

        # Результаты
        print("\n" + "=" * 70)
        print("📊 РЕЗУЛЬТАТЫ ТЕСТА:")
        print("=" * 70)

        for symbol in symbols:
            if len(price_history[symbol]) > 0:
                prices = [p for _, p in price_history[symbol]]
                unique_prices = len(set(prices))
                min_price = min(prices)
                max_price = max(prices)
                volatility = max_price - min_price

                print(f"\n{symbol}:")
                print(f"  Всего измерений: {len(prices)}")
                print(f"  Уникальных цен: {unique_prices}")
                print(f"  Диапазон: ${min_price:.2f} - ${max_price:.2f}")
                print(f"  Волатильность: ${volatility:.2f}")

                if unique_prices < len(prices) * 0.5:
                    print(f"  ⚠️  ПРОБЛЕМА: Слишком мало уникальных цен ({unique_prices}/{len(prices)})")
                else:
                    print(f"  ✅ ОК: Цены обновляются регулярно")

        await price_monitor.stop()
        print("\n✅ Тест завершен\n")
        return 0

    except Exception as e:
        print(f"\n❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
        await price_monitor.stop()
        return 1

if __name__ == "__main__":
    try:
        exit_code = asyncio.run(test_rtds_staleness())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n⚠️  Тест прерван пользователем")
        sys.exit(1)
