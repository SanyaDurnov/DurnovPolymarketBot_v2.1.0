"""
Test the fixed market outcome determination logic.

This test verifies that the determine_market_outcome function
correctly determines winners based on Polymarket logic:
- UP wins when end_price >= price_to_beat (price went higher)
- DOWN wins when end_price < price_to_beat (price went lower)
"""

import sys
import logging
from trading.position import determine_market_outcome

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'
)
logger = logging.getLogger(__name__)


def test_market_outcome_logic():
    """Test the market outcome determination logic."""

    logger.info("=" * 70)
    logger.info("TESTING MARKET OUTCOME LOGIC")
    logger.info("=" * 70)

    # Test Case 1: Price went UP (end_price > price_to_beat)
    logger.info("\n📈 TEST 1: Price went UP")
    logger.info("-" * 70)
    price_to_beat = 95000.0
    end_price = 96000.0
    result = determine_market_outcome(price_to_beat, end_price)
    expected = "UP"
    status = "✅ PASS" if result["outcome"] == expected else "❌ FAIL"
    logger.info(f"{status}: end_price ${end_price} > price_to_beat ${price_to_beat}")
    logger.info(f"   Expected: {expected}, Got: {result['outcome']}")
    assert result["outcome"] == expected, f"Expected {expected}, got {result['outcome']}"

    # Test Case 2: Price went DOWN (end_price < price_to_beat)
    logger.info("\n📉 TEST 2: Price went DOWN")
    logger.info("-" * 70)
    price_to_beat = 95000.0
    end_price = 94000.0
    result = determine_market_outcome(price_to_beat, end_price)
    expected = "DOWN"
    status = "✅ PASS" if result["outcome"] == expected else "❌ FAIL"
    logger.info(f"{status}: end_price ${end_price} < price_to_beat ${price_to_beat}")
    logger.info(f"   Expected: {expected}, Got: {result['outcome']}")
    assert result["outcome"] == expected, f"Expected {expected}, got {result['outcome']}"

    # Test Case 3: Price exactly at target (end_price == price_to_beat)
    logger.info("\n⚖️  TEST 3: Price exactly at target")
    logger.info("-" * 70)
    price_to_beat = 95000.0
    end_price = 95000.0
    result = determine_market_outcome(price_to_beat, end_price)
    expected = "UP"  # In Polymarket, >= means UP wins
    status = "✅ PASS" if result["outcome"] == expected else "❌ FAIL"
    logger.info(f"{status}: end_price ${end_price} == price_to_beat ${price_to_beat}")
    logger.info(f"   Expected: {expected}, Got: {result['outcome']}")
    assert result["outcome"] == expected, f"Expected {expected}, got {result['outcome']}"

    # Test Case 4: Small price increase
    logger.info("\n📈 TEST 4: Small price increase")
    logger.info("-" * 70)
    price_to_beat = 95000.0
    end_price = 95001.0
    result = determine_market_outcome(price_to_beat, end_price)
    expected = "UP"
    status = "✅ PASS" if result["outcome"] == expected else "❌ FAIL"
    logger.info(f"{status}: end_price ${end_price} slightly > price_to_beat ${price_to_beat}")
    logger.info(f"   Expected: {expected}, Got: {result['outcome']}")
    assert result["outcome"] == expected, f"Expected {expected}, got {result['outcome']}"

    # Test Case 5: Small price decrease
    logger.info("\n📉 TEST 5: Small price decrease")
    logger.info("-" * 70)
    price_to_beat = 95000.0
    end_price = 94999.0
    result = determine_market_outcome(price_to_beat, end_price)
    expected = "DOWN"
    status = "✅ PASS" if result["outcome"] == expected else "❌ FAIL"
    logger.info(f"{status}: end_price ${end_price} slightly < price_to_beat ${price_to_beat}")
    logger.info(f"   Expected: {expected}, Got: {result['outcome']}")
    assert result["outcome"] == expected, f"Expected {expected}, got {result['outcome']}"

    logger.info("\n" + "=" * 70)
    logger.info("✅ ALL TESTS PASSED!")
    logger.info("=" * 70)
    logger.info("\n✨ Market outcome logic is working correctly:")
    logger.info("   • UP wins when end_price >= price_to_beat (price went higher)")
    logger.info("   • DOWN wins when end_price < price_to_beat (price went lower)")


if __name__ == "__main__":
    try:
        test_market_outcome_logic()
        sys.exit(0)
    except AssertionError as e:
        logger.error(f"\n❌ TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
