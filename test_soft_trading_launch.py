"""
Тест запуска Soft Trading стратегии через web app.
"""

import logging
import sys
import os

# Добавляем путь к проекту
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_soft_trading_launch():
    """Тест логики выбора стратегии."""
    logger.info("=" * 60)
    logger.info("ТЕСТ ЗАПУСКА SOFT TRADING")
    logger.info("=" * 60)

    # Проверка текущей стратегии
    strategy = config.TRADING_STRATEGY
    logger.info(f"\n📊 Текущая стратегия: {strategy}")

    # Проверка импортов
    logger.info("\n🔍 Проверка импортов...")

    try:
        from web.app import app
        logger.info("✅ web.app импортирован")
    except Exception as exc:
        logger.error(f"❌ Ошибка импорта web.app: {exc}")
        return False

    try:
        from trading.position_manager_soft_trading import (
            create_position_manager_soft,
            stop_all_position_managers_soft
        )
        logger.info("✅ Soft trading модули импортированы")
    except Exception as exc:
        logger.error(f"❌ Ошибка импорта soft trading: {exc}")
        return False

    # Проверка логики выбора
    logger.info("\n🎯 Логика выбора стратегии:")

    if strategy == "soft_trading":
        logger.info("   ✅ Будет запущена SOFT TRADING стратегия")
        logger.info("   📊 Менеджеры будут созданы для активных рынков")
        logger.info("   🌙 Без auto_entry системы")
    elif strategy == "default":
        logger.info("   ✅ Будет запущена DEFAULT стратегия")
        logger.info("   📊 Auto-entry система")
        logger.info("   🎯 Position manager для хеджирования")
    else:
        logger.error(f"   ❌ Неизвестная стратегия: {strategy}")
        return False

    # Проверка параметров soft trading
    if strategy == "soft_trading":
        logger.info("\n⚙️ Параметры Soft Trading:")
        logger.info(f"   EDGE_ENTER: {config.SOFT_TRADE_EDGE_ENTER}%")
        logger.info(f"   FIRST_POSITION: ${config.SOFT_TRADE_FIRST_POSITION_USD}")
        logger.info(f"   MAX_LOSS: {config.SOFT_TRADE_MAX_LOSS_PCT}%")
        logger.info(f"   MIN_IMPROVEMENT: {config.SOFT_TRADE_MIN_IMPROVEMENT_PCT}%")
        logger.info(f"   CHECK_INTERVAL: {config.SOFT_TRADE_CHECK_INTERVAL}s")
        logger.info(f"   TARGET_SUM: ${config.SOFT_TRADE_TARGET_SUM}")
        logger.info(f"   COOLDOWN: {config.SOFT_TRADE_COOLDOWN_AFTER_BUY}s")

    logger.info("\n" + "=" * 60)
    logger.info("ТЕСТ ЗАВЕРШЕН УСПЕШНО")
    logger.info("=" * 60)

    # Инструкции
    logger.info("\n📚 Следующие шаги:")
    logger.info("   1. Убедитесь что TRADING_STRATEGY установлена правильно:")
    logger.info("      В .env: TRADING_STRATEGY=soft_trading")
    logger.info("      Или в config.py: TRADING_STRATEGY = 'soft_trading'")
    logger.info("")
    logger.info("   2. Запустите web приложение:")
    logger.info("      python main.py --mode web")
    logger.info("")
    logger.info("   3. Проверьте логи при запуске:")
    logger.info("      - Должно быть: '📊 Выбранная стратегия: soft_trading'")
    logger.info("      - Должно быть: '🌙 Запуск SOFT TRADING стратегии...'")
    logger.info("      - Должно быть: '✅ Запущен soft trading для рынка ...'")
    logger.info("")
    logger.info("   4. В логах каждые 5 секунд будет статус:")
    logger.info("      '📊 СТАТУС SOFT TRADING MANAGER'")

    return True


def test_strategy_switch():
    """Тест переключения стратегии."""
    logger.info("\n" + "=" * 60)
    logger.info("ТЕСТ ПЕРЕКЛЮЧЕНИЯ СТРАТЕГИИ")
    logger.info("=" * 60)

    logger.info("\nДля переключения на soft_trading:")
    logger.info("   1. Остановите приложение (Ctrl+C)")
    logger.info("   2. Измените .env: TRADING_STRATEGY=soft_trading")
    logger.info("   3. Или измените config.py: TRADING_STRATEGY = 'soft_trading'")
    logger.info("   4. Запустите снова: python main.py --mode web")

    logger.info("\nДля переключения на default:")
    logger.info("   1. Остановите приложение (Ctrl+C)")
    logger.info("   2. Измените .env: TRADING_STRATEGY=default")
    logger.info("   3. Или измените config.py: TRADING_STRATEGY = 'default'")
    logger.info("   4. Запустите снова: python main.py --mode web")

    logger.info("\n⚠️ Важно:")
    logger.info("   - Перед переключением остановите приложение")
    logger.info("   - Убедитесь что нет активных позиций")
    logger.info("   - Проверьте логи на ошибки")


if __name__ == "__main__":
    try:
        test_soft_trading_launch()
        test_strategy_switch()
    except Exception as exc:
        logger.error(f"Ошибка теста: {exc}", exc_info=True)
