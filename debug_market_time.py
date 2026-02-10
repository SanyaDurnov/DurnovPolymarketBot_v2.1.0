#!/usr/bin/env python3
"""
Debug market opening time parsing.
"""

import sys
import datetime
sys.path.insert(0, '/Users/sanyadurnov/Documents/Polymarket_bot_V2')

from polymarket.client import PolymarketClient

def main():
    print('🔍 Отладка времени открытия рынка 1298845...')

    client = PolymarketClient()
    market_data = client.get_market_data('1298845')

    if not market_data:
        print('❌ Не удалось получить данные рынка')
        return

    print('📋 Сырые данные рынка:')
    print(f'  createdAt: {market_data.get("createdAt")}')
    print(f'  active: {market_data.get("active")}')
    print(f'  closed: {market_data.get("closed")}')

    # Разные способы парсинга времени
    created_at = market_data.get('createdAt', '')
    print(f'\\n🔧 Парсинг времени: "{created_at}"')

    if created_at:
        # Способ 1: как UTC
        try:
            dt_utc = datetime.datetime.fromisoformat(created_at.replace('Z', '+00:00'))
            print(f'  Как UTC: {dt_utc} (ts: {int(dt_utc.timestamp())})')

            now_utc = datetime.datetime.now(datetime.timezone.utc)
            diff_utc = (now_utc - dt_utc).total_seconds() / 3600
            print(f'  Прошло (UTC): {diff_utc:.1f} часов')
        except Exception as e:
            print(f'  Ошибка UTC: {e}')

        # Способ 2: как ET (Eastern Time, UTC-5)
        try:
            # Убираем Z и парсим как naive datetime
            dt_naive = datetime.datetime.fromisoformat(created_at.replace('Z', ''))
            # Предполагаем, что это ET (UTC-5)
            dt_et = dt_naive.replace(tzinfo=datetime.timezone(datetime.timedelta(hours=-5)))
            dt_utc_from_et = dt_et.astimezone(datetime.timezone.utc)

            print(f'  Как ET (UTC-5): {dt_et} -> UTC: {dt_utc_from_et} (ts: {int(dt_utc_from_et.timestamp())})')

            now_utc = datetime.datetime.now(datetime.timezone.utc)
            diff_et = (now_utc - dt_utc_from_et).total_seconds() / 3600
            print(f'  Прошло (ET): {diff_et:.1f} часов')
        except Exception as e:
            print(f'  Ошибка ET: {e}')

        # Способ 3: как локальное время
        try:
            dt_local = datetime.datetime.fromisoformat(created_at.replace('Z', ''))
            print(f'  Как локальное: {dt_local} (ts: {int(dt_local.timestamp())})')

            now_local = datetime.datetime.now()
            diff_local = (now_local - dt_local).total_seconds() / 3600
            print(f'  Прошло (лок): {diff_local:.1f} часов')
        except Exception as e:
            print(f'  Ошибка лок: {e}')

    # Проверим вопрос рынка
    question = market_data.get('question', '')
    print(f'\\n❓ Вопрос: {question}')

    # Проверим время из вопроса
    if 'January 31' in question and '8:45AM-9:00AM' in question:
        print('🎯 Это рынок на 8:45AM-9:00AM ET 31 января')

        # ET = UTC-5, так что 8:45AM ET = 13:45 UTC
        market_date = datetime.date.today()
        if datetime.datetime.now().hour < 13:  # Если сейчас до 13:00, то рынок вчера
            market_date = market_date - datetime.timedelta(days=1)

        market_datetime_et = datetime.datetime.combine(
            market_date,
            datetime.time(8, 45, 0),
            tzinfo=datetime.timezone(datetime.timedelta(hours=-5))
        )

        market_datetime_utc = market_datetime_et.astimezone(datetime.timezone.utc)
        print(f'  Расчетное время открытия: {market_datetime_et} ET -> {market_datetime_utc} UTC')
        print(f'  Timestamp: {int(market_datetime_utc.timestamp())}')

        now_utc = datetime.datetime.now(datetime.timezone.utc)
        diff_calc = (now_utc - market_datetime_utc).total_seconds() / 3600
        print(f'  Прошло (расчет): {diff_calc:.1f} часов')

if __name__ == "__main__":
    main()