# Services Architecture - Polymarket Bot V2

**Status:** File-based caching (production-ready)
**Future:** Redis migration available (see [MIGRATION_TO_REDIS.md](MIGRATION_TO_REDIS.md))

---

## Overview

The bot is now split into **3 independent services** for better performance and reliability:

```
┌─────────────────────────────────────────────────────────────┐
│                    Service Architecture                      │
└─────────────────────────────────────────────────────────────┘

┌──────────────────────────┐
│  1. ChainlinkPriceCollector │  ← Collects historical crypto prices
│     (Background Service)     │     Runs: Continuously
└──────────────────────────┘     Storage: data/chainlink_btc_prices.json

┌──────────────────────────┐
│  2. Market Service          │  ← Fetches & filters markets from Gamma API
│     (Background Service)     │     Runs: Every 15 minutes (configurable)
└──────────────────────────┘     Storage: data/filtered_markets.json

┌──────────────────────────┐
│  3. Trading Bot             │  ← Trading logic + Web UI + Market Monitor
│     (Main Application)      │     Runs: Continuously
└──────────────────────────┘     Reads: Cache files from services 1 & 2
```

---

## Why This Architecture?

### Before (Monolithic)
- ❌ Web UI freezes during market fetch
- ❌ Heavy API calls block trading
- ❌ Can't scale to multiple bots
- ❌ Hard to debug which part is slow

### After (Services)
- ✅ Web UI always responsive
- ✅ Trading logic focused on trading
- ✅ Can run multiple bots reading same cache
- ✅ Easy to monitor and debug each service
- ✅ Services can be restarted independently

---

## Service Details

### 1. ChainlinkPriceCollector

**Purpose:** Collect historical crypto prices for `price_to_beat` calculation

**File:** `app/connectors/chainlink_price_collector.py`

**What it does:**
- Connects to Polymarket RTDS WebSocket
- Collects BTC/ETH/SOL prices every minute
- Stores last 100,000 prices (~27 hours of data)
- Auto-cleans old data

**Storage:** `data/chainlink_btc_prices.json`

**Runs:** Continuously (background process)

**Start:**
```bash
python -m app.connectors.chainlink_price_collector
```

**Logs:** `logs/price_collector.log`

---

### 2. Market Service (NEW!)

**Purpose:** Fetch and cache filtered markets for trading bots

**File:** `market_service.py`

**What it does:**
- Fetches all markets from Gamma API
- Applies filters (time-based, symbols, tags)
- Stores filtered markets in cache
- Updates every N minutes (configurable)

**Storage:**
- Markets: `data/filtered_markets.json`
- Metadata: `data/filtered_markets_meta.json`

**Configuration:**
- Update interval: `MARKETS_UPDATE_INTERVAL_MINUTES` in `app/config.py`
- Filters: `app/app_config.py`

**Start:**
```bash
python market_service.py
```

**Logs:** `logs/market_service.log`

---

### 3. Trading Bot

**Purpose:** Execute trading strategies and serve web interface

**File:** `main.py` (runs `web/app.py`)

**What it does:**
- Reads cached markets from Market Service
- Executes trading strategies
- Manages positions
- Runs Market Monitor (auto-closes positions)
- Serves web UI

**Depends on:**
- ChainlinkPriceCollector (for price_to_beat)
- Market Service (for markets)

**Start:**
```bash
python main.py
```

**Web UI:** http://localhost:8000

**Logs:** `logs/trading_bot.log`

---

## Starting Services

### Option 1: Automated Script (Recommended)

```bash
# Start all services
./start_services.sh

# Check status
./start_services.sh status

# Stop all services
./start_services.sh stop

# Restart all services
./start_services.sh restart
```

### Option 2: Manual Start

```bash
# Terminal 1: ChainlinkPriceCollector
python -m app.connectors.chainlink_price_collector

# Terminal 2: Market Service
python market_service.py

# Terminal 3: Trading Bot
python main.py
```

---

## Cache Abstraction Layer

The Market Service uses an **abstraction layer** that allows switching between file-based and Redis caching **without changing any code**.

**File:** `services/market_cache.py`

**Current:** File-based caching
```python
def get_market_cache() -> MarketCache:
    return FileMarketCache("data/filtered_markets.json")
```

**Future:** Redis caching (change ONE line)
```python
def get_market_cache() -> MarketCache:
    return RedisMarketCache("redis://localhost:6379")
```

**See:** [MIGRATION_TO_REDIS.md](MIGRATION_TO_REDIS.md) for migration guide

---

## Benefits by Service

### ChainlinkPriceCollector
- ✅ Reliable historical price data
- ✅ No external API dependencies at market close
- ✅ Accurate price_to_beat calculation
- ✅ Automatic data cleanup

### Market Service
- ✅ Web UI never freezes during market fetch
- ✅ Trading bot starts instantly (no waiting for API)
- ✅ Multiple bots can share same cache
- ✅ Configurable update frequency

### Trading Bot
- ✅ Focused on trading logic
- ✅ Always responsive web interface
- ✅ Can restart without affecting market data
- ✅ Easy to run multiple instances

---

## Monitoring

### Check Service Status

```bash
./start_services.sh status
```

**Expected output:**
```
✅ ChainlinkPriceCollector is running (PID: 12345)
✅ Market Service is running (PID: 12346)
✅ Trading Bot is running (PID: 12347)
```

### Watch Logs

```bash
# All logs
tail -f logs/*.log

# Specific service
tail -f logs/market_service.log
tail -f logs/price_collector.log
tail -f logs/trading_bot.log
```

### Check Cache Files

```bash
# Market cache
cat data/filtered_markets_meta.json
# Shows: {"last_update": "2026-02-08T12:34:56", "market_count": 150}

# Price collector data
ls -lh data/chainlink_btc_prices.json
# Should be ~31 MB
```

---

## Troubleshooting

### Market Service not starting

**Error:** `ModuleNotFoundError: No module named 'services'`

**Solution:**
```bash
# Ensure you're in project root
cd /Users/sanyadurnov/Documents/Polymarket_bot_V2
python market_service.py
```

### Trading bot shows "No markets available"

**Check:**
1. Is Market Service running? `./start_services.sh status`
2. Does cache file exist? `ls -lh data/filtered_markets.json`
3. Is cache stale? `cat data/filtered_markets_meta.json`

**Solution:**
```bash
# Restart market service
./start_services.sh stop
./start_services.sh start
```

### Price collector stopped

**Check lock file:**
```bash
ls -la data/price_collector.lock
```

**Remove if stale:**
```bash
rm data/price_collector.lock
python -m app.connectors.chainlink_price_collector
```

---

## Configuration

### Market Update Interval

**File:** `app/config.py`

```python
# Update markets every N minutes
MARKETS_UPDATE_INTERVAL_MINUTES = 15  # Default: 15 minutes

# Options:
# 5   - Every 5 minutes (frequent updates, more API calls)
# 10  - Every 10 minutes (balanced)
# 15  - Every 15 minutes (recommended)
# 30  - Every 30 minutes (less API load)
```

### Market Filters

**File:** `app/app_config.py`

```python
# Auto-generate time-based filters
auto_generate_filters = True

# Coins to track
coins = ["Bitcoin", "Ethereum", "Solana"]

# Time filters
filter_markets_started_minutes_ago = 15      # Markets started <15 min ago
filter_markets_starting_within_minutes = 20  # Markets starting <20 min ahead
```

---

## Performance Impact

### Before (Monolithic)
- 🐌 Market fetch: 10-30 seconds
- 🐌 Web UI: Freezes during fetch
- 🐌 Bot startup: 10-30 seconds
- 🐌 Multiple bots: Race conditions

### After (Services)
- ⚡ Market fetch: Background (invisible)
- ⚡ Web UI: Always responsive
- ⚡ Bot startup: <1 second
- ⚡ Multiple bots: Safe with shared cache

---

## Scaling to Multiple Bots

### With File-Based Cache
```bash
# Bot 1
python main.py --port 8000

# Bot 2 (different port)
python main.py --port 8001

# Bot 3 (different port)
python main.py --port 8002
```

**Note:** All bots read from same file. Works for 2-3 bots, but better to use Redis for more.

### With Redis Cache
See [MIGRATION_TO_REDIS.md](MIGRATION_TO_REDIS.md) - allows unlimited bots with position coordination.

---

## Future Enhancements

### Phase 1: Current (File-Based) ✅
- [x] Market Service separated
- [x] Cache abstraction layer
- [x] Startup automation
- [x] Migration documentation

### Phase 2: Redis Migration (When Needed)
- [ ] Migrate to Redis cache
- [ ] Position locking for multi-bot
- [ ] Centralized bot coordination
- [ ] Real-time bot status dashboard

### Phase 3: Advanced (Future)
- [ ] FastAPI service wrapper
- [ ] Bot-to-bot communication
- [ ] Distributed position tracking
- [ ] Global risk limits

---

## Summary

**3 Services:**
1. **ChainlinkPriceCollector** - Historical prices
2. **Market Service** - Fetch & cache markets
3. **Trading Bot** - Trading logic + UI

**Start all services:**
```bash
./start_services.sh
```

**Check status:**
```bash
./start_services.sh status
```

**Migrate to Redis when ready:**
See [MIGRATION_TO_REDIS.md](MIGRATION_TO_REDIS.md) - literally one line of code!

**Architecture is:**
- ✅ Production-ready
- ✅ Easy to maintain
- ✅ Ready to scale
- ✅ Simple to migrate

Happy trading! 🚀
