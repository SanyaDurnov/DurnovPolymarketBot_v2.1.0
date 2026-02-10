#!/usr/bin/env python3
"""
Test script to get BTC price from 1 minute ago from Chainlink collector.
"""

import sys
import time
sys.path.insert(0, '/Users/sanyadurnov/Documents/Polymarket_bot_V2')

from app.connectors.chainlink_price_collector import ChainlinkPriceCollector

def main():
    print('🧪 Тестирование получения цены BTC минуту назад из коллектора...')

    # Создаем коллектор и проверяем данные
    collector = ChainlinkPriceCollector()

    # Проверяем статистику
    stats = collector.get_stats()
    print('📊 Статистика коллектора:')
    print(f'  Всего записей: {stats["total_entries"]}')
    for symbol, symbol_stats in stats['symbols'].items():
        print(f'  {symbol}: {symbol_stats["entries"]} записей, последняя цена: {symbol_stats["last_price"]}')

    # Тестируем получение цены минуту назад
    one_minute_ago = int(time.time()) - 60
    print(f'\n🎯 Получаем цену BTC на timestamp {one_minute_ago} (минуту назад):')

    price = collector.get_price_at_time('BTCUSDT', one_minute_ago)
    if price:
        print(f'✅ BTC цена минуту назад: ${price:.2f}')
    else:
        print('❌ Цена BTC минуту назад не найдена')

    # Тестируем получение цены сейчас
    now = int(time.time())
    print(f'\n🎯 Получаем цену BTC на timestamp {now} (сейчас):')

    price_now = collector.get_price_at_time('BTCUSDT', now)
    if price_now:
        print(f'✅ BTC цена сейчас: ${price_now:.2f}')
    else:
        print('❌ Цена BTC сейчас не найдена')

    # Проверяем буферы напрямую
    print('\n🔍 Проверяем буферы напрямую:')
    for symbol in ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']:
        buffer_len = len(collector.price_buffers[symbol])
        print(f'  {symbol} буфер: {buffer_len} записей')
        if buffer_len > 0:
            # Показываем последние 3 записи
            for i, entry in enumerate(collector.price_buffers[symbol][-3:]):
                ts = entry['timestamp']
                price_val = entry['price']
                dt = time.strftime('%H:%M:%S', time.localtime(ts))
                print(f'    [{i+1}] {dt}: ${price_val:.2f}')

if __name__ == "__main__":
    main()