# Copilot Instructions for Polymarket_bot_V2

## Project Overview
This is an automated trading bot for Polymarket and Binance, organized by domain-specific modules. The architecture is modular, with clear separation between analysis, indicators, monitoring, trading, and storage components.

## Key Components
- **analysis/**: Probability and statistical analysis logic.
- **indicators/**: Implements market indicators (candle, momentum, volatility) and utility functions.
- **monitoring/**: Connectors and monitors for Binance and Polymarket, including real-time data streaming and price monitoring.
- **polymarket/**: Client and orderbook logic for interacting with Polymarket.
- **storage/**: Price buffer and data storage utilities.
- **trading/**: Order and position management, including simulation tools.
- **web/**: Reserved for web interface or API endpoints (currently minimal).

## Data Flow & Integration
- Market data is ingested via `monitoring/binance_connector.py` and `monitoring/polymarket_rtds.py`.
- Analysis and indicator modules process data for trading signals.
- Trading decisions are executed via `trading/order_manager.py` and `trading/position_manager.py`.
- Storage modules buffer and persist price data for analysis and backtesting.

## Developer Workflows
- **Dependencies**: Install Python packages from `requirements.txt`.
- **No explicit build/test scripts**: Add your own as needed. Use standard Python workflows (pytest, etc.).
- **Debugging**: Focus on entry points in `monitoring/` and `trading/` for live trading and simulation.

## Project Conventions
- Each domain folder has an `__init__.py` for explicit module boundaries.
- Utility/helper functions are grouped in `indicators/utils.py`.
- Real-time data is handled in `monitoring/` and buffered in `storage/`.
- Trading logic is separated from analysis/indicators for clarity and testability.

## External Integrations
- **Binance**: via `monitoring/binance_connector.py`
- **Polymarket**: via `polymarket/client.py` and `polymarket/orderbook.py`

## Example Patterns
- To add a new indicator, create a module in `indicators/` and update `indicators/__init__.py`.
- To extend trading logic, modify or subclass in `trading/order_manager.py` or `trading/position_manager.py`.
- For new data sources, add connectors in `monitoring/` and update data flow in analysis modules.

## References
- See `README.md` for high-level project description (if present).
- Use `requirements.txt` for dependency management.

---
**Update this file as project conventions evolve.**
