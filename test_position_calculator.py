"""
Тесты для Position Calculator.

Проверяет правильность расчетов сумм входа в позиции.
"""

import unittest
from unittest.mock import Mock

from app.config import W1_PROFIT_PCT, W2_ADDITIONAL_PROFIT_PCT
from trading.position_calculator import PositionCalculator
from trading.position import Position


class TestPositionCalculator(unittest.TestCase):
    """Тесты для PositionCalculator."""

    def test_calculate_opposite_entry_amount(self):
        """Тест расчета суммы для противоположной позиции."""
        # Тестовый случай из примера пользователя:
        # Вход DOWN: 100$ по 0.5
        # Нужно гарантировать 20% прибыль = 20$
        # Цена UP: 0.35
        # Расчет: opposite_amount = (20 + 100) / (1/0.35 - 1) = 120 / (2.857 - 1) = 120 / 1.857 ≈ 64.62

        initial_amount = 100.0
        initial_price = 0.5
        opposite_price = 0.35

        result = PositionCalculator.calculate_opposite_entry_amount(
            initial_amount, initial_price, opposite_price
        )

        # Проверяем что результат положительный и разумный
        self.assertGreater(result, 0)
        self.assertLess(result, initial_amount * 3)  # Не больше 3x от первоначального

        print(f"Opposite entry amount: ${result:.2f}")

    def test_calculate_additional_entry_amount(self):
        """Тест расчета суммы для дополнительного входа."""
        # Создаем тестовые позиции
        initial_position = Position(
            position_id="test_initial",
            market_id="test_market",
            market_title="Test Market",
            symbol="TEST",
            side="DOWN",
            entry_time=None,
            entry_price_avg=0.5,
            total_volume=200,  # 100$ / 0.5
            total_cost_usd=100.0,
            entry_reason="INITIAL_ENTRY"
        )

        opposite_position = Position(
            position_id="test_opposite",
            market_id="test_market",
            market_title="Test Market",
            symbol="TEST",
            side="UP",
            entry_time=None,
            entry_price_avg=0.35,
            total_volume=78 / 0.35,  # объем для 78$
            total_cost_usd=78.0,
            entry_reason="OPPOSITE_ENTRY"
        )

        positions = [initial_position, opposite_position]
        current_price = 0.4  # Текущая цена DOWN

        result = PositionCalculator.calculate_additional_entry_amount(
            positions, current_price
        )

        # Проверяем результат
        self.assertGreaterEqual(result, 0)
        self.assertLessEqual(result, initial_position.total_cost_usd * 0.5)  # Не больше 50% от первоначального

        print(f"Additional entry amount: ${result:.2f}")

        # Проверяем расчет по формуле из примера:
        # payout_opposite = 78 / 0.35 ≈ 222.86
        # required_profit = 100 * (20 + 10)/100 = 30
        # additional_amount = 222.86 - 100 - 78 - 30 = 14.86

        expected_payout = opposite_position.total_cost_usd / opposite_position.entry_price_avg
        required_profit = initial_position.total_cost_usd * (W1_PROFIT_PCT + W2_ADDITIONAL_PROFIT_PCT) / 100.0
        expected_additional = expected_payout - initial_position.total_cost_usd - opposite_position.total_cost_usd - required_profit

        print(f"Expected payout: ${expected_payout:.2f}")
        print(f"Required profit: ${required_profit:.2f}")
        print(f"Expected additional: ${expected_additional:.2f}")

    def test_validate_position_safety(self):
        """Тест проверки безопасности позиции."""
        # Создаем тестовые позиции
        positions = [
            Position(
                position_id="test_1",
                market_id="test",
                market_title="Test",
                symbol="TEST",
                side="DOWN",
                entry_time=None,
                entry_price_avg=0.5,
                total_volume=200,
                total_cost_usd=100.0,
                entry_reason="INITIAL_ENTRY"
            )
        ]

        # Тест безопасной позиции
        safe = PositionCalculator.validate_position_safety(
            positions, 50.0, 0.4, "DOWN"
        )
        self.assertTrue(safe)

        # Тест небезопасной позиции (слишком низкая цена)
        unsafe_price = PositionCalculator.validate_position_safety(
            positions, 50.0, 0.005, "DOWN"
        )
        self.assertFalse(unsafe_price)

        # Тест небезопасной позиции (слишком много денег)
        unsafe_amount = PositionCalculator.validate_position_safety(
            positions, 600.0, 0.4, "DOWN"  # 100 * 5 + 100 = 600
        )
        self.assertFalse(unsafe_amount)


if __name__ == '__main__':
    unittest.main()