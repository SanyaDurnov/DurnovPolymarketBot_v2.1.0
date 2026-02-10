#!/usr/bin/env python3
"""
Test different Chainlink feeds to find the most accurate ones.
"""

import sys
import asyncio
sys.path.insert(0, '/Users/sanyadurnov/Documents/Polymarket_bot_V2')

import aiohttp

class ChainlinkFeedTester:
    """Test different Chainlink feeds."""

    # Разные Chainlink feeds для BTC/USD
    BTC_FEEDS = {
        "BTC/USD Main": "0xF4030086522a5bEEa4988F8CA5B36dbC97BeE88c",  # Основной
        "BTC/USD Coinbase": "0xAed0c38402a5d19df6E4c03F4E2DceD6e29c1ee9",  # Coinbase
        "BTC/USD Binance": "0xBe9897146f7B1a8bD9579EAa8e4e53E8c3E8E3F9",   # Binance
        "BTC/USD Kraken": "0x6B73C84152fE2b04B1b9F2b4f4b9F2b4f4b9F2b4",   # Kraken (проверить)
    }

    RPC_URL = "https://ethereum-rpc.publicnode.com"

    async def test_feed(self, name: str, address: str) -> float | None:
        """Test single feed."""
        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "eth_call",
                    "params": [
                        {
                            "to": address,
                            "data": "0xfeaf968c"  # latestRoundData()
                        },
                        "latest"
                    ]
                }

                async with session.post(self.RPC_URL, json=payload) as response:
                    if response.status != 200:
                        print(f"❌ {name}: HTTP {response.status}")
                        return None

                    data = await response.json()
                    result = data.get('result')

                    if not result or result == '0x' or len(result) < 130:
                        print(f"❌ {name}: Invalid result")
                        return None

                    # Extract price
                    answer_hex = result[66:130]
                    answer_int = int(answer_hex, 16)
                    price = answer_int / (10 ** 8)

                    print(f"✅ {name}: ${price:.2f}")
                    return price

        except Exception as e:
            print(f"❌ {name}: Error - {e}")
            return None

    async def test_all_feeds(self):
        """Test all BTC feeds."""
        print("🧪 Тестирование разных Chainlink feeds для BTC/USD...")
        print("=" * 50)

        results = {}
        for name, address in self.BTC_FEEDS.items():
            price = await self.test_feed(name, address)
            if price:
                results[name] = price

        print("\\n📊 Результаты:")
        print("=" * 50)

        if results:
            # Найти min/max цены
            prices = list(results.values())
            min_price = min(prices)
            max_price = max(prices)
            avg_price = sum(prices) / len(prices)

            print(f"Количество рабочих feeds: {len(results)}")
            print(f"Средняя цена: ${avg_price:.2f}")
            print(f"Минимальная цена: ${min_price:.2f}")
            print(f"Максимальная цена: ${max_price:.2f}")
            print(f"Разброс: ${max_price - min_price:.2f}")

            print("\\nЦены по feeds:")
            for name, price in results.items():
                diff = price - avg_price
                print(f"  {name}: ${price:.2f} ({'+' if diff >= 0 else ''}{diff:.2f})")
        else:
            print("❌ Ни один feed не работает")

async def main():
    tester = ChainlinkFeedTester()
    await tester.test_all_feeds()

if __name__ == "__main__":
    asyncio.run(main())