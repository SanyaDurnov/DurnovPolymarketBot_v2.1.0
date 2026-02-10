#!/usr/bin/env python3
"""
Full demo script to show orderbook dump functionality with real Polymarket data.
This will show the exact same output as the auto-entry system.
"""

import sys
sys.path.insert(0, '/Users/sanyadurnov/Documents/Polymarket_bot_V2')

import logging
from datetime import datetime, timezone, timedelta

# Настраиваем логирование (как в основном приложении)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)  # Выводим в stdout чтобы было видно
    ]
)
logger = logging.getLogger(__name__)

# Импортируем компоненты
from polymarket.client import PolymarketClient

def demo_real_orderbook_dump():
    """Демонстрируем orderbook dump с реальными данными Polymarket."""
    print("=" * 60)
    print("🎯 ДЕМОНСТРАЦИЯ ORDERBOOK DUMP С РЕАЛЬНЫМИ ДАННЫМИ")
    print("=" * 60)

    # Инициализируем клиент
    print("🔧 Инициализация Polymarket клиента...")
    client = PolymarketClient()

    if not client._client:
        print("❌ Клиент не инициализирован!")
        return

    print("✅ Клиент инициализирован успешно")

    # Получаем активные рынки
    print("\n📊 Получение активных рынков...")
    markets = client.get_markets()
    if not markets:
        print("❌ Не найдено активных рынков")
        return

    # Берем первый активный рынок
    active_market = None
    for market in markets[:5]:  # Проверяем первые 5
        if market.get('active'):
            active_market = market
            break

    if not active_market:
        print("❌ Не найдено активных рынков")
        return

    market_id = active_market.get('id')
    title = active_market.get('title', 'Unknown')[:50]

    print(f"🎯 Выбран рынок: {market_id} - {title}")

    # Получаем orderbook
    print(f"\n📈 Получение orderbook для рынка {market_id}...")
    orderbook = client.get_orderbook(market_id)

    if not orderbook or 'orderbooks' not in orderbook:
        print("❌ Не удалось получить orderbook")
        return

    print("✅ Orderbook получен успешно!")

    # Имитируем логику из auto_entry.py - ВЫВОД ДАМПА
    print("\n" + "="*60)
    print("🎯 ORDERBOOK DUMP (как в auto_entry системе)")
    print("="*60)

    if orderbook and 'orderbooks' in orderbook:
        logger.info(f"=== ORDERBOOK DUMP FOR MARKET {market_id} BEFORE FIRST ITERATION ===")
        for outcome_key, outcome_data in orderbook['orderbooks'].items():
            logger.info(f"Outcome {outcome_key}:")
            if 'bids' in outcome_data and outcome_data['bids']:
                bids_sorted = sorted(outcome_data['bids'], key=lambda x: float(x['price']), reverse=True)  # Highest first
                logger.info(f"  BIDS (top 5, highest first): {bids_sorted[:5]}")
            if 'asks' in outcome_data and outcome_data['asks']:
                asks_sorted = sorted(outcome_data['asks'], key=lambda x: float(x['price']))  # Lowest first
                logger.info(f"  ASKS (top 5, lowest first): {asks_sorted[:5]}")
        logger.info("=== END ORDERBOOK DUMP ===")

    # Анализ цен
    print("\n" + "="*60)
    print("🎯 АНАЛИЗ ЦЕН ДЛЯ ПОКУПКИ")
    print("="*60)

    best_price = 0.0
    total_bids = 0
    total_asks = 0

    print("🔍 DEBUG: Поиск минимальной ask цены среди ВСЕХ asks...")

    # Собираем ВСЕ ask цены из всех outcomes
    all_ask_prices = []
    for outcome_key, outcome_data in orderbook['orderbooks'].items():
        if 'asks' in outcome_data and outcome_data['asks']:
            for ask in outcome_data['asks']:
                price = float(ask['price'])
                all_ask_prices.append(price)
                print(f"   {outcome_key}: ask = {price}")
            total_asks += len(outcome_data['asks'])

        if 'bids' in outcome_data and outcome_data['bids']:
            total_bids += len(outcome_data['bids'])

    # Находим минимальную цену среди ВСЕХ asks
    if all_ask_prices:
        best_price = min(all_ask_prices)
        print(f"   ✅ Минимальная цена среди всех asks: {best_price}")
    else:
        best_price = 0.0
        print("   ❌ Не найдено ни одной ask цены")

    print(f"Лучшая цена для покупки (минимальная ask): ${best_price:.4f}")
    print(f"📊 Ордербук {market_id}: best_ask={best_price:.4f}, total_bids={total_bids}, total_asks={total_asks}")

    # Проверка лимита
    MAX_PRICE = 0.52
    print(f"\n🎯 ПРОВЕРКА ЛИМИТА ЦЕНЫ:")
    print(f"   Лучшая цена: ${best_price:.4f}")
    print(f"   Лимит: ${MAX_PRICE}")
    print(f"   Результат: {'✅ ПРОХОДИТ' if best_price < MAX_PRICE else '❌ НЕ ПРОХОДИТ - СЛИШКОМ ДОРОГО'}")

    if best_price >= MAX_PRICE:
        print(f"\n💸 Цена ${best_price:.4f} >= лимита ${MAX_PRICE}")
        print("   Итерация покупки будет пропущена (как в реальной системе)")
    else:
        print(f"\n💰 Цена ${best_price:.4f} < лимита ${MAX_PRICE}")
        print("   Можно начинать покупку!")

    print("\n" + "="*60)
    print("🎉 ДЕМОНСТРАЦИЯ ЗАВЕРШЕНА!")
    print("Теперь ты видишь как работает orderbook dump в реальной системе!")
    print("="*60)

if __name__ == "__main__":
    demo_real_orderbook_dump()