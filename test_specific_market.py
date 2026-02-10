import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from trading.position_manager import PositionManager
from polymarket.client import PolymarketClient
from monitoring.price_monitor import PriceMonitor
from trading.order_manager import OrderManager
import asyncio
from datetime import datetime, timezone

async def main():
    # Создаем тестовые объекты
    pm_client = PolymarketClient()
    price_monitor = PriceMonitor()
    order_manager = OrderManager(pm_client)

    # Получаем тестовый рынок
    market_id = "1340437"
    market_data = pm_client.get_market_data(market_id)
    print(f"Market ID: {market_id}")
    print(f"Market Name: {market_data.get('question')}")
    print()

    # Создаем менеджер позиций
    manager = PositionManager(market_id, pm_client, order_manager, price_monitor)
    print(f"Detected Symbol: {manager.symbol}")
    print()

    # Проверяем цену для этого символа
    price = price_monitor.get_price(manager.symbol)
    print(f"Current Price: ${price:.2f}")

    # Проверяем волатильность
    volatility = price_monitor.get_volatility(manager.symbol)
    for tf, vol in volatility.items():
        print(f"Volatility ({tf}): {vol:.2f}%")

    # Проверяем получение цены по времени
    if price_monitor.chainlink_collector:
        current_time = int(datetime.now(timezone.utc).timestamp())
        price_now = price_monitor.chainlink_collector.get_price_at_time(manager.symbol, current_time)
        price_1min = price_monitor.chainlink_collector.get_price_at_time(manager.symbol, current_time - 60)
        price_5min = price_monitor.chainlink_collector.get_price_at_time(manager.symbol, current_time - 300)
        
        print(f"\nPrice Now: ${price_now:.2f}")
        print(f"Price 1min ago: ${price_1min:.2f}")
        print(f"Price 5min ago: ${price_5min:.2f}")

if __name__ == "__main__":
    asyncio.run(main())