import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from trading.position_manager import PositionManager
from polymarket.client import PolymarketClient
from monitoring.price_monitor import PriceMonitor
from trading.order_manager import OrderManager
from trading.position import Position
import asyncio
from datetime import datetime, timezone

async def main():
    # Создаем тестовые объекты
    pm_client = PolymarketClient()
    price_monitor = PriceMonitor()
    order_manager = OrderManager(pm_client)

    # Получаем тестовый рынок (Ethereum рынок)
    market_id = "1340464"
    market_data = pm_client.get_market_data(market_id)
    print(f"Market: {market_data.get('question')}")

    # Создаем менеджер позиций
    manager = PositionManager(market_id, pm_client, order_manager, price_monitor)
    print(f"Detected symbol: {manager.symbol}")

    # Проверяем цену для этого символа
    price = price_monitor.get_price(manager.symbol)
    print(f"Current price: ${price:.2f}")

    # Проверяем волатильность
    volatility = price_monitor.get_volatility(manager.symbol)
    print(f"Volatility (15m): {volatility.get('15m', 'N/A')}%")

    # Создаем тестовую позицию
    position = Position(
        position_id=f"test_pos_{market_id}",
        market_id=market_id,
        market_title=market_data.get('question', 'Unknown'),
        symbol="UNKNOWN",
        side="UP",
        entry_time=datetime.now(timezone.utc),
        entry_price_avg=0.5,
        total_volume=100,
        total_cost_usd=50,
        entry_reason="TEST"
    )

    # Запускаем управления позицией в фоне
    task = asyncio.create_task(manager.start_management(position))
    await asyncio.sleep(2)
    manager.stop_management()
    await task

if __name__ == "__main__":
    asyncio.run(main())