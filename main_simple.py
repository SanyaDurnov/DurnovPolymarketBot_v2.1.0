"""
Simple main script для тестирования Web UI.
"""

import argparse
import logging
import sys

from app import config

# Настройка логирования
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def web_mode_simple():
    """Простой режим Web UI: запуск FastAPI сервера без сложной инициализации."""
    logger.info("=" * 60)
    logger.info("ЗАПУСК ПРОСТОГО WEB UI")
    logger.info("=" * 60)

    try:
        import uvicorn
        from web.app_simple import app

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
    """Главная функция."""
    parser = argparse.ArgumentParser(description="Polymarket Bot V2 - Simple")
    parser.add_argument("--mode", choices=["web"], default="web", help="Режим работы")

    args = parser.parse_args()

    logger.info("Polymarket Bot V2 - Simple Mode")
    logger.info("Режим: %s", args.mode)
    logger.info("")

    try:
        if args.mode == "web":
            return web_mode_simple()
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