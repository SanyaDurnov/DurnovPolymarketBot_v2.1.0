#!/usr/bin/env python3
"""
Тест для проверки цен Polymarket в реальном времени.
"""

import asyncio
import logging
import sys
import time
from datetime import datetime

# Настраиваем logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Добавляем текущую директорию в путь
sys.path.insert(0, '.')

from monitoring.price_monitor import PriceMonitor


async def test_polymarket_prices():
    """Тестировать получение цен Polymarket."""
    print("🧪 Тестирование цен Polymarket в реальном времени")
    print("=" * 60)

    # Создаем PriceMonitor
    monitor = PriceMonitor()

    try:
        print("🔄 Запуск PriceMonitor...")
        await monitor.start()

        print("📊 Мониторинг цен в реальном времени (10 секунд)...")
        print("BTCUSDT | Polymarket | Binance | Разница")
        print("-" * 50)

        start_time = time.time()
        prices_log = []

        while time.time() - start_time < 10:  # 10 секунд теста
            try:
                # Получаем цены
                polymarket_price = monitor.get_polymarket_price("BTCUSDT")
                binance_price = monitor.get_price("BTCUSDT")

                if polymarket_price and binance_price:
                    diff = polymarket_price - binance_price
                    diff_pct = (diff / binance_price) * 100

                    timestamp = datetime.now().strftime("%H:%M:%S")
                    print(f"{timestamp} | ${polymarket_price:>10.2f} | ${binance_price:>10.2f} | {diff_pct:+.2f}%")

                    prices_log.append({
                        'timestamp': timestamp,
                        'polymarket': polymarket_price,
                        'binance': binance_price,
                        'diff': diff,
                        'diff_pct': diff_pct
                    })

                await asyncio.sleep(1)  # Проверяем каждую секунду

            except Exception as exc:
                print(f"❌ Ошибка при получении цен: {exc}")
                await asyncio.sleep(1)

        # Анализируем результаты
        if prices_log:
            print("\n📈 Анализ результатов:")
            print(f"Всего измерений: {len(prices_log)}")

            if len(prices_log) > 0:
                avg_polymarket = sum(p['polymarket'] for p in prices_log) / len(prices_log)
                avg_binance = sum(p['binance'] for p in prices_log) / len(prices_log)
                avg_diff = sum(p['diff'] for p in prices_log) / len(prices_log)
                avg_diff_pct = sum(p['diff_pct'] for p in prices_log) / len(prices_log)

                print(f"Средняя Polymarket: ${avg_polymarket:.2f}")
                print(f"Средняя Binance:    ${avg_binance:.2f}")
                print(f"Средняя разница:    ${avg_diff:.2f}")
                print(f"Средняя разница %:   {avg_diff_pct:+.2f}%")
                # Проверяем стабильность
                diffs = [abs(p['diff_pct']) for p in prices_log]
                max_diff = max(diffs)
                min_diff = min(diffs)

                print(f"Макс разница:        {max_diff:.2f}%")
                print(f"Мин разница:         {min_diff:.2f}%")
                if max_diff < 0.1:  # Менее 0.1% разницы
                    print("✅ Цены очень близкие - Polymarket можно использовать!")
                elif max_diff < 1.0:  # Менее 1% разницы
                    print("⚠️  Небольшая разница в ценах, но приемлемо")
                else:
                    print("❌ Слишком большая разница в ценах")
        else:
            print("❌ Не удалось получить цены для анализа")

        # Останавливаем монитор
        print("\n🔄 Остановка PriceMonitor...")
        await monitor.stop()

        print("\n✅ Тестирование завершено!")

    except Exception as exc:
        print(f"❌ Ошибка при тестировании: {exc}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # Запускаем тест
    asyncio.run(test_polymarket_prices())