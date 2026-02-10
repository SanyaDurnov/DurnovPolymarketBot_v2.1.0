"""
Тест выбора стратегий - проверка импорта и настроек.
"""

import logging
from app import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_strategy_selection():
    """Проверить выбор стратегии."""
    logger.info("=" * 60)
    logger.info("ТЕСТ ВЫБОРА СТРАТЕГИИ")
    logger.info("=" * 60)

    # Проверка текущей настройки
    current_strategy = config.TRADING_STRATEGY
    logger.info(f"Текущая стратегия: {current_strategy}")

    # Проверка импорта стандартной стратегии
    try:
        from trading.position_manager import (
            PositionManager,
            create_position_manager,
            get_position_manager,
            stop_all_position_managers
        )
        logger.info("✅ Стандартная стратегия (position_manager.py) импортирована")
        logger.info(f"   - Класс: {PositionManager.__name__}")
        logger.info(f"   - Функции: create_position_manager, get_position_manager, stop_all_position_managers")
    except Exception as exc:
        logger.error(f"❌ Ошибка импорта стандартной стратегии: {exc}")

    # Проверка импорта soft trading стратегии
    try:
        from trading.position_manager_soft_trading import (
            PositionManagerSoftTrading,
            create_position_manager_soft,
            get_position_manager_soft,
            stop_all_position_managers_soft
        )
        logger.info("✅ Soft Trading стратегия (position_manager_soft_trading.py) импортирована")
        logger.info(f"   - Класс: {PositionManagerSoftTrading.__name__}")
        logger.info(f"   - Функции: create_position_manager_soft, get_position_manager_soft, stop_all_position_managers_soft")
    except Exception as exc:
        logger.error(f"❌ Ошибка импорта soft trading стратегии: {exc}")

    # Проверка авто-входа
    try:
        from trading.auto_entry import AutoEntrySystem, init_auto_entry_system
        logger.info("✅ Auto Entry System импортирована")
        logger.info(f"   - Использует настройку TRADING_STRATEGY: {current_strategy}")
    except Exception as exc:
        logger.error(f"❌ Ошибка импорта auto_entry: {exc}")

    logger.info("=" * 60)
    logger.info("РЕКОМЕНДАЦИИ ПО ИСПОЛЬЗОВАНИЮ:")
    logger.info("=" * 60)

    if current_strategy == "default":
        logger.info("📋 Активна СТАНДАРТНАЯ стратегия:")
        logger.info("   - Работает с auto_entry")
        logger.info("   - Автоматический вход за минуту до старта")
        logger.info("   - Агрессивное хеджирование")
        logger.info("\nДля переключения на Soft Trading:")
        logger.info("   1. В config.py: TRADING_STRATEGY = 'soft_trading'")
        logger.info("   2. Или в .env: TRADING_STRATEGY=soft_trading")

    elif current_strategy == "soft_trading":
        logger.info("📋 Активна SOFT TRADING стратегия:")
        logger.info("   - Работает БЕЗ auto_entry")
        logger.info("   - Более консервативный подход")
        logger.info("   - Гибкие параметры")
        logger.info("\nДля переключения на стандартную:")
        logger.info("   1. В config.py: TRADING_STRATEGY = 'default'")
        logger.info("   2. Или в .env: TRADING_STRATEGY=default")

    else:
        logger.warning(f"⚠️ Неизвестная стратегия: {current_strategy}")
        logger.warning("   Используйте 'default' или 'soft_trading'")

    logger.info("=" * 60)
    logger.info("ТЕСТ ЗАВЕРШЕН")
    logger.info("=" * 60)


if __name__ == "__main__":
    test_strategy_selection()
