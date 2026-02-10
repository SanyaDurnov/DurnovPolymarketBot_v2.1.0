"""
Simple market cache reader for trading bot.

Reads pre-filtered markets from Market Service cache WITHOUT triggering API calls.
"""

from typing import List, Dict, Any
from services.market_cache import get_market_cache
import logging

logger = logging.getLogger(__name__)


def get_cached_markets(search_term: str | List[str] | None = None) -> List[Dict[str, Any]]:
    """
    Get markets from Market Service cache WITHOUT fetching from API.

    This function reads pre-filtered markets cached by Market Service.
    It does NOT trigger API calls or cache updates.

    Args:
        search_term: Optional filter to further narrow down cached markets.
                    If None, returns all cached markets.

    Returns:
        List of market dictionaries from cache
    """
    try:
        cache = get_market_cache()
        markets = cache.get_markets()

        if not markets:
            logger.warning("⚠️  No markets in cache. Is Market Service running?")
            return []

        # If search_term provided, filter markets
        if search_term:
            if isinstance(search_term, str):
                search_terms = [search_term.lower()]
            else:
                search_terms = [term.lower() for term in search_term]

            filtered_markets = []
            for market in markets:
                title = market.get("question", "").lower()
                if any(term in title for term in search_terms):
                    filtered_markets.append(market)

            logger.info(f"📊 Filtered {len(filtered_markets)}/{len(markets)} markets from cache")
            return filtered_markets

        logger.info(f"📊 Loaded {len(markets)} markets from cache")
        return markets

    except Exception as e:
        logger.error(f"❌ Failed to read markets from cache: {e}")
        return []


def get_cached_market_by_id(market_id: str) -> Dict[str, Any] | None:
    """
    Get a specific market from cache by its ID WITHOUT triggering API calls.

    Args:
        market_id: Market ID to search for

    Returns:
        Market dictionary if found, None otherwise
    """
    try:
        cache = get_market_cache()
        markets = cache.get_markets()

        if not markets:
            logger.warning("⚠️  No markets in cache. Is Market Service running?")
            return None

        # Search for market by ID
        market_id_str = str(market_id)
        for market in markets:
            if str(market.get("id")) == market_id_str:
                return market

        logger.warning(f"⚠️  Market {market_id} not found in cache")
        return None

    except Exception as e:
        logger.error(f"❌ Failed to read market {market_id} from cache: {e}")
        return None


def add_market_to_cache(market: Dict[str, Any]) -> bool:
    """
    Add or update a single market in cache.

    This is useful when fetching a market from API (fallback)
    and want to cache it for future requests.

    Args:
        market: Market dictionary to add/update

    Returns:
        True if successful, False otherwise
    """
    try:
        cache = get_market_cache()
        cache.add_market(market)
        logger.info(f"✅ Market {market.get('id')} added to cache")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to add market to cache: {e}")
        return False


def is_cache_fresh(max_age_minutes: int = 30) -> bool:
    """
    Check if market cache is fresh enough.

    Args:
        max_age_minutes: Maximum acceptable cache age in minutes

    Returns:
        True if cache is fresh, False if stale or not available
    """
    try:
        cache = get_market_cache()
        return not cache.is_stale(max_age_seconds=max_age_minutes * 60)
    except Exception as e:
        logger.error(f"❌ Failed to check cache freshness: {e}")
        return False
