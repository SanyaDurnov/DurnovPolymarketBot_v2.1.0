# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Polymarket Bot V2 is a Python-based automated trading bot for Polymarket prediction markets. It features two trading strategies, real-time price monitoring, probability-based analysis, and both simulation and live trading modes.

## Services Architecture

The bot is split into **3 independent services** for better performance and scalability:

1. **ChainlinkPriceCollector** - Collects historical crypto prices via WebSocket
   - File: `app/connectors/chainlink_price_collector.py`
   - Storage: `data/chainlink_btc_prices.json`
   - Purpose: Provides `price_to_beat` for market outcome determination

2. **Market Service** - Fetches and caches filtered markets from Gamma API
   - File: `market_service.py`
   - Storage: `data/filtered_markets.json` (file-based, Redis-ready)
   - Updates: Every N minutes (configurable via `MARKETS_UPDATE_INTERVAL_MINUTES`)
   - Purpose: Keeps market data fresh without blocking trading bot

3. **Trading Bot** - Main application (trading logic + web UI + market monitor)
   - File: `main.py` → `web/app.py`
   - Reads: Cached data from services 1 & 2
   - Purpose: Focus on trading, always responsive

**Benefits:**
- ✅ Web UI never freezes during market fetch
- ✅ Trading bot starts instantly (no API wait)
- ✅ Can run multiple bots sharing same cache
- ✅ Easy to monitor and debug each service independently
- ✅ Ready to migrate to Redis for multi-bot deployments (see `MIGRATION_TO_REDIS.md`)

**See:** [SERVICES_ARCHITECTURE.md](SERVICES_ARCHITECTURE.md) for detailed documentation.

## Commands

### Running the Application

**Recommended: Use automated startup script**
```bash
# Start all services (ChainlinkPriceCollector + Market Service + Trading Bot)
./start_services.sh

# Check service status
./start_services.sh status

# Stop all services
./start_services.sh stop

# Restart all services
./start_services.sh restart
```

**Manual startup (for development)**
```bash
# Terminal 1: Start ChainlinkPriceCollector (price history)
python -m app.connectors.chainlink_price_collector

# Terminal 2: Start Market Service (fetch & cache markets)
python market_service.py

# Terminal 3: Start Trading Bot (trading + web UI)
python main.py --mode web

# Test mode - validates all components
python main.py --mode test

# Run specific test files
python test_position_manager.py
python test_probability_fix.py
```

### Environment Setup

```bash
# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your API keys
```

### Testing Components

```bash
# Test Polymarket client and market fetching
python test_position_manager.py

# Test probability calculations
python test_probability_fix.py

# Test position management
python test_position_manager_probabilities_real.py

# Test soft trading strategy
python test_soft_trading.py

# Test orderbook analysis
python test_orderbook_full_demo.py
```

## High-Level Architecture

### Core Components Flow

```
main.py / web/app.py (entry points)
    ↓
polymarket/client.py (Gamma API + py-clob-client)
    ↓
analysis/market_analyzer.py (market selection & analysis)
    ↓
trading/auto_entry.py OR trading/soft_trading_entry.py
    ↓
trading/position_manager.py OR trading/position_manager_soft_trading.py
    ↓
trading/market_monitor.py (auto-close positions when markets end)
```

### Data Flow Architecture

1. **Price Monitoring** (`monitoring/price_monitor.py`):
   - Binance WebSocket → historical indicators (RSI, MACD, ATR, etc.)
   - Polymarket RTDS → real-time market prices
   - Chainlink feeds → crypto price data

2. **Market Analysis** (`analysis/`):
   - `market_analyzer.py`: Combines price data + indicators → market probabilities
   - `probability.py`: Calculates p_hit, p_terminal using Kalman Filter
   - `price_to_beat_service.py`: Determines market outcome thresholds

3. **Trading Execution** (`trading/`):
   - `auto_entry.py`: Scheduled entry system (1min before market start)
   - `position_manager.py` or `position_manager_soft_trading.py`: Manages positions after entry
   - `order_manager.py`: Executes actual trades via Polymarket API
   - `market_monitor.py`: Monitors open positions and auto-closes when markets resolve

### Strategy System

The bot supports two distinct strategies controlled by `TRADING_STRATEGY` in config.py:

**1. Default Strategy (`"default"`)**
- Uses `trading/auto_entry.py` + `trading/position_manager.py`
- Enters automatically 1 minute before market starts
- Gradual buying with price averaging (2 iterations, 20s intervals)
- Aggressive hedging with opposite positions
- Additional entries when price drops by 15%
- Target: guaranteed profit through hedging

**2. Soft Trading Strategy (`"soft_trading"`)**
- Uses `trading/soft_trading_entry.py` + `trading/position_manager_soft_trading.py`
- More conservative, no auto-entry
- Arbitrage approach: buys both UP and DOWN sides
- Goal: avg_UP + avg_DOWN < $1.00 (guaranteed profit regardless of outcome)
- Enters when edge > 5%
- Max loss: 5% of current position per buy

### Critical Architecture Patterns

#### 1. Market Data Flow (Gamma API)

The `polymarket/client.py` loads markets from Gamma API with extensive caching:
- Markets are cached in `markets_cache.json` for 5 minutes
- Gamma API endpoint: `https://gamma-api.polymarket.com/markets`
- Returns fields: `endDate`, `startDate`, `state`, `question`, `title`, `createdAt`
- **Critical:** Always prioritize `endDate`/`startDate` fields over parsing from title

#### 2. Position Management Lifecycle

```python
# Entry Phase (auto_entry.py or soft_trading_entry.py)
1. Market selected by MarketPreSelector
2. Entry system creates initial position
3. Position Manager spawned for this market

# Management Phase (position_manager.py or position_manager_soft_trading.py)
1. Continuously monitors probabilities (math_prob, market_prob, edge)
2. Decides on opposite entries or additional entries
3. Uses PositionCalculator to determine safe buy amounts

# Exit Phase (market_monitor.py)
1. Runs every N minutes (MARKET_MONITOR_INTERVAL)
2. Checks if market is closed (state or endDate)
3. Determines outcome (UP/DOWN) using price_to_beat
4. Closes all positions for that market
5. Calculates P&L
```

#### 3. Probability Analysis System

The `analysis/probability.py` uses a sophisticated Kalman Filter approach:
- `math_prob`: Mathematical probability from price movement analysis
- `market_prob`: Current market implied probability from orderbook
- `edge`: Difference between math_prob and market_prob
- `p_hit`: Probability of hitting target before market end (geometric Brownian motion)
- `p_terminal`: Probability of ending above target at market close (drift-based)

These are NOT simple price comparisons - they use:
- Historical volatility (ATR + current volatility hybrid)
- Time to market end
- Drift calculations
- Kalman Filter for noise reduction

#### 4. Web UI State Management

`web/app.py` initializes global objects at startup:
- `pm_client`: PolymarketClient (manages API connections)
- `orderbook_analyzer`: OrderbookAnalyzer (best bid/ask prices)
- `market_analyzer`: MarketAnalyzer (probability calculations)
- `order_manager`: OrderManager (trade execution)
- `market_monitor`: MarketMonitor (auto-close positions) - **starts automatically**

These are shared across all API endpoints and background tasks.

## Important Files and Their Roles

### Configuration
- `app/config.py`: Main configuration hub - all tunable parameters
- `.env`: Sensitive credentials (never commit this file)
- `app/app_config.py`: Runtime application state

### Core Trading Logic
- `trading/position.py`: Position data model with P&L tracking
- `trading/position_calculator.py`: Calculates safe buy amounts considering risk
- `trading/market_monitor.py`: Background task that auto-closes positions when markets end
- `analysis/price_to_beat_service.py`: Determines market outcomes (UP vs DOWN)

### Data Connectors
- `app/connectors/binance.py`: Binance historical and WebSocket data
- `app/connectors/polymarket_rtds.py`: Polymarket real-time data stream
- `app/connectors/chainlink_price_collector.py`: Chainlink price feeds

### Web Interface
- `web/app.py`: FastAPI application with startup/shutdown lifecycle
- `templates/`: Jinja2 HTML templates
- `static/`: Frontend assets (JavaScript, CSS)

## Known Issues and Solutions

### Issue: P&L Calculation Bug - Dict vs String Comparison (CRITICAL - FIXED)

**Problem:** ALL positions were being closed as losses (-100% P&L), even winning positions.

**Root Cause:** Type mismatch in `calculate_polymarket_pnl()` function call in `trading/position.py` line 226:
```python
# WRONG: Passing entire dict to function expecting string
pnl = calculate_polymarket_pnl(position, outcome)
# outcome = {"outcome": "UP", "end_price": 69309.646}

# Inside calculate_polymarket_pnl():
if position.side == outcome:  # Comparing "UP" (string) == {...} (dict)
    # This NEVER matches! All positions treated as losses
```

**Solution:** Fixed in `trading/position.py` line 226:
```python
# CORRECT: Extract string from dict before passing
outcome_str = outcome.get("outcome") if isinstance(outcome, dict) else outcome
pnl = calculate_polymarket_pnl(position, outcome_str)
```

**Impact:**
- Winning positions now show POSITIVE P&L
- Losing positions show NEGATIVE P&L
- Example: DOWN position bought at $0.42 for $100, when DOWN wins, yields +$134.39 P&L

**Test:** Run `python test_pnl_calculation_fix.py` to verify the fix.

---

### Issue: Inverted Market Outcome Logic (CRITICAL - FIXED)

**Problem:** All positions were being determined as losses when they should have been wins, and vice versa.

**Root Cause:** The `determine_market_outcome()` function in `trading/position.py` had inverted logic:
```python
# WRONG (old code):
if end_price < price_to_beat:
    outcome = "UP"  # ❌ This is backwards!
else:
    outcome = "DOWN"  # ❌ This is backwards!
```

**Explanation:** In Polymarket crypto prediction markets:
- "UP" means predicting the price will be **HIGHER** than the target
- "DOWN" means predicting the price will be **LOWER** than the target

Therefore:
- If `end_price >= price_to_beat` → UP wins (price went higher)
- If `end_price < price_to_beat` → DOWN wins (price went lower)

**Solution:** Fixed in `trading/position.py` line 399:
```python
# CORRECT (new code):
if end_price >= price_to_beat:
    outcome = "UP"  # ✅ Price is higher, UP wins
else:
    outcome = "DOWN"  # ✅ Price is lower, DOWN wins
```

**Impact:** This fix ensures Market Monitor correctly identifies winning vs losing positions when closing markets.

### Issue: Market Monitor Not Getting end_time

**Problem:** PriceToBeatService showed warnings about missing end_time/symbol for closed markets.

**Root Cause:** PriceToBeatService was parsing time from market `title` instead of using the `endDate`/`startDate` fields directly provided by Gamma API.

**Solution:** Modified `analysis/price_to_beat_service.py`:
- `_calculate_market_info()`: Now prioritizes `market_data.get("endDate")` before falling back to title parsing
- `_get_market_start_time_from_data()`: Now checks `market_data.get("startDate")` first

**Key Takeaway:** Always use direct API fields (`endDate`, `startDate`) rather than parsing from titles. Title parsing is fallback only.

### Issue: Market Monitor Not Running

**Problem:** MarketMonitor existed but wasn't being started.

**Solution:** Added automatic startup in `web/app.py`:
```python
@app.on_event("startup")
async def startup_event():
    # ... other initialization ...
    market_monitor = MarketMonitor(pm_client, price_monitor)
    asyncio.create_task(market_monitor.start_monitoring())
```

Market Monitor now runs automatically for both strategies.

## Configuration Patterns

### Simulation vs Live Trading

Set in `app/config.py`:
```python
SIM_MODE = True  # True = simulation, False = live trading
```

When `SIM_MODE = True`:
- No real orders are placed
- Uses simulated balance from `SIMULATION_INITIAL_BALANCE`
- Safe for testing strategies

### Strategy Selection

```python
TRADING_STRATEGY = "default"  # or "soft_trading"
```

Or via environment variable:
```bash
TRADING_STRATEGY=soft_trading
```

This determines which entry and position manager systems are used.

### Multi-Account Support

The bot supports two Polymarket accounts:
```python
POLYMARKET_ACTIVE_ACCOUNT = 1  # or 2
```

Each account has its own wallet address, private key, and API credentials (suffixed with `_1` or `_2`).

## Development Guidelines

### Adding New Indicators

1. Create indicator in `app/indicators/` (see `momentum.py`, `volatility.py` as examples)
2. Register in `monitoring/price_monitor.py`
3. Access via `market_analyzer.get_market_analysis()`

### Adding New Trading Strategies

1. Create entry system in `trading/` (see `auto_entry.py` or `soft_trading_entry.py`)
2. Create position manager in `trading/` (see `position_manager.py` or `position_manager_soft_trading.py`)
3. Add initialization in `web/app.py` startup based on `TRADING_STRATEGY`
4. Document in `STRATEGIES.md`

### Testing Changes

Always test in SIM_MODE first:
1. Set `SIM_MODE = True` in config.py
2. Run `python main.py --mode test` to validate components
3. Run `python main.py --mode web` and monitor behavior
4. Check logs for errors or unexpected behavior
5. Only switch to live trading after thorough testing

### Working with Probabilities

The probability system in `analysis/probability.py` is complex. Key points:
- Never modify probability calculations without understanding Kalman Filter math
- `math_prob` and `market_prob` are not simple price ratios
- `p_hit` and `p_terminal` use geometric Brownian motion models
- Volatility calculations use hybrid approach (ATR + current volatility)
- Test changes with `test_probability_*.py` scripts

## Web UI Endpoints

- `GET /`: Main dashboard with market overview
- `GET /api/status`: Current bot status and active positions
- `GET /api/markets`: List of monitored markets
- `GET /api/positions`: Open positions with P&L
- `POST /api/close_position`: Manually close a position
- `GET /api/market_monitor_stats`: Market monitor statistics

## Logging and Debugging

### Log Levels

Set in `app/config.py`:
```python
LOG_LEVEL = "INFO"  # DEBUG, INFO, WARNING, ERROR
LITE_LOGS = True  # Reduces verbose PriceMonitor logs
```

### Filtering Logs

```bash
# Market Monitor only
python main.py --mode web 2>&1 | grep "Market Monitor\|🔍\|🎯\|🏆"

# Position closures only
python main.py --mode web 2>&1 | grep "Закрыта позиция"

# P&L only
python main.py --mode web 2>&1 | grep "P&L="
```

## Dependencies and External Services

### Required APIs
- **Polymarket Gamma API**: Market data (no auth required)
- **Polymarket CLOB API**: Order placement (requires wallet + API keys)
- **Binance API**: Historical crypto price data (optional, for indicators)
- **Chainlink**: On-chain price feeds (optional)

### Key Python Libraries
- `py-clob-client>=0.5.7`: Polymarket trading client
- `fastapi>=0.110.0`: Web framework
- `pandas>=2.1.4`, `numpy>=1.26.3`: Data analysis
- `ta>=0.11.0`: Technical indicators
- `web3>=6.15.0`: Blockchain interactions

## Additional Documentation

- `MARKET_MONITOR.md`: Detailed Market Monitor documentation
- `STRATEGIES.md`: Trading strategy comparison and configuration
- `SOFT_TRADING_*.md`: Soft trading strategy guides
- `CHAINLINK_README.md`: Chainlink integration details
- `README.md`: Basic setup and usage

## Common Pitfalls

1. **Don't parse market times from titles** - Use `endDate`/`startDate` fields directly
2. **Always check SIM_MODE** before testing - Avoid accidental live trades
3. **Market Monitor runs automatically** - Don't manually start it
4. **Position managers are per-market** - Each market gets its own instance
5. **Probability calculations are complex** - Use existing test scripts to validate changes
6. **Cache exists for markets** - Check `markets_cache.json` if data seems stale
7. **Two different position managers** - Ensure you're editing the one matching your strategy
