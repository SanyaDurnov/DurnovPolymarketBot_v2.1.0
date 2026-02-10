#!/usr/bin/env python3
"""
Test Polymarket RTDS with real-time price updates every second.
"""

import asyncio
import sys
import time
sys.path.insert(0, '/Users/sanyadurnov/Documents/Polymarket_bot_V2')

from monitoring.price_monitor import PriceMonitor

async def test_realtime_prices():
    monitor = PriceMonitor()
    try:
        await monitor.start()
        print('✅ PriceMonitor запущен')
        print('📊 Наблюдение за ценами в реальном времени (обновление каждую секунду):')
        print('=' * 80)
        
        start_time = time.time()
        symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
        
        while True:
            current_time = time.time()
            elapsed = current_time - start_time
            
            # Печатаем заголовок каждые 10 секунд
            if int(elapsed) % 10 == 0:
                print(f'\n⏱️  Прошло: {int(elapsed)}s')
                print('-' * 80)
            
            # Получаем и выводим цены
            prices = []
            for symbol in symbols:
                monitor_price = monitor.get_price(symbol)
                if monitor_price:
                    prices.append(f'{symbol}: ${monitor_price:,.2f}')
                else:
                    prices.append(f'{symbol}: --')
            
            # Очищаем предыдущую строку и выводим новые цены
            print(f'\r{time.strftime("%H:%M:%S")} | {" | ".join(prices)}', end='', flush=True)
            
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        print('\n\n⏹️  Остановлено пользователем')
    except Exception as e:
        print(f'\n❌ Ошибка: {e}')
    finally:
        await monitor.stop()
        print('🔌 PriceMonitor остановлен')

if __name__ == "__main__":
    asyncio.run(test_realtime_prices())