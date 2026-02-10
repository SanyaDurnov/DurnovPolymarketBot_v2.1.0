#!/usr/bin/env python3
"""
Market Data Service - Standalone process for fetching and caching markets.

This service runs independently from the trading bot and:
1. Fetches markets from Gamma API
2. Applies filters (time-based, symbols, etc.)
3. Caches filtered markets for bot consumption
4. Updates cache at configurable intervals

Usage:
    python market_service.py

The service runs continuously until stopped (Ctrl+C).
"""

import sys
import time
import logging
from datetime import datetime
from typing import List, Dict

# Add project root to path
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.market_cache import get_market_cache
from polymarket.client import PolymarketClient
from app.app_config import app_config
from app import config as main_config

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/market_service.log')
    ]
)
logger = logging.getLogger(__name__)


class MarketService:
    """Service for fetching and caching filtered markets."""

    def __init__(self):
        self.cache = get_market_cache()
        self.pm_client = PolymarketClient()
        self.update_interval = app_config.markets_update_interval_minutes * 60  # Convert to seconds
        logger.info(f"Market Service initialized")
        logger.info(f"Update interval: {app_config.markets_update_interval_minutes} minutes")
        logger.info(f"Cache type: {type(self.cache).__name__}")

    def fetch_and_filter_markets(self) -> List[Dict]:
        """
        Fetch markets from Gamma API and apply filters.

        Returns:
            List of filtered market dictionaries
        """
        try:
            logger.info("=" * 70)
            logger.info("Fetching markets from Gamma API...")

            # Use existing PolymarketClient logic (как было раньше)
            all_markets = self.pm_client.get_markets(use_cache=False)

            logger.info(f"Fetched {len(all_markets)} total markets")

            # Filter markets (already done by PolymarketClient based on app_config)
            filtered_markets = all_markets

            logger.info(f"After filtering: {len(filtered_markets)} markets")

            # Log sample market for debugging
            if filtered_markets:
                sample = filtered_markets[0]
                logger.info(f"Sample market: {sample.get('question', 'N/A')[:100]}")

            return filtered_markets

        except Exception as e:
            logger.error(f"❌ Error fetching markets: {e}", exc_info=True)
            return []

    def update_cache(self) -> bool:
        """
        Fetch markets and update cache.

        Returns:
            True if successful, False otherwise
        """
        try:
            markets = self.fetch_and_filter_markets()

            if not markets:
                logger.warning("⚠️  No markets fetched, keeping existing cache")
                return False

            # Update cache
            self.cache.set_markets(markets)

            last_update = self.cache.get_last_update()
            logger.info(f"✅ Cache updated successfully at {last_update}")
            logger.info(f"Next update in {app_config.markets_update_interval_minutes} minutes")

            return True

        except Exception as e:
            logger.error(f"❌ Failed to update cache: {e}", exc_info=True)
            return False

    def run(self):
        """
        Main service loop.

        Fetches markets and updates cache at regular intervals.
        Runs until interrupted (Ctrl+C).
        """
        logger.info("=" * 70)
        logger.info("🚀 Market Service started")
        logger.info("=" * 70)

        # Initial fetch
        logger.info("Performing initial market fetch...")
        self.update_cache()

        # Main loop
        try:
            while True:
                logger.info(f"⏳ Sleeping for {app_config.markets_update_interval_minutes} minutes...")
                time.sleep(self.update_interval)

                logger.info("⏰ Update interval reached, fetching markets...")
                self.update_cache()

        except KeyboardInterrupt:
            logger.info("\n👋 Market Service stopped by user")
        except Exception as e:
            logger.error(f"❌ Market Service crashed: {e}", exc_info=True)
            sys.exit(1)


def main():
    """Entry point for market service."""
    # Ensure logs directory exists
    os.makedirs('logs', exist_ok=True)

    # Create and run service
    service = MarketService()
    service.run()


if __name__ == "__main__":
    main()
