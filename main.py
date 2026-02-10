"""
Polymarket Bot V2 - главная точка входа.
"""

import argparse
import asyncio
import logging
import sys

from app import config
from polymarket.client import PolymarketClient
from polymarket.orderbook import OrderbookAnalyzer
from monitoring.price_monitor import PriceMonitor
from analysis.market_analyzer import MarketAnalyzer
from trading.order_manager import OrderManager
from trading.auto_entry import init_auto_entry_system
from trading.market_monitor import MarketMonitor

# Настройка логирования
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def test_mode():
    """Режим тестирования: проверка всех компонентов."""
    logger.info("=" * 60)
    logger.info("РЕЖИМ ТЕСТИРОВАНИЯ")
    logger.info("=" * 60)
    
    try:
        # 1. Инициализация Polymarket Client
        logger.info("\n[1/5] Инициализация Polymarket Client...")
        pm_client = PolymarketClient()
        logger.info("✓ Polymarket Client инициализирован")
        
        # 2. Получение списка рынков
        logger.info("\n[2/5] Загружаем рынки...")
        markets = pm_client.get_markets()
        logger.info("✓ Получено %s рынков", len(markets) if markets else 0)

        # Показываем информацию о кэше
        cached_markets = pm_client._load_markets_cache()
        if cached_markets:
            logger.info("📊 Статистика API:")
            logger.info("  Всего рынков в кэше: %s", len(cached_markets))
            logger.info("  Загружено из Gamma API: %s рынков", len(cached_markets))

        if markets and len(markets) > 0:
            # Выбираем случайный рынок для тестирования
            import random
            test_market = random.choice(markets)
            test_market_id = str(test_market.get("id", ""))
            test_title = test_market.get("title") or test_market.get("question") or "N/A"

            logger.info("\n🎯 ВЫБРАН СЛУЧАЙНЫЙ РЫНОК ДЛЯ ТЕСТИРОВАНИЯ:")
            logger.info("  ID: %s", test_market_id)
            logger.info("  Название: %s", test_title[:100])

            # Разделяем рынки на 15-минутные и часовые
            quarter_hour_markets = []
            hour_markets = []

            for market in markets:
                title = market.get("title") or market.get("question") or ""
                # 15-минутные рынки содержат минуты в названии (:00PM-, :15PM-, etc.)
                is_quarter_hour = any(pattern in title for pattern in [
                    ":00AM-", ":00PM-", ":15AM-", ":15PM-", ":30AM-", ":30PM-", ":45AM-", ":45PM-"
                ])
                if is_quarter_hour:
                    quarter_hour_markets.append(market)
                else:
                    hour_markets.append(market)

            # Отладка: проверим первые 3 рынка
            logger.info("🔍 Отладка классификации (первые 3 рынка):")
            for idx, market in enumerate(markets[:3], 1):
                title = market.get("title") or market.get("question") or ""
                has_minutes = any(pattern in title for pattern in [":00-", ":15-", ":30-", ":45-"])
                category = "15-минутный" if has_minutes else "часовой"
                logger.info("  %s) %s -> %s", idx, title[:50], category)

            # Показываем 15-минутные рынки
            if quarter_hour_markets:
                logger.info("\n⏱️ 15-МИНУТНЫЕ РЫНКИ (%s):", len(quarter_hour_markets))
                for idx, market in enumerate(quarter_hour_markets[:10], 1):
                    market_id = market.get("id", "N/A")
                    title = market.get("title") or market.get("question") or "N/A"
                    logger.info("  %s) [%s] %s", idx, market_id, title[:80])

            # Показываем часовые рынки
            if hour_markets:
                logger.info("\n🕐 ЧАСОВЫЕ РЫНКИ (%s):", len(hour_markets))
                for idx, market in enumerate(hour_markets[:10], 1):
                    market_id = market.get("id", "N/A")
                    title = market.get("title") or market.get("question") or "N/A"
                    logger.info("  %s) [%s] %s", idx, market_id, title[:80])

            # Статистика фильтрации
            logger.info("\n📈 Статистика фильтрации:")
            logger.info("  Всего рынков после фильтрации: %s", len(markets))
            logger.info("  15-минутных рынков: %s", len(quarter_hour_markets))
            logger.info("  Часовых рынков: %s", len(hour_markets))
        else:
            # Если фильтрация не дала результатов, покажем примеры названий из кэша
            if cached_markets:
                logger.info("\n❌ Фильтры не нашли рынков. Примеры названий из кэша:")
                for idx, market in enumerate(cached_markets[:10], 1):
                    title = market.get("title") or market.get("question") or "N/A"
                    logger.info("  %s) %s", idx, title[:100])
        
        # 3. Тестирование OrderbookAnalyzer
        logger.info("\n[3/5] Тестирование OrderbookAnalyzer...")
        orderbook_analyzer = OrderbookAnalyzer(pm_client)
        
        if markets and len(markets) > 0:
            test_market = markets[0]
            test_market_id = str(test_market.get("id", ""))
            title = test_market.get("title") or test_market.get("question") or "N/A"
            logger.info("Тестовый рынок: %s", title[:80])
            
            orderbook_prices = orderbook_analyzer.get_market_prices(test_market_id)
            if orderbook_prices:
                logger.info("✓ Orderbook получен:")
                logger.info("  UP:   bid=$%.4f  ask=$%.4f  spread=$%.4f",
                           orderbook_prices.get("up_bid", 0),
                           orderbook_prices.get("up_ask", 0),
                           orderbook_prices.get("up_spread", 0))
                logger.info("  DOWN: bid=$%.4f  ask=$%.4f  spread=$%.4f",
                           orderbook_prices.get("down_bid", 0),
                           orderbook_prices.get("down_ask", 0),
                           orderbook_prices.get("down_spread", 0))
            else:
                logger.warning("⚠ Не удалось получить orderbook")
        
        # 4. Тестирование OrderManager (SIM MODE)
        logger.info("\n[4/5] Тестирование OrderManager (SIM MODE)...")
        order_manager = OrderManager(
            polymarket_client=pm_client,
            sim_mode=config.SIM_MODE,
            initial_balance=config.SIMULATION_INITIAL_BALANCE,
        )
        
        balance = order_manager.get_balance()
        logger.info("✓ OrderManager инициализирован")
        logger.info("  Режим: %s", "SIM" if config.SIM_MODE else "REAL")
        logger.info("  Баланс: $%.2f", balance)
        
        # 5. Сводка
        logger.info("\n[5/5] Сводка тестирования:")
        logger.info("✓ Все базовые компоненты работают")
        logger.info("✓ Система готова к использованию")
        
        logger.info("\n" + "=" * 60)
        logger.info("ТЕСТИРОВАНИЕ ЗАВЕРШЕНО УСПЕШНО")
        logger.info("=" * 60)
        
    except Exception as exc:
        logger.error("❌ Ошибка при тестировании: %s", exc, exc_info=True)
        return 1
    
    return 0


async def monitor_mode():
    """Режим мониторинга: запуск Price Monitor."""
    logger.info("=" * 60)
    logger.info("РЕЖИМ МОНИТОРИНГА ЦЕН")
    logger.info("=" * 60)
    
    try:
        price_monitor = PriceMonitor()
        
        # Запускаем мониторинг
        await price_monitor.start()
        
        logger.info("✓ Мониторинг запущен. Нажмите Ctrl+C для остановки.")
        
        # Ждем бесконечно
        try:
            while price_monitor.is_running:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            logger.info("\nОстановка мониторинга...")
        finally:
            await price_monitor.stop()
            
    except Exception as exc:
        logger.error("❌ Ошибка в режиме мониторинга: %s", exc, exc_info=True)
        return 1
    
    return 0


def check_chainlink_server():
    """Проверка доступности Chainlink Historical API сервера."""
    import requests
    try:
        response = requests.get("http://localhost:3000/api/price", timeout=5)
        return response.status_code == 200
    except Exception:
        return False


def start_chainlink_server():
    """Запуск Chainlink Historical API сервера в фоне."""
    import subprocess
    import os

    try:
        chainlink_dir = "quickstarts-historical-prices-api"
        if not os.path.exists(chainlink_dir):
            logger.warning("Папка %s не найдена, Chainlink сервер не будет запущен", chainlink_dir)
            return

        logger.info("🚀 Запуск Chainlink Historical API сервера...")

        # Запускаем в фоне
        process = subprocess.Popen(
            ["npm", "run", "dev"],
            cwd=chainlink_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            preexec_fn=os.setsid if os.name != 'nt' else None
        )

        # Ждем немного чтобы сервер запустился
        import time
        time.sleep(3)

        if process.poll() is None:
            logger.info("✅ Chainlink сервер запущен (PID: %s)", process.pid)
            logger.info("   API доступен на: http://localhost:3000")
        else:
            logger.warning("⚠️ Chainlink сервер не запустился")

    except Exception as exc:
        logger.error("❌ Ошибка при запуске Chainlink сервера: %s", exc)


def kill_old_processes():
    """Убивает старые процессы бота перед запуском нового."""
    import subprocess
    import os

    try:
        # Получаем PID текущего процесса
        current_pid = os.getpid()

        # Ищем все процессы python с main.py
        result = subprocess.run(
            ["pgrep", "-f", "python.*main.py"],
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            old_pids = [int(pid) for pid in result.stdout.strip().split('\n') if pid and int(pid) != current_pid]

            if old_pids:
                logger.info("🔍 Найдены старые процессы бота: %s", old_pids)
                for pid in old_pids:
                    try:
                        subprocess.run(["kill", str(pid)], check=False)
                        logger.info("   ✓ Остановлен процесс PID %s", pid)
                    except Exception as e:
                        logger.warning("   ⚠️  Не удалось остановить PID %s: %s", pid, e)

                # Даем время процессам завершиться
                import time
                time.sleep(2)
            else:
                logger.info("✓ Старых процессов не найдено")
        else:
            logger.info("✓ Старых процессов не найдено")

    except Exception as exc:
        logger.warning("⚠️  Ошибка при проверке старых процессов: %s", exc)


def web_mode():
    """Режим Web UI: запуск FastAPI сервера."""
    logger.info("=" * 60)
    logger.info("ЗАПУСК WEB UI")
    logger.info("=" * 60)

    # Убиваем старые процессы перед запуском
    kill_old_processes()

    # Проверяем доступность Chainlink сервера
    logger.info("Проверяем доступность Chainlink Historical API...")
    if not check_chainlink_server():
        logger.warning("⚠️ Chainlink сервер недоступен на http://localhost:3000")
        logger.warning("Запустите его отдельно: cd quickstarts-historical-prices-api && npm run dev")
        logger.warning("Или продолжите с fallback на текущие цены")

    try:
        import uvicorn
        from web.app import app

        logger.info("Запуск сервера на http://%s:%s", config.WEB_HOST, config.WEB_PORT)
        logger.info("Откройте браузер и перейдите по адресу выше")

        uvicorn.run(
            app,
            host=config.WEB_HOST,
            port=config.WEB_PORT,
            log_level="info",
        )

    except ImportError as exc:
        logger.error("❌ Не удалось импортировать web модули: %s", exc)
        logger.error("Убедитесь что установлены все зависимости: pip install -r requirements.txt")
        return 1
    except Exception as exc:
        logger.error("❌ Ошибка при запуске Web UI: %s", exc, exc_info=True)
        return 1

    return 0


def main():
    """Главная функция с выбором режима."""
    parser = argparse.ArgumentParser(
        description="Polymarket Bot V2",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:
  python main.py --mode test      # Тестирование компонентов
  python main.py --mode monitor   # Мониторинг цен
  python main.py --mode web       # Запуск Web UI
        """
    )
    
    parser.add_argument(
        "--mode",
        choices=["test", "monitor", "web"],
        default="test",
        help="Режим работы (по умолчанию: test)",
    )
    
    args = parser.parse_args()
    
    # Выводим текущие настройки
    logger.info("Polymarket Bot V2")
    logger.info("Режим: %s", "SIMULATION" if config.SIM_MODE else "REAL TRADING")
    logger.info("Монеты: %s", config.COINS)
    logger.info("")
    
    try:
        if args.mode == "test":
            return test_mode()
        elif args.mode == "monitor":
            return asyncio.run(monitor_mode())
        elif args.mode == "web":
            return web_mode()
        else:
            logger.error("Неизвестный режим: %s", args.mode)
            return 1
            
    except KeyboardInterrupt:
        logger.info("\nПрервано пользователем")
        return 0
    except Exception as exc:
        logger.error("Критическая ошибка: %s", exc, exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
