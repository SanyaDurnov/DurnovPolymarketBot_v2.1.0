"""
Market caching abstraction layer.

Supports both file-based (simple) and Redis-based (scalable) caching.
Switch between them by changing get_market_cache() factory function.

Current: File-based (no dependencies)
Future: Redis-based (just change one line)
"""

from abc import ABC, abstractmethod
import json
import os
import tempfile
from typing import List, Dict, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class MarketCache(ABC):
    """Abstract interface for market data caching."""

    @abstractmethod
    def get_markets(self) -> List[Dict]:
        """Get cached markets."""
        pass

    @abstractmethod
    def set_markets(self, markets: List[Dict]) -> None:
        """Store markets in cache."""
        pass

    @abstractmethod
    def get_last_update(self) -> Optional[datetime]:
        """Get timestamp of last cache update."""
        pass

    @abstractmethod
    def is_stale(self, max_age_seconds: int = 1800) -> bool:
        """Check if cache is stale (older than max_age_seconds)."""
        pass

    @abstractmethod
    def add_market(self, market: Dict) -> None:
        """Add or update a single market in cache."""
        pass


class FileMarketCache(MarketCache):
    """
    File-based market cache.

    Pros:
    - No dependencies (just Python)
    - Easy to debug (just open the JSON file)
    - Works immediately

    Cons:
    - Potential race conditions with multiple readers
    - Limited to single machine

    Use for:
    - Development
    - Single bot deployment
    - Quick setup
    """

    def __init__(self, file_path: str = "data/filtered_markets.json"):
        self.file_path = file_path
        self.meta_path = file_path.replace(".json", "_meta.json")

        # Ensure directory exists
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        logger.info(f"FileMarketCache initialized: {file_path}")

    def get_markets(self) -> List[Dict]:
        """Load markets from JSON file."""
        try:
            with open(self.file_path, 'r') as f:
                markets = json.load(f)
            logger.debug(f"Loaded {len(markets)} markets from {self.file_path}")
            return markets
        except FileNotFoundError:
            logger.warning(f"Market cache file not found: {self.file_path}")
            return []
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse market cache: {e}")
            return []

    def set_markets(self, markets: List[Dict]) -> None:
        """
        Save markets to JSON file (atomic write).

        Uses temp file + rename for atomic write to prevent
        race conditions where reader gets partial data.
        """
        try:
            # Atomic write with temp file
            dir_path = os.path.dirname(self.file_path)
            with tempfile.NamedTemporaryFile(
                'w',
                delete=False,
                dir=dir_path,
                suffix='.tmp'
            ) as tmp:
                json.dump(markets, tmp, indent=2)
                tmp.flush()
                os.fsync(tmp.fileno())
                tmp_name = tmp.name

            # Atomic rename
            os.replace(tmp_name, self.file_path)

            # Store metadata
            with open(self.meta_path, 'w') as f:
                json.dump({
                    "last_update": datetime.now().isoformat(),
                    "market_count": len(markets)
                }, f)

            logger.info(f"✅ Cached {len(markets)} markets to {self.file_path}")

        except Exception as e:
            logger.error(f"❌ Failed to cache markets: {e}")
            raise

    def get_last_update(self) -> Optional[datetime]:
        """Get timestamp of last cache update."""
        try:
            with open(self.meta_path, 'r') as f:
                meta = json.load(f)
                return datetime.fromisoformat(meta["last_update"])
        except (FileNotFoundError, KeyError, ValueError):
            return None

    def is_stale(self, max_age_seconds: int = 1800) -> bool:
        """Check if cache is older than max_age_seconds (default 30 min)."""
        last_update = self.get_last_update()
        if not last_update:
            return True
        age_seconds = (datetime.now() - last_update).total_seconds()
        return age_seconds > max_age_seconds

    def add_market(self, market: Dict) -> None:
        """
        Add or update a single market in cache.

        If market with same ID exists, it will be updated.
        If not, it will be appended to the list.
        """
        try:
            # Get current markets
            markets = self.get_markets()

            # Find and update if exists, otherwise append
            market_id = str(market.get("id"))
            updated = False

            for i, existing_market in enumerate(markets):
                if str(existing_market.get("id")) == market_id:
                    markets[i] = market
                    updated = True
                    logger.info(f"✅ Updated market {market_id} in cache")
                    break

            if not updated:
                markets.append(market)
                logger.info(f"✅ Added new market {market_id} to cache")

            # Save updated list
            self.set_markets(markets)

        except Exception as e:
            logger.error(f"❌ Failed to add market to cache: {e}")


class RedisMarketCache(MarketCache):
    """
    Redis-based market cache.

    Pros:
    - No race conditions (atomic operations)
    - Multiple bots can share cache
    - Fast (in-memory)
    - Supports distributed locking

    Cons:
    - Requires Redis installation
    - Slightly more complex setup

    Use for:
    - Production with multiple bots
    - High-frequency updates
    - Distributed deployments
    """

    def __init__(self, redis_url: str = "redis://localhost:6379"):
        try:
            import redis
            self.redis = redis.from_url(redis_url, decode_responses=True)
            self.markets_key = "polymarket:filtered_markets"
            self.meta_key = "polymarket:markets_meta"

            # Test connection
            self.redis.ping()
            logger.info(f"✅ Connected to Redis at {redis_url}")
        except ImportError:
            raise ImportError(
                "Redis not installed. Run: pip install redis\n"
                "Or switch back to FileMarketCache in services/market_cache.py"
            )
        except Exception as e:
            raise ConnectionError(f"❌ Failed to connect to Redis: {e}")

    def get_markets(self) -> List[Dict]:
        """Load markets from Redis."""
        data = self.redis.get(self.markets_key)
        if not data:
            logger.warning("No markets found in Redis cache")
            return []

        markets = json.loads(data)
        logger.debug(f"Loaded {len(markets)} markets from Redis")
        return markets

    def set_markets(self, markets: List[Dict]) -> None:
        """Save markets to Redis."""
        self.redis.set(self.markets_key, json.dumps(markets))
        self.redis.hset(self.meta_key, mapping={
            "last_update": datetime.now().isoformat(),
            "market_count": len(markets)
        })
        logger.info(f"✅ Cached {len(markets)} markets to Redis")

    def get_last_update(self) -> Optional[datetime]:
        """Get timestamp of last cache update."""
        timestamp = self.redis.hget(self.meta_key, "last_update")
        if not timestamp:
            return None
        return datetime.fromisoformat(timestamp)

    def is_stale(self, max_age_seconds: int = 1800) -> bool:
        """Check if cache is older than max_age_seconds."""
        last_update = self.get_last_update()
        if not last_update:
            return True
        age_seconds = (datetime.now() - last_update).total_seconds()
        return age_seconds > max_age_seconds

    def add_market(self, market: Dict) -> None:
        """
        Add or update a single market in Redis cache.

        If market with same ID exists, it will be updated.
        If not, it will be appended to the list.
        """
        try:
            # Get current markets
            markets = self.get_markets()

            # Find and update if exists, otherwise append
            market_id = str(market.get("id"))
            updated = False

            for i, existing_market in enumerate(markets):
                if str(existing_market.get("id")) == market_id:
                    markets[i] = market
                    updated = True
                    logger.info(f"✅ Updated market {market_id} in Redis cache")
                    break

            if not updated:
                markets.append(market)
                logger.info(f"✅ Added new market {market_id} to Redis cache")

            # Save updated list
            self.set_markets(markets)

        except Exception as e:
            logger.error(f"❌ Failed to add market to Redis cache: {e}")


# ============================================================================
# Factory Function - CHANGE THIS TO MIGRATE
# ============================================================================

def get_market_cache() -> MarketCache:
    """
    Create market cache instance.

    CURRENT: File-based caching (no setup required)

    TO MIGRATE TO REDIS:
    1. Install Redis: brew install redis (macOS) or apt install redis (Linux)
    2. Start Redis: redis-server
    3. Install Python client: pip install redis
    4. Change the return statement below to: return RedisMarketCache()

    See MIGRATION_TO_REDIS.md for detailed instructions.
    """

    # PHASE 1: File-based (CURRENT)
    return FileMarketCache("data/filtered_markets.json")

    # PHASE 2: Redis-based (UNCOMMENT WHEN READY)
    # return RedisMarketCache("redis://localhost:6379")
