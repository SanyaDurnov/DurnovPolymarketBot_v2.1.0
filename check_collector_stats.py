#!/usr/bin/env python3
"""
Check Chainlink Price Collector statistics.

Shows current number of records and latest prices.
"""

import sys
import os
sys.path.insert(0, '/Users/sanyadurnov/Documents/Polymarket_bot_V2')

from app.connectors.chainlink_price_collector import ChainlinkPriceCollector

def main():
    print('📊 Проверка статистики Chainlink Price Collector...')

    collector = ChainlinkPriceCollector()
    stats = collector.get_stats()

    print(f'Всего записей: {stats["total_entries"]}')
    for symbol, symbol_stats in stats['symbols'].items():
        print(f'{symbol}: {symbol_stats["entries"]} записей')

    # Проверим файл
    if os.path.exists('data/chainlink_btc_prices.json'):
        file_size = os.path.getsize('data/chainlink_btc_prices.json')
        print(f'\nФайл данных: {file_size} байт')

        # Покажем последние записи
        import json
        with open('data/chainlink_btc_prices.json', 'r') as f:
            data = json.load(f)
            for symbol in ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']:
                if symbol in data['prices'] and data['prices'][symbol]:
                    last_entry = data['prices'][symbol][-1]
                    print(f'{symbol} последняя запись: ${last_entry["price"]:.2f} в {last_entry["datetime"]}')

if __name__ == "__main__":
    main()