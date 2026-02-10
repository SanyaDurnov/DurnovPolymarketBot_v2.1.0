#!/usr/bin/env python3
"""
Test script for market time parsing.
Tests get_market_start_time and get_market_end_time with example titles.
"""

import sys
import os
sys.path.insert(0, '/Users/sanyadurnov/Documents/Polymarket_bot_V2')

from polymarket.client import PolymarketClient
from app.filter_generator import get_polymarket_time
from datetime import datetime

def test_parsing():
    print('🧪 Тестирование парсинга времени рынков...')

    client = PolymarketClient()

    # Текущая дата в ET
    current_et = get_polymarket_time()
    print(f'Текущее время ET: {current_et.strftime("%Y-%m-%d %H:%M:%S %Z")}')

    # Примеры названий рынков
    test_titles = [
        "Bitcoin Up or Down - February 1, 11:15AM-11:30AM ET",
        "Bitcoin Up or Down - February 1, 11:15PM-11:30PM ET",
        "Ethereum Up or Down - February 1, 11:00AM-11:15AM ET",
        "Solana Up or Down - February 1, 11:00PM-11:15PM ET",
    ]

    for title in test_titles:
        print(f'\n📋 Тестируем: "{title}"')

        # Парсим время начала
        start_time = client.get_market_start_time(title)
        print(f'  Время начала: {start_time}')

        # Парсим время окончания
        end_time = client.get_market_end_time(title)
        print(f'  Время окончания: {end_time}')

        if start_time and end_time:
            # Рассчитываем минуты до начала
            minutes_until_start = (start_time - current_et).total_seconds() / 60
            print(f'  Минут до начала: {minutes_until_start:.1f}')

            # Рассчитываем продолжительность
            duration_minutes = (end_time - start_time).total_seconds() / 60
            print(f'  Продолжительность (мин): {duration_minutes:.1f}')

            # Проверяем, должен ли быть отфильтрован (FILTER_MARKETS_STARTING_WITHIN_MINUTES = 10)
            if minutes_until_start > 10:
                print(f'  ❌ ДОЛЖЕН БЫТЬ ОТФИЛЬТРОВАН (>{10} мин)')
            else:
                print(f'  ✅ ОСТАЕТСЯ В СПИСКЕ (<={10} мин)')
        else:
            print('  ❌ ПАРСИНГ НЕ УДАЛСЯ - НЕ БУДЕТ ОТФИЛЬТРОВАН')

if __name__ == "__main__":
    test_parsing()