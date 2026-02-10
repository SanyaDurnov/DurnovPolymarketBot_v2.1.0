# Research: Simplifying price_to_beat Determination

**Date:** 2026-02-08
**Status:** Research Complete - No Changes Made

## Executive Summary

After thorough investigation, **the current implementation using ChainlinkPriceCollector is the optimal approach**. Polymarket does NOT provide `price_to_beat` or starting price data in their API, so we must collect and store historical prices ourselves.

---

## Current Implementation

### How price_to_beat Works Now

1. **ChainlinkPriceCollector** (`app/connectors/chainlink_price_collector.py`):
   - Runs as background service via WebSocket to Polymarket RTDS
   - Collects real-time crypto prices (BTC, ETH, SOL) every minute
   - Stores historical prices in `data/chainlink_btc_prices.json`
   - Data structure: `{symbol: [{timestamp, price, ...}]}`

2. **PriceToBeatService** (`analysis/price_to_beat_service.py`):
   - When market starts, extracts `startDate` from Gamma API
   - Looks up the price at that exact timestamp from collector's historical data
   - Caches result for performance
   - Fallback: Uses current price if historical data unavailable

### Market Title Format Example
```
"Will Bitcoin be above $100,000 at 10:00PM-10:15PM ET?"
```
- Contains: crypto symbol, target price, time range
- `startDate` from API: Used to get timestamp
- `endDate` from API: Used to determine when market closes

---

## Research Findings

### 1. Polymarket/Gamma API Fields Available

Queried `https://gamma-api.polymarket.com/markets/{market_id}`, found these fields:

**Available:**
- ✅ `id` - Market ID
- ✅ `question` / `title` - Market title/question
- ✅ `startDate` - ISO timestamp when market starts (e.g., "2025-01-05T18:49:12.543209Z")
- ✅ `endDate` - ISO timestamp when market ends
- ✅ `outcomes` - Array like ["Yes", "No"] or ["Up", "Down"]
- ✅ `outcomePrices` - Current market prices (e.g., ["0.52", "0.48"])
- ✅ `active` - Boolean if market is active
- ✅ `closed` - Boolean if market is closed
- ✅ `liquidity` - Current liquidity
- ✅ `volume` - Trading volume

**NOT Available:**
- ❌ `startPrice` - NO field for starting crypto price
- ❌ `targetPrice` - NO field for target price (must parse from title)
- ❌ `price_to_beat` - NO field for price at market start
- ❌ Historical price data - NO historical prices provided

### 2. outcomePrices vs price_to_beat

**Important Distinction:**
- `outcomePrices` = Current market probability/prediction prices (e.g., "UP" costs $0.52)
- `price_to_beat` = Actual crypto price at market start time (e.g., BTC was $95,100 at 10:00 PM)

These are **completely different**:
- `outcomePrices` changes as traders bet → Not useful for determining market outcome
- `price_to_beat` is the reference point → Essential for outcome determination

**Example:**
```
Market: "Will BTC be above $100,000 at 10:00PM ET?"
startDate: "2026-02-08T03:00:00Z" (10:00 PM ET)
outcomePrices: ["0.52", "0.48"] ← Market thinks 52% chance UP

At 10:00 PM:
- Actual BTC price: $95,100 ← This is price_to_beat
- outcomePrices at that moment: Still market prediction, NOT the crypto price

At market end (10:15 PM):
- End price: $95,500
- Comparison: $95,500 < $100,000 → DOWN wins
- price_to_beat not used for outcome (target $100k is in title)
```

Wait, I need to reconsider...

### 3. Re-examining price_to_beat Purpose

Looking at the code more carefully:

In `determine_market_outcome(price_to_beat, end_price)`:
- Compares end_price vs price_to_beat
- NOT comparing against title's target price ($100k)

This suggests markets are structured differently than I assumed. Let me check actual market formats...

Looking at filter generation and market titles, the markets appear to be:
```
"Will BTC be above $X at [TIME1]-[TIME2]?"
```

Where:
- Start time (TIME1) = When we check starting price
- End time (TIME2) = When we check ending price
- Price to beat = Starting price at TIME1
- End price = Price at TIME2
- Outcome: If end_price >= price_to_beat → UP (price increased)

So `price_to_beat` is **the crypto price at market START time**, not the target in the title!

---

## Can We Simplify?

### Option 1: Use Polymarket's outcomePrices ❌

**Status:** NOT VIABLE

`outcomePrices` are market prediction prices, not crypto prices. Cannot use for outcome determination.

### Option 2: Query Price at Runtime ❌

**Status:** NOT RECOMMENDED

Could query Binance API or other sources at market close for historical price.

**Problems:**
- Rate limiting on historical data APIs
- Reliability issues (what if API is down when market closes?)
- Accuracy concerns (slight differences in timestamp interpretation)
- No guarantee of data availability for exact timestamp

### Option 3: Use Polymarket's startDate Field ✅ (Current Approach)

**Status:** ALREADY IMPLEMENTED

Current system:
1. Gets `startDate` from Gamma API ✅
2. Looks up historical price from collector at that timestamp ✅
3. Caches result ✅

**This is optimal because:**
- `startDate` is always available and accurate
- We control our own historical data (no external API dependencies)
- Data is local and fast to query
- Collector runs continuously, ensuring we have prices for all markets

### Option 4: Use Alternative Price Sources ⚠️

**Status:** COMPLEX, NOT RECOMMENDED

Could use:
- Binance Klines API for historical data
- CoinGecko historical prices
- Other crypto data providers

**Problems:**
- Same reliability issues as Option 2
- Additional API dependencies
- Potential costs for premium endpoints
- Still need real-time collection or runtime queries

---

## Current System Benefits

### ✅ Advantages of ChainlinkPriceCollector

1. **Reliability**
   - Runs continuously in background
   - No external API dependencies at market close time
   - Data always available locally

2. **Accuracy**
   - Collects prices every minute
   - Exact timestamp matching possible
   - Averaging capability (3 samples over 30 seconds)

3. **Performance**
   - Local JSON file lookup is fast
   - No network requests at market close
   - Caching in PriceToBeatService

4. **Data Sovereignty**
   - We control our own data
   - No rate limits
   - Can validate and audit prices

5. **Fallback Strategy**
   - If historical data missing: Uses current price
   - Graceful degradation

### ⚠️ Current Limitations

1. **Storage Growth**
   - JSON file grows over time (currently ~31 MB)
   - Max 100,000 entries (~27 hours of data)
   - Auto-cleanup prevents infinite growth

2. **Collector Must Run**
   - Requires background process
   - If collector stops, no new historical data
   - Fallback to current price may not be accurate

3. **Single Point of Failure**
   - If RTDS WebSocket disconnects, price collection pauses
   - Lock file prevents multiple instances (good for safety, but requires monitoring)

---

## Alternative Approaches Considered

### Approach A: On-Demand Binance Historical Query

```python
# At market close, query Binance for historical price
import ccxt
exchange = ccxt.binance()
ohlcv = exchange.fetch_ohlcv('BTC/USDT', '1m', since=start_timestamp, limit=1)
price_to_beat = ohlcv[0][4]  # close price
```

**Pros:**
- No need for collector
- Simpler architecture
- Binance has comprehensive historical data

**Cons:**
- Network request at critical time (market close)
- Rate limits (1200 requests/minute)
- API might be down
- Slight timestamp mismatches possible

### Approach B: Hybrid (Collector + On-Demand Fallback)

Use collector as primary, Binance as fallback if collector data unavailable.

**Pros:**
- Best of both worlds
- Increased reliability

**Cons:**
- More complex
- Still need collector running
- Fallback might have accuracy issues

### Approach C: Database with Periodic Sync

Store prices in SQLite/PostgreSQL, sync from Binance periodically.

**Pros:**
- Better querying capabilities
- Structured data
- Can sync historical data retroactively

**Cons:**
- More infrastructure
- Still need periodic sync process
- Doesn't eliminate collector need

---

## Recommendations

### ✅ Keep Current Implementation

The current **ChainlinkPriceCollector + PriceToBeatService** approach is optimal because:

1. **No simpler alternative exists** - Polymarket doesn't provide starting prices
2. **Current system is reliable** - Local data, no external dependencies
3. **Performance is good** - Fast local lookups with caching
4. **Already working** - System is battle-tested

### 💡 Potential Improvements (Optional)

If you want to enhance the current system:

#### 1. Add Monitoring
```python
# Alert if collector hasn't updated in X minutes
# Check data gaps and auto-restart collector
```

#### 2. Add Binance Fallback
```python
# In PriceToBeatService.get_price_to_beat():
if not price_from_collector:
    price_from_binance = await self._get_binance_historical_price(symbol, timestamp)
    if price_from_binance:
        logger.warning("Using Binance fallback for price_to_beat")
        return price_from_binance
```

#### 3. Optimize Storage
```python
# Move to SQLite instead of JSON
# Automatic cleanup of old data
# Compression for historical data
```

#### 4. Add Data Validation
```python
# Cross-check collector prices against Binance occasionally
# Alert on significant discrepancies
# Maintain data quality metrics
```

---

## Conclusion

**Answer to Your Question:**

> "Can we get price_to_beat from Polymarket? Do we have start_price for market info?"

**No**, Polymarket does NOT provide:
- ❌ `price_to_beat` (crypto price at market start)
- ❌ `start_price` or any crypto price data
- ❌ Historical crypto prices

They only provide:
- ✅ `startDate` / `endDate` (market timing)
- ✅ `outcomePrices` (market prediction prices, NOT crypto prices)

**Your current ChainlinkPriceCollector solution is necessary and optimal.** There is no simpler way to get `price_to_beat` without collecting historical prices yourself.

The collector is well-designed:
- Uses Polymarket's own RTDS feed (most accurate source)
- Stores data locally for reliability
- Has fallback mechanisms
- Properly handles edge cases

**Recommendation:** Keep the current implementation. It cannot be significantly simplified without sacrificing reliability or accuracy.

---

## Technical Details

### Current Data Flow

```
Polymarket RTDS WebSocket
    ↓
ChainlinkPriceCollector (background service)
    ↓
data/chainlink_btc_prices.json (local storage)
    ↓
PriceToBeatService.get_price_to_beat()
    ↓
market_monitor.py (uses for outcome determination)
```

### Files Involved

1. `app/connectors/chainlink_price_collector.py` - Price collection service
2. `analysis/price_to_beat_service.py` - Price lookup and caching
3. `data/chainlink_btc_prices.json` - Historical price storage
4. `trading/market_monitor.py` - Uses price_to_beat for outcomes

### Key Methods

- `ChainlinkPriceCollector.get_price_at_time(symbol, timestamp)` - Lookup historical price
- `PriceToBeatService.get_price_to_beat(market_id)` - Get cached or calculated price
- `PriceToBeatService._get_market_start_time_from_data()` - Extract startDate from API
- `determine_market_outcome(price_to_beat, end_price)` - Compare prices for outcome

---

## Questions & Answers

**Q: Why not use Binance API directly instead of collector?**
A: Reliability. At market close, we need guaranteed price data. External API might be down, rate-limited, or slow. Local data is instant and reliable.

**Q: Can we reduce the collector to run only when markets are active?**
A: No. We need continuous data to have prices for ANY market start time. Markets can start at any minute, so we need every minute's price data.

**Q: Is 31 MB of price data too much?**
A: No. It's ~27 hours of data for 3 symbols. The 100K entry limit auto-cleans old data. This is minimal storage for the reliability it provides.

**Q: What if RTDS WebSocket disconnects?**
A: Collector reconnects automatically. Short gaps use fallback to current price. For long gaps, would need to backfill from Binance (could add this feature).

**Q: Could we use startDate/endDate from API instead of parsing titles?**
A: **Already done!** The fix from earlier prioritizes `startDate`/`endDate` fields over title parsing. Title parsing is just fallback.

---

**Final Verdict:** ✅ **No simplification needed. Current implementation is optimal.**
