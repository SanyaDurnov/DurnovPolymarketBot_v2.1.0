#!/usr/bin/env python3
"""
Check if we have Chainlink price data for market 1298831 opening time.
"""

import sys
import json
sys.path.insert(0, '/Users/sanyadurnov/Documents/Polymarket_bot_V2')

from app.connectors.chainlink_price_collector import ChainlinkPriceCollector

def main():
    collector = ChainlinkPriceCollector()

    # Timestamp открытия рынка 1298831 (из предыдущего вывода)
    market_open_timestamp = 1769780250
    print(f'Рынок 1298831 открылся в timestamp: {market_open_timestamp}')

    # Проверяем, есть ли данные на этот timestamp
    btc_price = collector.get_price_at_time('BTCUSDT', market_open_timestamp)
    print(f'Цена BTC на момент открытия: {btc_price}')

    if btc_price is None:
        print('❌ Нет данных на момент открытия - коллектор начал работать позже')

        # Проверим, какие данные у нас есть
        stats = collector.get_stats()
        print(f'Всего записей: {stats["total_entries"]}')

        # Самая ранняя запись
        if stats['total_entries'] > 0:
            # Загрузим файл и посмотрим первую запись
            try:
                with open('data/chainlink_btc_prices.json', 'r') as f:
                    data = json.load(f)
                    if 'prices' in data and 'BTCUSDT' in data['prices'] and data['prices']['BTCUSDT']:
                        first_entry = data['prices']['BTCUSDT'][0]
                        print(f'Самая ранняя запись: {first_entry["datetime"]} (timestamp: {first_entry["timestamp"]})')

                        # Разница во времени
                        time_diff = first_entry["timestamp"] - market_open_timestamp
                        hours_diff = time_diff / 3600
                        print(f'Разница со временем открытия: {time_diff} сек ({hours_diff:.1f} часов)')

                        if hours_diff > 0:
                            print('✅ Коллектор начал работать ПОСЛЕ открытия рынка')
                        else:
                            print('❌ Коллектор начал работать ДО открытия рынка')
            except Exception as e:
                print(f'Ошибка чтения файла: {e}')
    else:
        print('✅ Есть данные на момент открытия!')

if __name__ == "__main__":
    main()