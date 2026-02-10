#!/usr/bin/env python3
"""
Test Price to beat for current market 1298831.
"""

import sys
import time
import datetime
sys.path.insert(0, '/Users/sanyadurnov/Documents/Polymarket_bot_V2')

from polymarket.client import PolymarketClient
from app.connectors.chainlink_price_collector import ChainlinkPriceCollector

def main():
    print('🧪 Тестирование Price to beat для рынка 1298831...')

    # Получаем данные рынка
    client = PolymarketClient()
    market_data = client.get_market_data('1298831')

    if not market_data:
        print('❌ Не удалось получить данные рынка')
        return

    # Парсим время открытия
    created_at = market_data.get('createdAt', '')
    if not created_at:
        print('❌ Нет времени создания рынка')
        return

    try:
        # Формат: "2026-01-30T13:37:30.325139Z"
        dt = datetime.datetime.fromisoformat(created_at.replace('Z', '+00:00'))
        market_open_timestamp = int(dt.timestamp())
        print(f'✅ Рынок открылся: {dt} (timestamp: {market_open_timestamp})')
    except Exception as e:
        print(f'❌ Ошибка парсинга времени: {e}')
        return

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
            earliest_entry = min(collector.price_buffers['BTCUSDT'], key=lambda x: x['timestamp'])
            latest_entry = max(collector.price_buffers['BTCUSDT'], key=lambda x: x['timestamp'])

            print(f'📅 Самая ранняя запись: {earliest_entry["datetime"]} (ts: {earliest_entry["timestamp"]})')
            print(f'📅 Самая поздняя запись: {latest_entry["datetime"]} (ts: {latest_entry["timestamp"]})')

            time_diff = earliest_entry['timestamp'] - market_open_timestamp
            hours_diff = time_diff / 3600
            print(f'⏰ Разница: {time_diff} сек ({hours_diff:.1f} часов)')

            if hours_diff > 0:
                print('✅ Коллектор начал работать ПОСЛЕ открытия рынка')
            else:
                print('❌ Коллектор начал работать ДО открытия рынка')

    # Тестируем API
    print('🌐 Тестируем API /api/market/1298831...')
    import subprocess
    try:
        result = subprocess.run([
            'curl', '-s', 'http://localhost:8000/api/market/1298831'
        ], capture_output=True, text=True, timeout=10)

        if result.returncode == 0:
            import json
            try:
                data = json.loads(result.stdout)
                price_to_beat = data.get('price_to_beat')
                status = data.get('status')
                print(f'📡 API ответ: price_to_beat={price_to_beat}, status={status}')
            except:
                print(f'📡 API сырой ответ: {result.stdout[:200]}...')
        else:
            print(f'❌ Ошибка API: {result.stderr}')
    except Exception as e:
        print(f'❌ Ошибка тестирования API: {e}')

if __name__ == "__main__":
    main()