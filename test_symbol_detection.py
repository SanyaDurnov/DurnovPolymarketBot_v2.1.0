import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from trading.position_manager import PositionManager
from polymarket.client import PolymarketClient
from monitoring.price_monitor import PriceMonitor
from trading.order_manager import OrderManager

# Создаем тестовые объекты
pm_client = PolymarketClient()
price_monitor = PriceMonitor()
order_manager = OrderManager(pm_client)

# Получаем список рынков для теста
markets = pm_client.get_markets()
print(f'Found {len(markets)} markets')

# Тесты на определение символа из названия
test_cases = [
    'Bitcoin Up or Down',
    'Ethereum Up or Down',
    'Solana Up or Down',
    'BTC vs ETH',
    'ETH/USD Prediction',
    'SOL Price Movement'
]

# Создаем тестовый менеджер для каждого случая
for title in test_cases:
    # Создаем временный market_data
    market_data = {'question': title}
    pm_client.get_market_data = lambda x: market_data
    
    manager = PositionManager('test_market', pm_client, order_manager, price_monitor)
    symbol = manager._get_symbol_from_market()
    print(f'Title: \"{title}\" -> Symbol: {symbol}')