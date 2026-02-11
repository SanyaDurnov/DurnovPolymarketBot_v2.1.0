"""
Web UI для Polymarket Bot V2 (FastAPI).
"""

import asyncio
import logging
import sys
from datetime import datetime, timezone
from typing import Dict, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
import uvicorn

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import config
from app.config import (
    SIM_MODE,
    COINS,
    SIMULATION_INITIAL_BALANCE,
    AUTO_GENERATE_FILTERS,
    GAMMA_API_TAG,
    ACCOUNT_2_TYPE,
    POLYMARKET_WALLET_ADDRESS_1,
    POLYMARKET_WALLET_ADDRESS_2,
    TRADING_STRATEGY,
)
from app.app_config import app_config
from polymarket.client import PolymarketClient
from polymarket.orderbook import OrderbookAnalyzer
from polymarket.market_cache_reader import get_cached_markets, get_cached_market_by_id, add_market_to_cache
from analysis.market_analyzer import MarketAnalyzer
from trading.order_manager import OrderManager
from trading.auto_entry import init_auto_entry_system
from trading.soft_trading_entry import init_soft_trading_entry_system
from trading.position_manager import stop_all_position_managers
from trading.position_manager_soft_trading import stop_all_position_managers_soft
from trading.market_monitor import MarketMonitor
from app.monitoring.collector_monitor import collector_monitor
from app.log_handler import market_log_handler

# Настраиваем логирование для вывода в консоль
# Root logger на WARNING — только критичные ошибки от всех модулей
# force=True чтобы перезаписать basicConfig из main.py (basicConfig работает только 1 раз без force)
logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
    force=True,
)

# Торговые модули — полные INFO логи
for _module in [
    "trading.auto_entry",
    "trading.position_manager",
    "trading.position_manager_soft_trading",
    "trading.soft_trading_entry",
    "trading.order_manager",
    "trading.market_monitor",
    "trading.position",
    "web.app",
]:
    logging.getLogger(_module).setLevel(logging.INFO)

# In-memory handler для просмотра логов на UI (по маркету)
market_log_handler.setFormatter(logging.Formatter(
    '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
))
market_log_handler.setLevel(logging.DEBUG)
logging.getLogger().addHandler(market_log_handler)

logger = logging.getLogger(__name__)

# Создаем FastAPI приложение
app = FastAPI(
    title="Polymarket Bot V2",
    description="Trading bot для Polymarket с анализом вероятностей",
    version="2.0.0",
)

# Настраиваем CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Разрешаем все origins для разработки
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Настраиваем шаблоны и статические файлы
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# Глобальные объекты (инициализируются при старте)
pm_client: Optional[PolymarketClient] = None
orderbook_analyzer: Optional[OrderbookAnalyzer] = None
market_analyzer: Optional[MarketAnalyzer] = None
order_manager: Optional[OrderManager] = None
market_monitor: Optional[MarketMonitor] = None


@app.on_event("startup")
async def startup_event():
    """Инициализация при старте приложения."""
    global pm_client, orderbook_analyzer, market_analyzer, order_manager, market_monitor
    
    try:
        logger.info("Инициализация компонентов...")
        
        # Polymarket Client
        pm_client = PolymarketClient()
        logger.info("✓ Polymarket Client")
        
        # Orderbook Analyzer
        orderbook_analyzer = OrderbookAnalyzer(pm_client)
        # Запускаем кэширование orderbook
        orderbook_analyzer.start_cache_updater()
        logger.info("✓ Orderbook Analyzer (с кэшированием)")
        
        # Order Manager
        order_manager = OrderManager(
            polymarket_client=pm_client,
            orderbook_analyzer=orderbook_analyzer,
            sim_mode=SIM_MODE,
            initial_balance=SIMULATION_INITIAL_BALANCE,
        )
        logger.info("✓ Order Manager (режим: %s)", "SIM" if SIM_MODE else "REAL")
        
        # Инициализируем Price Monitor для Market Analyzer
        from monitoring.price_monitor import PriceMonitor
        price_monitor = PriceMonitor()
        await price_monitor.start()  # Запускаем PriceMonitor для получения цен

        # Market Analyzer
        market_analyzer = MarketAnalyzer(
            price_monitor=price_monitor,
            polymarket_client=pm_client,
            orderbook_analyzer=orderbook_analyzer,
        )
        logger.info("✅ MarketAnalyzer инициализирован")
        logger.info("✓ Market Analyzer")

        # Запускаем автоматическое обновление рынков
        pm_client.start_auto_update()
        logger.info("✓ Автообновление рынков запущено")

        # Запускаем мониторинг коллектора
        collector_monitor.start_monitoring()
        logger.info("✓ Мониторинг коллектора запущен")

        # Запускаем Market Monitor для автоматического закрытия позиций
        market_monitor = MarketMonitor(
            polymarket_client=pm_client,
            price_monitor=price_monitor
        )
        asyncio.create_task(market_monitor.start_monitoring())
        logger.info(f"✓ Market Monitor запущен (интервал: {config.MARKET_MONITOR_INTERVAL} мин)")

        # Выбор и запуск стратегии на основе TRADING_STRATEGY
        logger.info(f"📊 Выбранная стратегия: {TRADING_STRATEGY}")

        if TRADING_STRATEGY == "soft_trading":
            # SOFT TRADING: Запускаем систему по расписанию (аналог auto_entry)
            logger.info("🌙 Запуск SOFT TRADING стратегии...")

            soft_trading_entry_system = init_soft_trading_entry_system(pm_client, price_monitor, order_manager)
            soft_trading_entry_system.start_scheduler()
            logger.info("✓ Система Soft Trading Entry запущена")

            # Запуск планировщика в фоне (общий для обеих стратегий)
            import threading
            def run_scheduler():
                while True:
                    import schedule
                    schedule.run_pending()
                    import time
                    time.sleep(10)  # Проверка каждые 10 секунд

                    # Отладка: показывать активные задачи каждые 5 минут
                    if int(time.time()) % 300 == 0:
                        jobs = schedule.jobs
                        logger.info(f"Планировщик: {len(jobs)} активных задач")
                        for job in jobs:
                            logger.info(f"  Задача: {job}")

            scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
            scheduler_thread.start()
            logger.info("✓ Планировщик запущен в фоне")

        else:
            # DEFAULT: Запускаем auto_entry систему
            logger.info("🎯 Запуск DEFAULT стратегии (auto_entry)...")

            auto_entry_system = init_auto_entry_system(pm_client, price_monitor, order_manager)
            auto_entry_system.start_scheduler()
            logger.info("✓ Система автоматического входа запущена")

            # Запуск планировщика в фоне
            import threading
            def run_scheduler():
                while True:
                    import schedule
                    schedule.run_pending()
                    import time
                    time.sleep(10)  # Проверка каждые 10 секунд

                    # Отладка: показывать активные задачи каждые 5 минут
                    if int(time.time()) % 300 == 0:
                        jobs = schedule.jobs
                        logger.info(f"Планировщик: {len(jobs)} активных задач")
                        for job in jobs:
                            logger.info(f"  Задача: {job}")

            scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
            scheduler_thread.start()
            logger.info("✓ Планировщик запущен в фоне")

        logger.info("✓ Все компоненты инициализированы")

    except Exception as exc:
        logger.error("Ошибка при инициализации: %s", exc, exc_info=True)


@app.on_event("shutdown")
async def shutdown_event():
    """Очистка при остановке приложения."""
    logger.info("🛑 Остановка приложения...")

    try:
        # Остановка Market Monitor
        if market_monitor:
            logger.info("Остановка Market Monitor...")
            market_monitor.stop_monitoring()

        # Остановка менеджеров позиций в зависимости от стратегии
        if TRADING_STRATEGY == "soft_trading":
            logger.info("Остановка soft trading менеджеров...")
            stop_all_position_managers_soft()
        else:
            logger.info("Остановка position менеджеров...")
            stop_all_position_managers()

        logger.info("✓ Все компоненты остановлены")

    except Exception as exc:
        logger.error("Ошибка при остановке: %s", exc, exc_info=True)


@app.get("/")
async def root(request: Request):
    """Главная страница."""
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/markets")
async def get_markets(limit: int = 10):
    """
    Получить список доступных рынков.
    
    Args:
        limit: Максимальное количество рынков (по умолчанию 10)
    """
    if not pm_client:
        raise HTTPException(status_code=500, detail="Polymarket Client не инициализирован")

    try:
        # Read from Market Service cache (no API calls)
        markets = get_cached_markets()
        
        if not markets:
            return {"markets": [], "count": 0}
        
        # Ограничиваем количество
        limited_markets = markets[:limit]
        
        # Форматируем для API
        formatted_markets = []
        for market in limited_markets:
            formatted_markets.append({
                "id": str(market.get("id", "")),
                "title": market.get("title") or market.get("question", ""),
                "active": market.get("active", True),
            })
        
        return {
            "markets": formatted_markets,
            "count": len(formatted_markets),
            "total": len(markets),
        }
        
    except Exception as exc:
        logger.error("Ошибка при получении рынков: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/market/{market_id}")
async def get_market_analysis(market_id: str):
    """
    Получить полный анализ рынка.

    Args:
        market_id: ID рынка на Polymarket
    """
    if not market_analyzer:
        raise HTTPException(
            status_code=500,
            detail="Market Analyzer не инициализирован (требуется Price Monitor)"
        )

    try:
        analysis = await market_analyzer.analyze_market(market_id)

        if not analysis:
            raise HTTPException(status_code=404, detail="Не удалось проанализировать рынок")

        return analysis

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Ошибка при анализе рынка: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/market/random")
async def get_random_market_analysis():
    """
    Выбрать случайный рынок и проанализировать его.
    """
    if not pm_client or not market_analyzer:
        raise HTTPException(
            status_code=500,
            detail="Компоненты не инициализированы"
        )

    try:
        # Read from Market Service cache (no API calls)
        markets = get_cached_markets()
        if not markets:
            raise HTTPException(status_code=404, detail="Нет доступных рынков")

        # Выбираем случайный рынок
        import random
        random_market = random.choice(markets)
        market_id = str(random_market.get("id", ""))

        logger.info("Выбран случайный рынок для анализа: %s", market_id)

        # Анализируем рынок
        analysis = await market_analyzer.analyze_market(market_id)

        if not analysis:
            raise HTTPException(status_code=404, detail="Не удалось проанализировать случайный рынок")

        return analysis

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Ошибка при анализе случайного рынка: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/market/{market_id}")
async def market_detail(request: Request, market_id: str):
    """
    Детальная страница рынка с полной аналитикой.
    """
    return templates.TemplateResponse("market_detail.html", {"request": request})


@app.get("/test")
async def test_page(request: Request):
    """
    Тестовая страница для анализа случайного рынка.
    """
    return templates.TemplateResponse("test.html", {"request": request})


@app.get("/configurations")
async def configurations_page(request: Request):
    """
    Страница настроек системы автоматического входа.
    """
    return templates.TemplateResponse("configurations.html", {"request": request})


@app.get("/statistics")
async def statistics_page(request: Request):
    """
    Страница статистики позиций и результатов торговли.
    """
    return templates.TemplateResponse("statistics.html", {"request": request})


@app.post("/api/clear-statistics")
async def clear_statistics():
    """Очистить все позиции из статистики."""
    try:
        from trading.position import position_storage
        
        # Очистка позиций
        position_storage.clear_all_positions()
        
        # Очистка кэша PriceToBeatService (если доступен)
        try:
            from analysis.price_to_beat_service import price_to_beat_service
            if price_to_beat_service:
                price_to_beat_service.clear_cache()
                logger.info("🧹 Кэш PriceToBeatService очищен")
        except ImportError:
            logger.warning("⚠️ PriceToBeatService не доступен для очистки кэша")
        
        logger.info("✅ Статистика успешно очищена")
        return {"success": True, "message": "Статистика успешно очищена"}
        
    except Exception as e:
        logger.error(f"❌ Ошибка при очистке статистики: {e}")
        return {"success": False, "error": str(e)}


@app.get("/api/statistics")
async def get_statistics(session_pnl: bool = False):
    """Получить полную статистику позиций и результатов торговли."""
    try:
        from trading.position import position_storage, simulation_manager
        from app.config import SIM_MODE

        # Получаем все позиции
        all_positions = position_storage.get_all_positions()
        open_positions = position_storage.get_open_positions()
        closed_positions = position_storage.get_closed_positions()

        # Статистика позиций
        if session_pnl:
            # Используем статистику симуляции (текущая сессия)
            sim_stats = simulation_manager.get_stats()
            stats = {
                'total_positions': sim_stats['total_trades'],
                'open_positions': len(open_positions),
                'closed_positions': sim_stats['total_trades'],
                'total_pnl_usd': sim_stats['total_pnl'],
                'total_trades': sim_stats['total_trades'],
                'winning_trades': sim_stats['winning_trades'],
                'losing_trades': sim_stats['losing_trades'],
                'win_rate': sim_stats['win_rate']
            }
        else:
            # Используем полную статистику всех позиций
            stats = position_storage.get_stats()

        # Статистика симуляции (если в SIM режиме)
        sim_stats = None
        if SIM_MODE:
            sim_stats = simulation_manager.get_stats()

        # Форматируем позиции для таблицы
        def format_position(pos):
            return {
                "position_id": pos.position_id,
                "market_id": pos.market_id,
                "market_title": f"Market {pos.market_id}",  # Показываем только Market ID
                "symbol": pos.symbol,  # Показываем symbol всегда (даже UNKNOWN)
                "side": pos.side,
                "entry_price": f"${pos.entry_price_avg:.4f}" if pos.entry_price_avg else None,
                "total_cost": f"${pos.total_cost_usd:.2f}",
                "status": pos.status,
                "pnl_usd": f"${pos.pnl_usd:.2f}" if pos.pnl_usd else None,
                "pnl_pct": f"{pos.pnl_pct:.1f}%" if pos.pnl_pct else None,
                "entry_reason": pos.entry_reason,
                # Переместили в конец:
                "entry_time": pos.entry_time.strftime("%Y-%m-%d %H:%M") if pos.entry_time else None,
                "exit_time": pos.exit_time.strftime("%Y-%m-%d %H:%M") if pos.exit_time else None,
                "start_price": pos.start_price,  # Price to beat при входе
                "exit_price": f"${pos.exit_price:.4f}" if pos.exit_price else None,
            }

        # Группируем позиции по статусу и сортируем по market_id
        positions_data = {
            "open": [format_position(pos) for pos in sorted(open_positions, key=lambda p: p.market_id)],
            "closed": [format_position(pos) for pos in sorted(closed_positions[-50:], key=lambda p: p.market_id)],  # Последние 50 закрытых
            "all": [format_position(pos) for pos in sorted(all_positions[-100:], key=lambda p: p.market_id)],  # Последние 100 всех
        }

        return {
            "positions": positions_data,
            "stats": stats,
            "sim_stats": sim_stats,
            "mode": "SIM" if SIM_MODE else "REAL",
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as exc:
        logger.error("Ошибка при получении статистики: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/positions")
async def get_positions():
    """Получить открытые позиции."""
    try:
        # Импортируем глобальный position_storage
        from trading.position import position_storage
        from analysis.price_to_beat_service import PriceToBeatService

        # Используем глобальные переменные
        global price_monitor, pm_client

        open_positions = position_storage.get_open_positions()
        closed_positions = position_storage.get_closed_positions()

        logger.info("Получено позиций: открытых=%s, закрытых=%s",
                   len(open_positions), len(closed_positions))

        # Helper: получить start_price с fallback
        async def get_start_price(pos):
            if pos.start_price is not None:
                return pos.start_price
            # Fallback: попробовать получить из PriceToBeatService
            try:
                if not price_monitor or not pm_client:
                    return None
                ptb_service = PriceToBeatService(price_monitor, pm_client)
                return await ptb_service.get_price_to_beat(pos.market_id)
            except Exception as e:
                logger.debug(f"Не удалось получить start_price для позиции {pos.position_id}: {e}")
                return None

        # Подготовить данные с fallback для start_price
        open_data = []
        for pos in open_positions:
            start_price = await get_start_price(pos)
            open_data.append({
                "position_id": pos.position_id,
                "market_id": pos.market_id,
                "market_title": pos.market_title,
                "symbol": pos.symbol,
                "side": pos.side,
                "entry_price_avg": pos.entry_price_avg,
                "total_volume": pos.total_volume,
                "total_cost_usd": pos.total_cost_usd,
                "entry_reason": pos.entry_reason,
                "entry_time": pos.entry_time.isoformat() if pos.entry_time else None,
                "minutes_until_start": pos.minutes_until_start,
                "start_price": start_price,  # С fallback
                "status": pos.status,
            })

        closed_data = []
        for pos in closed_positions[-10:]:  # Последние 10
            start_price = await get_start_price(pos)
            closed_data.append({
                "position_id": pos.position_id,
                "market_id": pos.market_id,
                "market_title": pos.market_title,
                "symbol": pos.symbol,
                "side": pos.side,
                "entry_price_avg": pos.entry_price_avg,
                "total_volume": pos.total_volume,
                "total_cost_usd": pos.total_cost_usd,
                "entry_reason": pos.entry_reason,
                "entry_time": pos.entry_time.isoformat() if pos.entry_time else None,
                "exit_time": pos.exit_time.isoformat() if pos.exit_time else None,
                "start_price": start_price,  # С fallback
                "exit_price": pos.exit_price,
                "pnl_usd": pos.pnl_usd,
                "pnl_pct": pos.pnl_pct,
                "status": pos.status,
            })

        return {
            "open": open_data,
            "closed": closed_data,
        }

    except Exception as exc:
        logger.error("Ошибка при получении позиций: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/stats")
async def get_stats():
    """Получить статистику торговли."""
    if not order_manager:
        raise HTTPException(status_code=500, detail="Order Manager не инициализирован")

    try:
        stats = order_manager.get_stats()
        return stats

    except Exception as exc:
        logger.error("Ошибка при получении статистики: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/balance")
async def get_balance():
    """Получить балансы всех аккаунтов."""
    try:
        balances = []
        total_balance = 0.0
        mode = "SIM" if SIM_MODE else "REAL"

        # Получаем балансы для всех аккаунтов
        for account_num in [1, 2]:
            wallet_address = globals()[f"POLYMARKET_WALLET_ADDRESS_{account_num}"]
            account_type = ACCOUNT_2_TYPE if account_num == 2 else "polymarket"

            if not wallet_address or wallet_address.startswith("0x000"):
                continue

            try:
                balance = 0.0

                if account_type == "web3":
                    # Web3 баланс USDC с блокчейна
                    from app.connectors.web3_balance import web3_balance_checker
                    balance = web3_balance_checker.get_usdc_balance(wallet_address)
                    logger.info("Получен Web3 баланс для аккаунта %s: %.6f USDC", account_num, balance)
                else:
                    # Polymarket Data API баланс
                    import requests
                    data_api_url = "https://data-api.polymarket.com/value"
                    params = {"user": wallet_address}
                    balance_response = requests.get(data_api_url, params=params, timeout=10)

                    if balance_response.status_code == 200:
                        balance_data = balance_response.json()
                        if isinstance(balance_data, list) and len(balance_data) > 0:
                            balance = float(balance_data[0].get("value", 0))
                        elif isinstance(balance_data, dict):
                            balance = float(balance_data.get("value", 0))
                    logger.info("Получен Polymarket баланс для аккаунта %s: %.6f USDC", account_num, balance)

                account_balance = {
                    "account": account_num,
                    "type": account_type,
                    "wallet": f"{wallet_address[:6]}...{wallet_address[-4:]}",
                    "balance": balance,
                    "currency": "USDC"
                }
                balances.append(account_balance)
                total_balance += balance

            except Exception as account_exc:
                logger.warning("Ошибка при получении баланса аккаунта %s: %s", account_num, account_exc)
                balances.append({
                    "account": account_num,
                    "type": account_type,
                    "wallet": f"{wallet_address[:6]}...{wallet_address[-4:]}",
                    "balance": 0.0,
                    "currency": "USDC",
                    "error": str(account_exc)
                })

        return {
            "balances": balances,
            "total_balance": total_balance,
            "mode": mode,
            "currency": "USDC"
        }

    except Exception as exc:
        logger.error("Ошибка при получении балансов: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/config")
async def get_config():
    """Получить текущую конфигурацию."""
    return {
        "sim_mode": SIM_MODE,
        "coins": COINS,
        "initial_balance": SIMULATION_INITIAL_BALANCE,
        "auto_generate_filters": AUTO_GENERATE_FILTERS,
        "gamma_api_tag": GAMMA_API_TAG,
    }


@app.get("/api/auto-entry/config")
async def get_auto_entry_config():
    """Получить настройки системы автоматического входа с описаниями."""
    from app.config import (
        FIRST_POSITION_SIZE_PCT,
        MAX_PRICE_FOR_FIRST_ENTRY,
        ENTER_TO_1H_MARKETS,
        ENTER_TO_15M_MARKETS,
        H1_MARKETS_NUMBER_TO_ENTER,
        M15_MARKETS_NUMBER_TO_ENTER,
        AMOUNT_OF_ONE_BUY_IN_LOOP,
        LOOP_DELAY,
        MATH_PROB_FOR_OPPOSITE,
        PRICE_ENTRY_FOR_OPPOSITE,
        W1_PROFIT_PCT,
        W2_ADDITIONAL_PROFIT_PCT,
        PERCENT_FOR_PRICE_REDUCE,
    )

    return {
        "settings": [
            {
                "key": "FIRST_POSITION_SIZE_PCT",
                "value": FIRST_POSITION_SIZE_PCT,
                "type": "number",
                "description": "Размер первой позиции (% от баланса). Определяет сколько процентов от общего баланса использовать для входа в рынок."
            },
            {
                "key": "MAX_PRICE_FOR_FIRST_ENTRY",
                "value": MAX_PRICE_FOR_FIRST_ENTRY,
                "type": "number",
                "description": "Максимальная цена для входа. Система не будет покупать, если текущая цена выше этого лимита."
            },
            {
                "key": "ENTER_TO_1H_MARKETS",
                "value": ENTER_TO_1H_MARKETS,
                "type": "boolean",
                "description": "Входить ли в часовые рынки (1h). Если включено, система будет рассматривать часовые рынки для автоматического входа."
            },
            {
                "key": "ENTER_TO_15M_MARKETS",
                "value": ENTER_TO_15M_MARKETS,
                "type": "boolean",
                "description": "Входить ли в 15-минутные рынки (15m). Если включено, система будет рассматривать 15-минутные рынки для автоматического входа."
            },
            {
                "key": "H1_MARKETS_NUMBER_TO_ENTER",
                "value": H1_MARKETS_NUMBER_TO_ENTER,
                "type": "number",
                "description": "Максимальное количество часовых рынков для входа за одну сессию. Система выберет топ-N лучших часовых рынков."
            },
            {
                "key": "M15_MARKETS_NUMBER_TO_ENTER",
                "value": M15_MARKETS_NUMBER_TO_ENTER,
                "type": "number",
                "description": "Максимальное количество 15-минутных рынков для входа за одну сессию. Система выберет топ-N лучших 15-минутных рынков."
            },
            {
                "key": "AMOUNT_OF_ONE_BUY_IN_LOOP",
                "value": AMOUNT_OF_ONE_BUY_IN_LOOP,
                "type": "number",
                "description": "Размер одной покупки в цикле ($). Система покупает outcome tokens порциями по этому размеру."
            },
            {
                "key": "LOOP_DELAY",
                "value": LOOP_DELAY,
                "type": "number",
                "description": "Задержка между покупками в цикле (секунды). Определяет как часто система делает последовательные покупки."
            },
            {
                "key": "MATH_PROB_FOR_OPPOSITE",
                "value": MATH_PROB_FOR_OPPOSITE,
                "type": "number",
                "description": "Минимальная математическая вероятность для входа в противоположную сторону после первого входа."
            },
            {
                "key": "PRICE_ENTRY_FOR_OPPOSITE",
                "value": PRICE_ENTRY_FOR_OPPOSITE,
                "type": "number",
                "description": "Максимальная цена для входа в противоположную сторону после первого входа."
            },
            {
                "key": "W1_PROFIT_PCT",
                "value": W1_PROFIT_PCT,
                "type": "number",
                "description": "Минимальная гарантированная прибыль (%) от первого входа при входе в противоположную сторону."
            },
            {
                "key": "W2_ADDITIONAL_PROFIT_PCT",
                "value": W2_ADDITIONAL_PROFIT_PCT,
                "type": "number",
                "description": "Дополнительная прибыль (%) для второго входа в исходную сторону."
            },
            {
                "key": "PERCENT_FOR_PRICE_REDUCE",
                "value": PERCENT_FOR_PRICE_REDUCE,
                "type": "number",
                "description": "Минимальное снижение цены (%) для дополнительного входа в исходную сторону."
            }
        ],
        "schedule": {
            "description": "Система запускает сессии автоматического входа в :13, :28, :43, :58 каждого часа",
            "iterations_per_session": 6,
            "iteration_delay": 30,
            "total_session_time": "3 минуты"
        }
    }


@app.post("/api/auto-entry/config")
async def update_auto_entry_config(config_data: dict):
    """Обновить настройки системы автоматического входа."""
    try:
        # Валидация входных данных
        required_keys = [
            "FIRST_POSITION_SIZE_PCT", "MAX_PRICE_FOR_FIRST_ENTRY",
            "ENTER_TO_1H_MARKETS", "ENTER_TO_15M_MARKETS",
            "H1_MARKETS_NUMBER_TO_ENTER", "M15_MARKETS_NUMBER_TO_ENTER",
            "AMOUNT_OF_ONE_BUY_IN_LOOP", "LOOP_DELAY"
        ]

        for key in required_keys:
            if key not in config_data:
                raise HTTPException(status_code=400, detail=f"Missing required field: {key}")

        # Валидация типов и диапазонов
        if not (0 < config_data["FIRST_POSITION_SIZE_PCT"] <= 100):
            raise HTTPException(status_code=400, detail="FIRST_POSITION_SIZE_PCT must be between 1-100")

        if not (0 < config_data["MAX_PRICE_FOR_FIRST_ENTRY"] <= 1):
            raise HTTPException(status_code=400, detail="MAX_PRICE_FOR_FIRST_ENTRY must be between 0-1")

        if not (0 <= config_data["H1_MARKETS_NUMBER_TO_ENTER"] <= 10):
            raise HTTPException(status_code=400, detail="H1_MARKETS_NUMBER_TO_ENTER must be between 0-10")

        if not (0 <= config_data["M15_MARKETS_NUMBER_TO_ENTER"] <= 10):
            raise HTTPException(status_code=400, detail="M15_MARKETS_NUMBER_TO_ENTER must be between 0-10")

        if not (0.1 <= config_data["AMOUNT_OF_ONE_BUY_IN_LOOP"] <= 100):
            raise HTTPException(status_code=400, detail="AMOUNT_OF_ONE_BUY_IN_LOOP must be between 0.1-100")

        if not (0.1 <= config_data["LOOP_DELAY"] <= 60):
            raise HTTPException(status_code=400, detail="LOOP_DELAY must be between 0.1-60")

        # Обновление настроек в памяти (для демонстрации)
        # В реальном приложении нужно сохранять в файл или базу данных
        logger.info("Обновление настроек авто-входа:")
        for key, value in config_data.items():
            logger.info(f"  {key}: {value}")

        # Возвращаем обновленные настройки
        return {
            "status": "success",
            "message": "Настройки обновлены успешно",
            "settings": config_data
        }

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Ошибка при обновлении настроек: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/auto-entry/test-run")
async def test_run_auto_entry():
    """Ручной запуск тестовой сессии авто-входа."""
    from trading.auto_entry import get_auto_entry_system
    auto_entry_system = get_auto_entry_system()

    if not auto_entry_system:
        raise HTTPException(status_code=500, detail="Auto-entry system не инициализирован")

    try:
        logger.info("🎯 Ручной запуск тестовой сессии авто-входа")
        await auto_entry_system._auto_entry_session()
        return {"status": "Test session completed successfully"}
    except Exception as exc:
        logger.error("Ошибка при ручном запуске сессии: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/market/{market_id}/logs")
async def get_market_logs(market_id: str, after_id: int = 0, limit: int = 200):
    """Логи по конкретному маркету (фильтрация по market_id в тексте сообщения)."""
    limit = min(limit, 500)
    logs = market_log_handler.get_logs_for_market(
        market_id=market_id,
        after_id=after_id,
        limit=limit,
    )
    latest_id = logs[-1]["id"] if logs else after_id
    return {"logs": logs, "latest_id": latest_id, "count": len(logs)}


@app.post("/api/market/{market_id}/enter")
async def manual_enter_market(market_id: str, side: str = "UP"):
    """
    Ручной вход в рынок для тестирования (обходит проверку времени старта).

    Args:
        market_id: ID рынка на Polymarket
        side: Сторона входа ("UP" или "DOWN")
    """
    from trading.auto_entry import get_auto_entry_system
    auto_entry_system = get_auto_entry_system()

    if not auto_entry_system:
        raise HTTPException(status_code=500, detail="Auto-entry system не инициализирован")

    try:
        # Read market from cache (приоритет)
        market_data = get_cached_market_by_id(market_id)

        # Fallback на API если рынка нет в кэше (manual entry)
        if not market_data:
            logger.warning(f"⚠️  Рынок {market_id} не найден в кэше для manual entry, запрашиваем из API")
            market_data = pm_client.get_market_data(market_id)
            if not market_data:
                raise HTTPException(status_code=404, detail="Рынок не найден")

            # Добавляем в кэш для следующих запросов
            add_market_to_cache(market_data)
            logger.info(f"💾 Рынок {market_id} добавлен в кэш после API fallback (manual entry)")

        # Создать объект рынка для входа
        market = {
            "market_id": market_id,
            "title": market_data.get("question", f"Market {market_id}"),
            "recommended_side": side,
            "start_time": datetime.now(timezone.utc)  # Имитируем, что рынок уже стартовал (с timezone)
        }

        logger.info("🎯 Ручной вход в рынок %s (%s)", market_id, side)

        # Запустить процесс входа
        await auto_entry_system._enter_market(market)

        return {
            "status": "Entry process started",
            "market_id": market_id,
            "side": side,
            "message": f"Started entry process for market {market_id} on {side} side"
        }

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Ошибка при ручном входе в рынок %s: %s", market_id, exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/market-indicators")
async def get_market_indicators():
    """Получить текущие индикаторы рынка для BTC/ETH/SOL."""
    if not market_analyzer:
        raise HTTPException(status_code=500, detail="Market Analyzer не инициализирован")

    try:
        indicators = {}
        symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

        for symbol in symbols:
            # Получаем статистику из Price Monitor
            stats = market_analyzer.price_monitor.get_stats(symbol)
            if stats:
                indicators[symbol] = {
                    "price": stats.get("price"),
                    "momentum": stats.get("momentums", {}),
                    "volatility": stats.get("volatility", {}),
                    "timestamp": stats.get("timestamp"),
                }
            else:
                indicators[symbol] = None

        return indicators

    except Exception as exc:
        logger.error("Ошибка при получении индикаторов рынка: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/top-entry-markets")
async def get_top_entry_markets():
    """Получить топ-3 рынков для входа по строгим критериям."""
    try:
        from analysis.market_pre_selector import MarketPreSelector

        # Создаем экземпляр MarketPreSelector
        pre_selector = MarketPreSelector(pm_client, market_analyzer.price_monitor)

        # Ищем рынки, начинающиеся в ближайшее время
        markets_starting_soon = pre_selector.select_markets_starting_soon(minutes_ahead=app_config.best_markets_pre_selector_minutes_ahead)

        # Отбираем лучшие рынки по типам с строгими критериями
        top_markets_by_type = pre_selector.select_best_momentum_markets(
            markets_starting_soon,
            min_score=-10.0,  # Не фильтруем по score, используем строгие критерии
            max_markets=3
        )

        logger.info("Найдено рынков через 0-%s мин: %s",
                   app_config.best_markets_pre_selector_minutes_ahead, len(markets_starting_soon))
        logger.info("Отобрано: 15m=%s, 1h=%s, all=%s",
                   len(top_markets_by_type.get("15m_markets", [])),
                   len(top_markets_by_type.get("1h_markets", [])),
                   len(top_markets_by_type.get("all_markets", [])))

        # Форматируем для API
        def format_markets(markets_list):
            return [
                {
                    "market_id": market["market_id"],
                    "title": market["title"][:80] + "..." if len(market["title"]) > 80 else market["title"],
                    "symbol": market["symbol"],
                    "market_type": market.get("market_type", "unknown"),
                    "momentum_score": round(market["momentum_score"], 3),
                    "trend_direction": market["trend_direction"],
                    "recommended_side": market["recommended_side"],
                    "start_time": market.get("start_time"),
                    "minutes_until_start": round(market.get("minutes_until_start", 0), 1),
                    "current_price": market.get("current_price"),
                    "momentum_data": market.get("momentum_data", {}),
                }
                for market in markets_list
            ]

        # Форматируем все категории
        formatted_15m = format_markets(top_markets_by_type.get("15m_markets", []))
        formatted_1h = format_markets(top_markets_by_type.get("1h_markets", []))
        formatted_all = format_markets(top_markets_by_type.get("all_markets", []))

        # Если нет отобранных рынков, возвращаем демо-данные для демонстрации UI
        if not formatted_15m and not formatted_1h and not formatted_all:
            logger.info("Нет отобранных рынков, возвращаем демо-данные для демонстрации")
            demo_markets = [
                {
                    "market_id": "demo_1",
                    "title": "Demo BTC Market - Sample Entry Opportunity",
                    "symbol": "BTC",
                    "market_type": "15m",
                    "momentum_score": 0.75,
                    "trend_direction": "BULLISH",
                    "recommended_side": "UP",
                    "start_time": datetime.now().isoformat(),
                    "minutes_until_start": 15,
                    "current_price": 45000.50,
                    "momentum_data": {
                        "1m": 0.5,
                        "5m": 0.8,
                        "15m": 0.6,
                        "1h": 0.7
                    }
                },
                {
                    "market_id": "demo_2",
                    "title": "Demo ETH Market - Sample Entry Opportunity",
                    "symbol": "ETH",
                    "market_type": "1h",
                    "momentum_score": 0.62,
                    "trend_direction": "BEARISH",
                    "recommended_side": "DOWN",
                    "start_time": datetime.now().isoformat(),
                    "minutes_until_start": 8,
                    "current_price": 2800.75,
                    "momentum_data": {
                        "1m": -0.3,
                        "5m": -0.5,
                        "15m": -0.4,
                        "1h": -0.6
                    }
                },
                {
                    "market_id": "demo_3",
                    "title": "Demo SOL Market - Sample Entry Opportunity",
                    "symbol": "SOL",
                    "market_type": "15m",
                    "momentum_score": 0.88,
                    "trend_direction": "BULLISH",
                    "recommended_side": "UP",
                    "start_time": datetime.now().isoformat(),
                    "minutes_until_start": 22,
                    "current_price": 95.25,
                    "momentum_data": {
                        "1m": 0.9,
                        "5m": 0.8,
                        "15m": 0.9,
                        "1h": 0.7
                    }
                }
            ]

            # Разделяем демо-данные по типам
            formatted_15m = [m for m in demo_markets if m["market_type"] == "15m"]
            formatted_1h = [m for m in demo_markets if m["market_type"] == "1h"]
            formatted_all = demo_markets[:3]  # Первые 3 для all

        return {
            "15m_markets": formatted_15m,
            "1h_markets": formatted_1h,
            "all_markets": formatted_all,
            "total_found": len(markets_starting_soon),
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as exc:
        logger.error("Ошибка при получении топ-рынков для входа: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/order/buy")
async def place_buy_order(
    market_id: str,
    side: str,
    amount: float,
    price: float,
):
    """
    Разместить ордер на покупку.
    
    Args:
        market_id: ID рынка
        side: "UP" или "DOWN"
        amount: Сумма в USDC
        price: Лимитная цена
    """
    if not order_manager:
        raise HTTPException(status_code=500, detail="Order Manager не инициализирован")
    
    try:
        result = order_manager.buy_outcome(
            market_id=market_id,
            side=side,
            amount_usdc=amount,
            price=price,
        )
        
        return result
        
    except Exception as exc:
        logger.error("Ошибка при создании BUY ордера: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/order/test_buy")
async def test_buy_order(
    market_id: str,
    side: str,
    amount: float,
    price: float,
):
    """
    Разместить РЕАЛЬНЫЙ тестовый ордер на покупку (минуя SIM_MODE).

    Используется для тестирования подключения к Polymarket API.
    """
    if not pm_client:
        raise HTTPException(status_code=500, detail="Polymarket клиент не инициализирован")

    try:
        outcome = 0 if side.upper() == "UP" else 1
        logger.info(
            "🧪 Test BUY order: market_id=%s, side=%s, outcome=%d, amount=$%.2f, price=%.4f",
            market_id, side.upper(), outcome, amount, price,
        )

        order = pm_client.buy_outcome(
            market_id=market_id,
            outcome=outcome,
            amount_usdc=amount,
            max_price=price,
        )

        success = order is not None
        if success:
            logger.info("✅ Test BUY order placed successfully: %s", order)
        else:
            logger.warning("❌ Test BUY order returned None")

        return {
            "success": success,
            "mode": "REAL",
            "side": side.upper(),
            "amount": amount,
            "price": price,
            "order": order,
        }

    except Exception as exc:
        logger.error("Ошибка при создании тестового BUY ордера: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/order/sell")
async def place_sell_order(
    market_id: str,
    side: str,
    amount: float,
    price: float,
):
    """Разместить ордер на продажу."""
    if not order_manager:
        raise HTTPException(status_code=500, detail="Order Manager не инициализирован")

    try:
        result = order_manager.sell_outcome(
            market_id=market_id,
            side=side,
            amount_usdc=amount,
            price=price,
        )

        return result

    except Exception as exc:
        logger.error("Ошибка при создании SELL ордера: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/collector/status")
async def get_collector_status():
    """Получить статус коллектора."""
    try:
        status = collector_monitor.get_status()
        return status
    except Exception as exc:
        logger.error("Ошибка при получении статуса коллектора: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/collector/restart")
async def restart_collector():
    """Перезапустить коллектор вручную."""
    try:
        result = await collector_monitor.manual_restart()
        return result
    except Exception as exc:
        logger.error("Ошибка при перезапуске коллектора: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))



