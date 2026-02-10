
import asyncio
import logging
from datetime import datetime, timedelta
from unittest.mock import MagicMock, AsyncMock

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("analysis.market_analyzer")

# Mock dependencies
price_monitor = MagicMock()
price_monitor.get_chainlink_price_at_time = AsyncMock(return_value=None)

polymarket_client = MagicMock()
polymarket_client.get_market_start_time = MagicMock(return_value=None)
polymarket_client.get_market_end_time = MagicMock(return_value=None)

orderbook_analyzer = MagicMock()

# Import MarketAnalyzer (assuming it's in the python path)
import sys
import os
sys.path.append(os.getcwd())

from analysis.market_analyzer import MarketAnalyzer

async def test_get_price_to_beat():
    analyzer = MarketAnalyzer(price_monitor, polymarket_client, orderbook_analyzer)
    
    market_id = "1320780"
    symbol = "BTCUSDT"
    current_price = 95000.0
    
    print("\n--- Test Case 1: minutes_since_open = 0, start_time = None (Parsing failed) ---")
    time_metrics_1 = {
        "minutes_since_open": 0,
        "start_time": None
    }
    # This should return None and log DEBUG (hidden) then ERROR in analyze_market
    price_to_beat = await analyzer._get_price_to_beat(market_id, symbol, current_price, time_metrics_1)
    print(f"Result 1: {price_to_beat}")

    print("\n--- Test Case 2: minutes_since_open = 0, start_time = Future ---")
    future_time = datetime.now() + timedelta(minutes=10)
    time_metrics_2 = {
        "minutes_since_open": 0,
        "start_time": future_time
    }
    # This currently returns None because of the early check `if minutes_since_open <= 0`
    price_to_beat = await analyzer._get_price_to_beat(market_id, symbol, current_price, time_metrics_2)
    print(f"Result 2: {price_to_beat}")

    print("\n--- Test Case 3: minutes_since_open = 10, start_time = Past, Chainlink returns None ---")
    past_time = datetime.now() - timedelta(minutes=10)
    time_metrics_3 = {
        "minutes_since_open": 10,
        "start_time": past_time
    }
    price_monitor.get_chainlink_price_at_time.return_value = None
    price_to_beat = await analyzer._get_price_to_beat(market_id, symbol, current_price, time_metrics_3)
    print(f"Result 3: {price_to_beat}")

if __name__ == "__main__":
    asyncio.run(test_get_price_to_beat())
