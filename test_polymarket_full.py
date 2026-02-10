#!/usr/bin/env python3
"""
Test full PriceMonitor with Polymarket RTDS.
"""

import asyncio
import sys
sys.path.insert(0, '/Users/sanyadurnov/Documents/Polymarket_bot_V2')

from monitoring.price_monitor import PriceMonitor

async def test_full_monitor():
    monitor = PriceMonitor()
    try:
        await monitor.start()
        print('✅ PriceMonitor запущен')
        
        # Ждем немного для получения данных
        await asyncio.sleep(5)
        
        symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
        for symbol in symbols:
            monitor_price = monitor.get_price(symbol)
            polymarket_price = monitor.get_polymarket_price(symbol)
            print(f'{symbol}:')
            print(f'  PriceMonitor: ${monitor_price:.2f}' if monitor_price else '  PriceMonitor: None')
            print(f'  Polymarket:   ${polymarket_price:.2f}' if polymarket_price else '  Polymarket:   None')
            
    except Exception as e:
        print(f'❌ Ошибка: {e}')
    finally:
        await monitor.stop()

if __name__ == "__main__":
    asyncio.run(test_full_monitor())