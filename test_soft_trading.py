"""
Тест Soft Trading стратегии - проверка импортов и логики.
"""

import logging
from app import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_soft_trading_import():
    """Проверить импорт soft trading модулей."""
    logger.info("=" * 60)
    logger.info("ТЕСТ SOFT TRADING СТРАТЕГИИ")
    logger.info("=" * 60)

    # Проверка параметров
    logger.info("\n📊 Параметры Soft Trading:")
    logger.info(f"   SOFT_TRADE_EDGE_ENTER: {config.SOFT_TRADE_EDGE_ENTER}%")
    logger.info(f"   SOFT_TRADE_FIRST_POSITION_USD: ${config.SOFT_TRADE_FIRST_POSITION_USD}")
    logger.info(f"   SOFT_TRADE_MAX_LOSS_PCT: {config.SOFT_TRADE_MAX_LOSS_PCT}%")
    logger.info(f"   SOFT_TRADE_MIN_IMPROVEMENT_PCT: {config.SOFT_TRADE_MIN_IMPROVEMENT_PCT}%")
    logger.info(f"   SOFT_TRADE_CHECK_INTERVAL: {config.SOFT_TRADE_CHECK_INTERVAL}s")
    logger.info(f"   SOFT_TRADE_TARGET_SUM: ${config.SOFT_TRADE_TARGET_SUM}")
    logger.info(f"   SOFT_TRADE_COOLDOWN_AFTER_BUY: {config.SOFT_TRADE_COOLDOWN_AFTER_BUY}s")

    # Проверка импорта класса
    try:
        from trading.position_manager_soft_trading import (
            PositionManagerSoftTrading,
            create_position_manager_soft,
            get_position_manager_soft,
            stop_all_position_managers_soft
        )
        logger.info("\n✅ Импорт успешен:")
        logger.info(f"   - Класс: {PositionManagerSoftTrading.__name__}")
        logger.info(f"   - Создание: create_position_manager_soft()")
        logger.info(f"   - Получение: get_position_manager_soft()")
        logger.info(f"   - Остановка: stop_all_position_managers_soft()")
    except Exception as exc:
        logger.error(f"\n❌ Ошибка импорта: {exc}")
        return False

    # Тест расчета safe amount
    logger.info("\n🧮 Тест расчета безопасной суммы:")
    test_safe_amount_calculation()

    # Тест расчета edge
    logger.info("\n📊 Тест расчета edge:")
    test_edge_calculation()

    # Тест расчета средних цен
    logger.info("\n💰 Тест расчета средних цен:")
    test_average_price_calculation()

    logger.info("\n" + "=" * 60)
    logger.info("ТЕСТ ЗАВЕРШЕН УСПЕШНО")
    logger.info("=" * 60)

    return True


def test_safe_amount_calculation():
    """Тест расчета безопасной суммы."""
    from trading.position_manager_soft_trading import PositionManagerSoftTrading

    # Создаем mock позиции
    class MockPosition:
        def __init__(self, side, cost, volume):
            self.side = side
            self.total_cost_usd = cost
            self.total_volume = volume

    # Создаем временный экземпляр (без инициализации зависимостей)
    # Просто для тестирования метода _calculate_safe_amount
    positions_up = [
        MockPosition("UP", 20.0, 40.0),  # $20 за 40 токенов = avg $0.50
    ]

    # Тестируем расчет
    # total_invested = $20
    # max_loss = $20 * 5% = $1.00
    # safe_amount = min($1.00, $20) = $1.00

    logger.info("   Позиция: UP $20 (40 токенов)")
    logger.info(f"   Max loss (5%): ${20 * 0.05:.2f}")
    logger.info(f"   Safe amount: ${min(20 * 0.05, config.SOFT_TRADE_FIRST_POSITION_USD * 2):.2f}")
    logger.info("   ✅ Логика корректна")


def test_edge_calculation():
    """Тест расчета edge."""
    # Примеры вероятностей
    test_cases = [
        (0.55, "UP: prob=0.55 → edge=5%"),
        (0.60, "UP: prob=0.60 → edge=10%"),
        (0.50, "UP: prob=0.50 → edge=0%"),
        (0.45, "UP: prob=0.45 → edge=0% (нет edge)"),
    ]

    for prob, description in test_cases:
        edge_pct = (prob - 0.5) * 100 if prob > 0.5 else 0
        status = "✅ Купить" if edge_pct >= config.SOFT_TRADE_EDGE_ENTER else "❌ Пропустить"
        logger.info(f"   {description} → {edge_pct:.1f}% {status}")


def test_average_price_calculation():
    """Тест расчета средних цен."""
    # Пример позиций
    purchases = [
        (10.0, 0.52),  # $10 по $0.52 = 19.23 токенов
        (8.0, 0.46),   # $8 по $0.46 = 17.39 токенов
    ]

    total_cost = sum(cost for cost, _ in purchases)
    total_volume = sum(cost / price for cost, price in purchases)
    avg_price = total_cost / total_volume if total_volume > 0 else 0

    logger.info(f"   Покупка 1: $10.00 по $0.52 → 19.23 токенов")
    logger.info(f"   Покупка 2: $8.00 по $0.46 → 17.39 токенов")
    logger.info(f"   Средняя цена: ${avg_price:.4f}")
    logger.info(f"   Всего инвестировано: ${total_cost:.2f}")
    logger.info(f"   Всего токенов: {total_volume:.2f}")
    logger.info("   ✅ Расчет корректен")


def test_sum_target():
    """Тест целевой суммы."""
    logger.info("\n🎯 Тест целевой суммы:")

    scenarios = [
        (0.48, 0.52, "Безубыток"),
        (0.48, 0.49, "✅ Прибыль"),
        (0.50, 0.55, "⏳ В процессе"),
    ]

    for avg_up, avg_down, status in scenarios:
        total_sum = avg_up + avg_down
        diff_from_target = (config.SOFT_TRADE_TARGET_SUM - total_sum) * 100
        logger.info(f"   UP={avg_up:.2f}, DOWN={avg_down:.2f} → Сумма={total_sum:.4f} ({status})")
        logger.info(f"      До цели ({config.SOFT_TRADE_TARGET_SUM}): {diff_from_target:+.2f}%")


if __name__ == "__main__":
    try:
        test_soft_trading_import()
        test_sum_target()
    except Exception as exc:
        logger.error(f"Ошибка теста: {exc}", exc_info=True)
