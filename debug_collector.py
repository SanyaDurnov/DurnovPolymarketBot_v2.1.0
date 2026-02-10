#!/usr/bin/env python3
"""
Debug script for Chainlink Price Collector.

Проверяет получение данных из Chainlink и работу коллектора.
"""

import sys
import os
sys.path.insert(0, '/Users/sanyadurnov/Documents/Polymarket_bot_V2')

import asyncio
from app.connectors.chainlink_price_collector import ChainlinkPriceCollector

async def debug_collector():
    print('🔍 Отладка Chainlink Price Collector...')

    collector = ChainlinkPriceCollector()

    try:
        await collector.connect()

        print('1. Тестируем получение цены BTC напрямую из Chainlink...')
        btc_price = await collector._get_current_price('BTCUSDT')
        print(f'   BTC price: {btc_price}')

        print('2. Тестируем получение цены ETH...')
        eth_price = await collector._get_current_price('ETHUSDT')
        print(f'   ETH price: {eth_price}')

        print('3. Тестируем получение цены SOL...')
        sol_price = await collector._get_current_price('SOLUSDT')
        print(f'   SOL price: {sol_price}')

        if btc_price and eth_price and sol_price:
            print('✅ Chainlink работает! Собираем данные...')

            # Пробуем собрать данные
            await collector._collect_prices()

            # Проверяем буферы
            print('4. Проверяем буферы после сбора:')
            for symbol in ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']:
                buffer_len = len(collector.price_buffers[symbol])
                print(f'   {symbol}: {buffer_len} записей')

            # Сохраняем
            collector._save_data()
            print('5. 💾 Данные сохранены')

            # Проверяем файл
            if os.path.exists('data/chainlink_btc_prices.json'):
                file_size = os.path.getsize('data/chainlink_btc_prices.json')
                print(f'6. ✅ Файл создан! Размер: {file_size} байт')

                # Показываем содержимое
                with open('data/chainlink_btc_prices.json', 'r') as f:
                    content = f.read()
                    print(f'   Содержимое файла: {content[:300]}...')
            else:
                print('6. ❌ Файл не создан')
        else:
            print('❌ Chainlink не работает - проверь RPC endpoint')

    except Exception as e:
        print(f'❌ Ошибка: {e}')
        import traceback
        traceback.print_exc()
    finally:
        await collector.disconnect()

if __name__ == "__main__":
    asyncio.run(debug_collector())