#!/usr/bin/env python3
"""
Test that current price is now taken from Polymarket RTDS.
"""

import sys
import time
sys.path.insert(0, '/Users/sanyadurnov/Documents/Polymarket_bot_V2')

from monitoring.price_monitor import PriceMonitor

def main():
    print('🧪 Тестирование получения current price из Polymarket RTDS...')

    # Создаем PriceMonitor
    monitor = PriceMonitor()

    # Проверяем цены для всех символов
    symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']

    print('Проверяем цены из разных источников:')
    print('=' * 50)

    for symbol in symbols:
        # Цена из PriceMonitor (теперь должна быть из Polymarket)
        monitor_price = monitor.get_price(symbol)

        # Цена напрямую из Polymarket
        polymarket_price = monitor.get_polymarket_price(symbol)

        # Цена из Binance (для сравнения)
        binance_price = monitor.binance.get_last_price(symbol)

        print(f'{symbol}:')
        print(f'  PriceMonitor: ${monitor_price:.2f}' if monitor_price else '  PriceMonitor: None')
        print(f'  Polymarket:   ${polymarket_price:.2f}' if polymarket_price else '  Polymarket:   None')
        print(f'  Binance:      ${binance_price:.2f}' if binance_price else '  Binance:      None')

        # Проверяем совпадение
        if monitor_price and polymarket_price:
            diff = abs(monitor_price - polymarket_price)
            if diff < 0.01:  # Разница меньше 1 цента
                print('  ✅ PriceMonitor использует Polymarket!')
            else:
                print(f'  ❌ Разница: ${diff:.2f}')
        elif monitor_price and binance_price:
            diff = abs(monitor_price - binance_price)
            if diff < 0.01:
                print('  ⚠️  PriceMonitor использует Binance (fallback)')
            else:
                print(f'  ❌ Разница с Binance: ${diff:.2f}')
        else:
            print('  ❌ Нет данных для сравнения')

        print()

    # Проверяем статус Polymarket соединения
    print('Статус соединений:')
    print(f'Polymarket connected: {monitor.polymarket.is_connected}')
    print(f'Binance connected: {monitor.binance.is_connected}')

    if monitor.polymarket.is_connected:
        print('Последние цены из Polymarket RTDS:')
        for symbol in symbols:
            price = monitor.polymarket.get_price(symbol)
            timestamp = monitor.polymarket.get_timestamp(symbol)
            if price and timestamp:
                print(f'  {symbol}: ${price:.2f} в {timestamp.strftime("%H:%M:%S")}')
            else:
                print(f'  {symbol}: нет данных')

if __name__ == "__main__":
    main()