#!/usr/bin/env python3
"""
Check market 1298831 data and opening time.
"""

import sys
import datetime
sys.path.insert(0, '/Users/sanyadurnov/Documents/Polymarket_bot_V2')

from polymarket.client import PolymarketClient

def main():
    client = PolymarketClient()
    market_data = client.get_market_data('1298831')

    if market_data:
        print('Рынок 1298831:')
        print(f'  Question: {market_data.get("question", "")[:100]}...')
        print(f'  Active: {market_data.get("active")}')
        print(f'  Closed: {market_data.get("closed")}')
        print(f'  Created: {market_data.get("createdAt", "")}')

        # Проверим время открытия
        created_at = market_data.get('createdAt', '')
        if created_at:
            # Парсим время
            try:
                # Формат: "2026-01-31T12:30:00.000Z"
                dt = datetime.datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                print(f'  Время открытия: {dt}')
                print(f'  Timestamp открытия: {int(dt.timestamp())}')

                # Текущее время
                now = datetime.datetime.now(datetime.timezone.utc)
                print(f'  Текущее время: {now}')
                time_diff_hours = (now - dt).total_seconds() / 3600
                print(f'  Прошло времени: {time_diff_hours:.1f} часов')

                if time_diff_hours < 0:
                    print('  ❌ Рынок еще не открылся!')
                elif time_diff_hours < 24:
                    print('  ✅ Рынок недавно открылся')
                else:
                    print('  ✅ Рынок открыт давно')

            except Exception as e:
                print(f'  Не удалось распарсить время: {created_at} (ошибка: {e})')
    else:
        print('Не удалось получить данные рынка 1298831')

if __name__ == "__main__":
    main()