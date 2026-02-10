#!/usr/bin/env python3
"""
Test Price to beat for market 1298845 with correct opening time.
"""

import sys
import time
import datetime
sys.path.insert(0, '/Users/sanyadurnov/Documents/Polymarket_bot_V2')

from app.connectors.chainlink_price_collector import ChainlinkPriceCollector

def main():
    print('🧪 Тестирование Price to beat для рынка 1298845 с правильным временем...')

    # Правильное время открытия: 31 января 8:45AM ET = 13:45 UTC
    market_open_timestamp = 1769867100  # 31 Jan 2026 13:45 UTC
    print(f'🎯 Рынок 1298845 открылся: {datetime.datetime.fromtimestamp(market_open_timestamp)} (ts: {market_open_timestamp})')

    # Проверяем коллектор
    collector = ChainlinkPriceCollector()
    stats = collector.get_stats()
    print(f'📊 Коллектор: {stats["total_entries"]} записей')

    # Проверяем цену на момент открытия
    btc_price_at_open = collector.get_price_at_time('BTCUSDT', market_open_timestamp)
    print(f'💰 BTC цена на открытии: {btc_price_at_open}')

    # Проверяем текущую цену
    current_timestamp = int(time.time())
    btc_price_now = collector.get_price_at_time('BTCUSDT', current_timestamp)
    print(f'💰 BTC цена сейчас: {btc_price_now}')

    # Проверяем ближайшую доступную цену
    if btc_price_at_open is None:
        print('🔍 Ищем ближайшую доступную цену...')

        # Проверим буферы
        if collector.price_buffers['BTCUSDT']:
            # Найдем запись, ближайшую к времени открытия
            closest_entry = min(
                collector.price_buffers['BTCUSDT'],
                key=lambda x: abs(x['timestamp'] - market_open_timestamp)
            )

            time_diff = abs(closest_entry['timestamp'] - market_open_timestamp)
            print(f'📅 Ближайшая запись: {closest_entry["datetime"]} (ts: {closest_entry["timestamp"]})')
            print(f'💰 Цена: ${closest_entry["price"]:.2f}')
            print(f'⏰ Разница: {time_diff} сек ({time_diff/60:.1f} мин)')

            if time_diff <= 300:  # 5 минут
                print('✅ Найдена подходящая цена!')
                btc_price_at_open = closest_entry['price']
            else:
                print('❌ Ближайшая цена слишком старая')

    # Тестируем API
    print('\\n🌐 Тестируем API /api/market/1298845...')
    import subprocess
    try:
        result = subprocess.run([
            'curl', '-s', 'http://localhost:8000/api/market/1298845'
        ], capture_output=True, text=True, timeout=10)

        if result.returncode == 0:
            import json
            try:
                data = json.loads(result.stdout)
                price_to_beat = data.get('price_to_beat')
                status = data.get('status')
                print(f'📡 API ответ: price_to_beat={price_to_beat}, status={status}')

                if price_to_beat and btc_price_at_open:
                    diff = abs(float(price_to_beat) - btc_price_at_open)
                    print(f'🎯 Разница: ${diff:.2f}')
                    if diff < 1:
                        print('✅ Price to beat совпадает с Chainlink!')
                    else:
                        print('❌ Price to beat не совпадает с Chainlink')
            except:
                print(f'📡 API сырой ответ: {result.stdout[:200]}...')
        else:
            print(f'❌ Ошибка API: {result.stderr}')
    except Exception as e:
        print(f'❌ Ошибка тестирования API: {e}')

if __name__ == "__main__":
    main()