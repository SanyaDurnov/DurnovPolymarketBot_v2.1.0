#!/usr/bin/env python3
"""
Test that orderbook correctly extracts best bid/ask prices.
"""

import sys
sys.path.insert(0, '/Users/sanyadurnov/Documents/Polymarket_bot_V2')

from polymarket.orderbook import OrderbookAnalyzer
from polymarket.client import PolymarketClient

def test_best_price_extraction():
    """Test the _get_best_price method with sample data."""
    print('🧪 Тестирование извлечения лучших цен из orderbook...')

    # Создаем analyzer без реального клиента для тестирования
    analyzer = OrderbookAnalyzer(None)

    # Тестовые данные - массив ордеров с разными ценами
    test_orders = [
        {"price": 0.45, "size": 100},
        {"price": 0.48, "size": 200},
        {"price": 0.42, "size": 150},
        {"price": 0.50, "size": 50},
    ]

    print('Тестовые ордера:')
    for i, order in enumerate(test_orders, 1):
        print(f'  {i}. price=${order["price"]}, size={order["size"]}')

    # Тестируем bid (максимальная цена)
    best_bid = analyzer._get_best_price(test_orders, "bid")
    print(f'\\nЛучший BID (макс. цена): ${best_bid:.2f}')
    print('Ожидалось: $0.50')
    assert best_bid == 0.50, f"Ожидалось 0.50, получено {best_bid}"

    # Тестируем ask (минимальная цена)
    best_ask = analyzer._get_best_price(test_orders, "ask")
    print(f'Лучший ASK (мин. цена): ${best_ask:.2f}')
    print('Ожидалось: $0.42')
    assert best_ask == 0.42, f"Ожидалось 0.42, получено {best_ask}"

    print('✅ Тесты пройдены!')

def test_real_orderbook():
    """Test with real orderbook data from Polymarket."""
    print('\\n🧪 Тестирование с реальными данными Polymarket...')

    # Создаем реальный клиент
    client = PolymarketClient()
    analyzer = OrderbookAnalyzer(client)

    # Тестируем на рынке 1298845
    market_id = "1298845"
    print(f'Получаем orderbook для рынка {market_id}...')

    orderbook = analyzer.get_orderbook(market_id)
    if not orderbook:
        print('❌ Не удалось получить orderbook')
        return

    print('Raw orderbook получен, извлекаем лучшие цены...')

    best_prices = analyzer.get_best_bid_ask(orderbook)
    if not best_prices:
        print('❌ Не удалось извлечь лучшие цены')
        return

    print('✅ Лучшие цены извлечены:')
    print(f'  UP BID:   ${best_prices["up_bid"]:.4f} (size: {best_prices["up_bid_size"]})')
    print(f'  UP ASK:   ${best_prices["up_ask"]:.4f} (size: {best_prices["up_ask_size"]})')
    print(f'  DOWN BID: ${best_prices["down_bid"]:.4f} (size: {best_prices["down_bid_size"]})')
    print(f'  DOWN ASK: ${best_prices["down_ask"]:.4f} (size: {best_prices["down_ask_size"]})')
    print(f'  UP SPREAD:   {best_prices["up_spread"]:.4f}')
    print(f'  DOWN SPREAD: {best_prices["down_spread"]:.4f}')

    # Проверяем логику: bid должен быть меньше ask
    if best_prices["up_bid"] and best_prices["up_ask"]:
        if best_prices["up_bid"] >= best_prices["up_ask"]:
            print('❌ ОШИБКА: UP BID >= UP ASK!')
        else:
            print('✅ UP BID < UP ASK - корректно')

    if best_prices["down_bid"] and best_prices["down_ask"]:
        if best_prices["down_bid"] >= best_prices["down_ask"]:
            print('❌ ОШИБКА: DOWN BID >= DOWN ASK!')
        else:
            print('✅ DOWN BID < DOWN ASK - корректно')

def main():
    try:
        test_best_price_extraction()
        test_real_orderbook()
        print('\\n🎉 Все тесты пройдены!')
    except Exception as e:
        print(f'\\n❌ Ошибка в тестах: {e}')
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()