#!/usr/bin/env python3
"""
Test to compare prices from Polymarket RTDS and Binance side by side.
This will help us determine if PriceMonitor is using Polymarket or Binance.
"""

import asyncio
import sys
import time
sys.path.insert(0, '/Users/sanyadurnov/Documents/Polymarket_bot_V2')

from app.connectors.polymarket_rtds import PolymarketConnector
from app.connectors.binance import BinanceConnector
from monitoring.price_monitor import PriceMonitor

async def test_price_comparison():
    print('🔍 Тест сравнения источников цен: Polymarket RTDS vs Binance')
    print('=' * 80)
    
    # Создаем отдельные коннекторы
    polymarket = PolymarketConnector()
    binance = BinanceConnector()
    
    # Создаем PriceMonitor
    monitor = PriceMonitor()
    
    try:
        # Запускаем все коннекторы
        await polymarket.connect()
        await binance.start()
        await monitor.start()
        
        print('✅ Все коннекторы запущены')
        print('📊 Сравнение цен в реальном времени:')
        print('-' * 80)
        
        symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
        start_time = time.time()
        
        while True:
            current_time = time.time()
            elapsed = current_time - start_time
            
            if int(elapsed) % 5 == 0:  # Каждые 5 секунд
                print(f'\n⏱️  Прошло: {int(elapsed)}s')
                print('-' * 80)
            
            # Получаем цены из всех источников
            results = []
            for symbol in symbols:
                # Polymarket RTDS (изолированно)
                pm_price = polymarket.get_price(symbol)
                
                # Binance (изолированно)
                bn_price = binance.get_last_price(symbol)
                
                # PriceMonitor (что он использует)
                pm_monitor_price = monitor.get_price(symbol)
                
                # Определяем источник PriceMonitor
                source = "❓ Неизвестно"
                if pm_monitor_price and pm_price:
                    diff_pm = abs(pm_monitor_price - pm_price)
                    if diff_pm < 0.01:  # Разница меньше 1 цента
                        source = "✅ Polymarket"
                    else:
                        source = "❌ Binance"
                
                result_line = f'{symbol}: PM={pm_price:.2f} | BN={bn_price:.2f} | MON={pm_monitor_price:.2f} | Источник: {source}'
                results.append(result_line)
            
            # Очищаем предыдущую строку и выводим новые результаты
            print(f'\r{time.strftime("%H:%M:%S")} | {" | ".join(results)}', end='', flush=True)
            
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        print('\n\n⏹️  Остановлено пользователем')
    except Exception as e:
        print(f'\n❌ Ошибка: {e}')
    finally:
        # Останавливаем все коннекторы
        await polymarket.disconnect()
        await binance.stop()
        await monitor.stop()
        print('\n🔌 Все коннекторы остановлены')

if __name__ == "__main__":
    asyncio.run(test_price_comparison())