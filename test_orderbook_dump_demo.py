#!/usr/bin/env python3
"""
Demo script to show orderbook dump functionality.
"""

import sys
sys.path.insert(0, '/Users/sanyadurnov/Documents/Polymarket_bot_V2')

import logging
from datetime import datetime, timezone, timedelta

# Настраиваем логирование
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Импортируем только необходимые модули
# from trading.auto_entry import AutoEntrySystem
# from polymarket.orderbook import OrderbookAnalyzer

def create_mock_orderbook():
    """Создаем mock orderbook с реалистичными данными."""
    return {
        'orderbooks': {
            'UP': {
                'bids': [
                    {'price': '0.95', 'size': '100'},
                    {'price': '0.92', 'size': '200'},
                    {'price': '0.90', 'size': '150'},
                    {'price': '0.88', 'size': '50'},
                    {'price': '0.85', 'size': '75'}
                ],
                'asks': [
                    {'price': '0.99', 'size': '120'},  # <- Это минимальная ask цена
                    {'price': '1.02', 'size': '80'},
                    {'price': '1.05', 'size': '200'},
                    {'price': '1.08', 'size': '90'},
                    {'price': '1.10', 'size': '60'}
                ]
            },
            'DOWN': {
                'bids': [
                    {'price': '0.05', 'size': '300'},
                    {'price': '0.03', 'size': '150'},
                    {'price': '0.02', 'size': '200'},
                    {'price': '0.01', 'size': '100'}
                ],
                'asks': [
                    {'price': '0.08', 'size': '250'},  # <- Минимальная ask цена для DOWN
                    {'price': '0.12', 'size': '180'},
                    {'price': '0.15', 'size': '120'},
                    {'price': '0.18', 'size': '90'}
                ]
            }
        }
    }

def demo_orderbook_parsing():
    """Демонстрируем парсинг ордербука."""
    print("🎯 ДЕМОНСТРАЦИЯ ОРДЕРБУК ДАМПА")
    print("=" * 50)

    # Создаем mock orderbook
    orderbook = create_mock_orderbook()
    market_id = "1314236"  # Пример реального market ID

    # Имитируем логику из auto_entry.py
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

    # Имитируем получение лучшей цены для покупки
    print("\n🎯 АНАЛИЗ ЛУЧШИХ ЦЕН ДЛЯ ПОКУПКИ:")
    print("-" * 40)

    best_price = 0.0
    total_bids = 0
    total_asks = 0

    for outcome_key, outcome_data in orderbook['orderbooks'].items():
        if 'asks' in outcome_data and outcome_data['asks']:
            # Лучшая цена продажи (ask) для покупки outcome tokens
            ask_price = float(outcome_data['asks'][0]['price'])
            if best_price == 0 or ask_price < best_price:
                best_price = ask_price
            total_asks += len(outcome_data['asks'])

        if 'bids' in outcome_data and outcome_data['bids']:
            total_bids += len(outcome_data['bids'])

    print(f"Лучшая цена для покупки (минимальная ask): ${best_price:.4f}")
    print(f"📊 Ордербук {market_id}: best_ask={best_price:.4f}, total_bids={total_bids}, total_asks={total_asks}")

    # Проверяем лимит
    MAX_PRICE = 0.52
    print(f"\n🎯 ПРОВЕРКА ЛИМИТА:")
    print(f"Цена: {best_price:.4f}")
    print(f"Лимит: {MAX_PRICE}")
    print(f"Результат: {'✅ ПРОХОДИТ' if best_price < MAX_PRICE else '❌ НЕ ПРОХОДИТ - СЛИШКОМ ДОРОГО'}")

    if best_price >= MAX_PRICE:
        print(f"\n💸 Цена {best_price:.4f} >= лимита {MAX_PRICE}, итерация будет пропущена")

def demo_buying_logic():
    """Демонстрируем логику покупки."""
    print("\n\n🎯 ДЕМОНСТРАЦИЯ ЛОГИКИ ПОКУПКИ:")
    print("=" * 50)

    # Параметры
    total_amount = 100.0  # $ для входа
    iterations = 6
    amount_per_iteration = total_amount / iterations

    print(f"Общая сумма: ${total_amount}")
    print(f"Итераций: {iterations}")
    print(f"Сумма за итерацию: ${amount_per_iteration:.2f}")

    # Имитируем покупки
    for i in range(1, iterations + 1):
        print(f"\n🔄 Итерация {i}/{iterations}: покупка ${amount_per_iteration:.2f}")

        # Имитируем получение цены
        current_price = 0.99  # Из mock ордербука
        print(f"   Текущая цена: ${current_price:.4f}")

        # Проверяем лимит
        if current_price >= 0.52:
            print(f"   ❌ Цена ${current_price:.4f} >= лимита $0.52, пропускаем итерацию")
            continue

        # Рассчитываем количество tokens
        outcome_amount = amount_per_iteration / current_price
        print(f"   ✅ Покупка: {outcome_amount:.6f} outcome tokens")
        print(f"      По цене: ${current_price:.4f}")
        print(f"      На сумму: ${amount_per_iteration:.2f}")

if __name__ == "__main__":
    demo_orderbook_parsing()
    demo_buying_logic()

    print("\n\n🎉 ДЕМОНСТРАЦИЯ ЗАВЕРШЕНА!")
    print("Теперь ты видишь как работает ордербук дамп и почему цена 0.99 не проходит лимит.")