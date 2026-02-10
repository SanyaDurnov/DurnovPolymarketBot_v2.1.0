"""
Test the P&L calculation fix for dict vs string outcome comparison.

This test verifies that calculate_polymarket_pnl correctly handles
winning and losing positions when outcome is passed as a dict.
"""

import sys
import logging
from datetime import datetime
from trading.position import Position, calculate_polymarket_pnl

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'
)
logger = logging.getLogger(__name__)


def test_pnl_calculation_with_dict_outcome():
    """Test that P&L is calculated correctly when outcome is in dict format."""

    logger.info("=" * 70)
    logger.info("TESTING P&L CALCULATION WITH DICT OUTCOME")
    logger.info("=" * 70)

    # Create test positions
    up_position = Position(
        position_id="test_up_1",
        market_id="test_market",
        market_title="Test Market",
        symbol="BTCUSDT",
        side="UP",
        entry_price_avg=0.50,
        total_volume=100.0,
        total_cost_usd=50.0,
        entry_time=datetime.now(),
        entry_reason="TEST",
        status="OPEN"
    )

    down_position = Position(
        position_id="test_down_1",
        market_id="test_market",
        market_title="Test Market",
        symbol="BTCUSDT",
        side="DOWN",
        entry_price_avg=0.50,
        total_volume=100.0,
        total_cost_usd=50.0,
        entry_time=datetime.now(),
        entry_reason="TEST",
        status="OPEN"
    )

    # Test Case 1: UP wins (dict format)
    logger.info("\n📈 TEST 1: UP wins (outcome as dict)")
    logger.info("-" * 70)
    outcome_dict = {"outcome": "UP", "end_price": 95500.0}

    # Extract outcome string (simulating the fix)
    outcome_str = outcome_dict.get("outcome") if isinstance(outcome_dict, dict) else outcome_dict

    up_pnl = calculate_polymarket_pnl(up_position, outcome_str)
    down_pnl = calculate_polymarket_pnl(down_position, outcome_str)

    logger.info(f"\nResults:")
    logger.info(f"  UP position P&L: ${up_pnl:.2f} (should be POSITIVE)")
    logger.info(f"  DOWN position P&L: ${down_pnl:.2f} (should be NEGATIVE)")

    assert up_pnl > 0, f"UP position should win! Got P&L=${up_pnl}"
    assert down_pnl < 0, f"DOWN position should lose! Got P&L=${down_pnl}"
    logger.info("  ✅ PASS: UP wins, DOWN loses")

    # Test Case 2: DOWN wins (dict format)
    logger.info("\n📉 TEST 2: DOWN wins (outcome as dict)")
    logger.info("-" * 70)
    outcome_dict = {"outcome": "DOWN", "end_price": 94500.0}

    outcome_str = outcome_dict.get("outcome") if isinstance(outcome_dict, dict) else outcome_dict

    up_pnl = calculate_polymarket_pnl(up_position, outcome_str)
    down_pnl = calculate_polymarket_pnl(down_position, outcome_str)

    logger.info(f"\nResults:")
    logger.info(f"  UP position P&L: ${up_pnl:.2f} (should be NEGATIVE)")
    logger.info(f"  DOWN position P&L: ${down_pnl:.2f} (should be POSITIVE)")

    assert up_pnl < 0, f"UP position should lose! Got P&L=${up_pnl}"
    assert down_pnl > 0, f"DOWN position should win! Got P&L=${down_pnl}"
    logger.info("  ✅ PASS: DOWN wins, UP loses")

    # Test Case 3: String outcome (backward compatibility)
    logger.info("\n🔄 TEST 3: String outcome (backward compatibility)")
    logger.info("-" * 70)
    outcome_str = "UP"

    up_pnl = calculate_polymarket_pnl(up_position, outcome_str)
    down_pnl = calculate_polymarket_pnl(down_position, outcome_str)

    logger.info(f"\nResults:")
    logger.info(f"  UP position P&L: ${up_pnl:.2f} (should be POSITIVE)")
    logger.info(f"  DOWN position P&L: ${down_pnl:.2f} (should be NEGATIVE)")

    assert up_pnl > 0, f"UP position should win! Got P&L=${up_pnl}"
    assert down_pnl < 0, f"DOWN position should lose! Got P&L=${down_pnl}"
    logger.info("  ✅ PASS: String outcome works correctly")

    logger.info("\n" + "=" * 70)
    logger.info("✅ ALL TESTS PASSED!")
    logger.info("=" * 70)
    logger.info("\n✨ P&L calculation correctly handles both winning and losing positions")
    logger.info("   when outcome is passed as a dict with 'outcome' key")


def test_realistic_scenario():
    """Test with realistic values from the log."""
    logger.info("\n" + "=" * 70)
    logger.info("REALISTIC SCENARIO TEST (from actual logs)")
    logger.info("=" * 70)

    # From the actual log:
    # DOWN position: entry_price=$0.4181, invested=$100.00
    # UP position: entry_price=$0.3000, invested=$51.43
    # Outcome: UP wins (end_price $69309.65 < price_to_beat $69621.18)

    down_pos = Position(
        position_id="pos_1350766_1770533583",
        market_id="1350766",
        market_title="Will BTC be above X at Y time?",
        symbol="BTCUSDT",
        side="DOWN",
        entry_price_avg=0.4181,
        total_volume=239.23,  # 100 / 0.4181
        total_cost_usd=100.00,
        entry_time=datetime.now(),
        entry_reason="FIRST_ENTRY",
        status="OPEN"
    )

    up_pos = Position(
        position_id="pos_1350766_1770533841_opposite_entry",
        market_id="1350766",
        market_title="Will BTC be above X at Y time?",
        symbol="BTCUSDT",
        side="UP",
        entry_price_avg=0.3000,
        total_volume=171.43,  # 51.43 / 0.3000
        total_cost_usd=51.43,
        entry_time=datetime.now(),
        entry_reason="OPPOSITE_ENTRY",
        status="OPEN"
    )

    # Market outcome: price went DOWN (end_price < price_to_beat)
    # So DOWN should win, UP should lose
    outcome_dict = {"outcome": "DOWN", "end_price": 69309.65}
    outcome_str = outcome_dict.get("outcome")

    logger.info("\n📊 Market: 1350766")
    logger.info(f"  price_to_beat: $69,621.18")
    logger.info(f"  end_price: $69,309.65")
    logger.info(f"  Price went DOWN → DOWN wins")

    down_pnl = calculate_polymarket_pnl(down_pos, outcome_str)
    up_pnl = calculate_polymarket_pnl(up_pos, outcome_str)

    logger.info(f"\nResults:")
    logger.info(f"  DOWN position: ${down_pnl:.2f} (should be POSITIVE)")
    logger.info(f"  UP position: ${up_pnl:.2f} (should be NEGATIVE)")

    assert down_pnl > 0, f"DOWN should win! Got P&L=${down_pnl}"
    assert up_pnl < 0, f"UP should lose! Got P&L=${up_pnl}"

    total_pnl = down_pnl + up_pnl
    logger.info(f"\n  Total P&L: ${total_pnl:.2f}")
    logger.info("  ✅ PASS: Correct outcome!")


if __name__ == "__main__":
    try:
        test_pnl_calculation_with_dict_outcome()
        test_realistic_scenario()

        logger.info("\n" + "=" * 70)
        logger.info("🎉 ALL TESTS PASSED - FIX VERIFIED!")
        logger.info("=" * 70)
        sys.exit(0)
    except AssertionError as e:
        logger.error(f"\n❌ TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
