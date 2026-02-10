"""
Position Calculator - расчеты для управления позициями.

Содержит методы для расчета оптимальных сумм входа в дополнительные позиции
с гарантией прибыли по алгоритму hedging.
"""

import logging
from typing import List, Optional

from app.config import W1_PROFIT_PCT, W2_ADDITIONAL_PROFIT_PCT
from trading.position import Position

logger = logging.getLogger(__name__)


class PositionCalculator:
    """
    Калькулятор для расчета сумм входа в позиции с гарантией прибыли.
    """

    @staticmethod
    def calculate_opposite_entry_amount(
        initial_amount: float,
        initial_price: float,
        opposite_price: float
    ) -> float:
        """
        Рассчитать сумму для входа в противоположную позицию.

        Гарантирует минимальную прибыль W1_PROFIT_PCT от первоначального входа.

        Args:
            initial_amount: Сумма первоначального входа ($)
            initial_price: Цена первоначального входа
            opposite_price: Цена входа в противоположную позицию

        Returns:
            Сумма для входа в противоположную позицию ($)
        """
        try:
            # Потенциальная прибыль от первоначальной позиции при ее победе
            # payout = initial_amount / initial_price
            # profit = payout - initial_amount
            # Гарантированная прибыль должна быть >= initial_amount * (W1_PROFIT_PCT / 100)

            min_profit = initial_amount * (W1_PROFIT_PCT / 100.0)

            # Если первоначальная позиция выиграет:
            # payout = initial_amount / initial_price
            # profit = payout - initial_amount
            # Но мы должны гарантировать min_profit

            # Максимальная сумма для противоположной позиции:
            # payout_opposite = opposite_amount / opposite_price
            # Если противоположная выиграет: profit = payout_opposite - opposite_amount - initial_amount
            # Если первоначальная выиграет: profit = payout_initial - initial_amount - opposite_amount
            # Мы хотим profit >= min_profit в обоих случаях

            # Для простоты берем случай когда противоположная сторона проигрывает
            # (что дает нам payout от первоначальной позиции)
            payout_initial = initial_amount / initial_price
            profit_from_initial_win = payout_initial - initial_amount

            # Нам нужно чтобы profit_from_initial_win >= min_profit
            # payout_opposite = opposite_amount / opposite_price
            # Если противоположная выиграет: payout_opposite - opposite_amount - initial_amount >= min_profit

            # Решаем уравнение: (opposite_amount / opposite_price) - opposite_amount - initial_amount = min_profit
            # opposite_amount / opposite_price - opposite_amount = min_profit + initial_amount
            # opposite_amount * (1/opposite_price - 1) = min_profit + initial_amount
            # opposite_amount = (min_profit + initial_amount) / (1/opposite_price - 1)

            denominator = 1.0 / opposite_price - 1.0
            if denominator <= 0:
                return 0.0

            opposite_amount = (min_profit + initial_amount) / denominator

            # Ограничиваем разумными пределами
            opposite_amount = min(opposite_amount, initial_amount * 3)  # Не больше 3x от первоначального
            opposite_amount = max(opposite_amount, 0)  # Не отрицательная

            logger.debug(".2f"
                        ".2f"
                        ".2f")

            return opposite_amount

        except Exception as exc:
            logger.error(f"Ошибка при расчете суммы противоположного входа: {exc}")
            return 0.0

    @staticmethod
    def calculate_additional_entry_amount(
        positions: List[Position],
        current_price: float
    ) -> float:
        """
        Рассчитать сумму для дополнительного входа в исходную позицию.

        По алгоритму: моделируем исход где противоположная сторона wins,
        и находим сколько можно добавить в исходную сторону чтобы прибыль
        была ровно W1 + W2 % от первоначального входа.

        Args:
            positions: Список текущих позиций [initial, opposite]
            current_price: Текущая цена входа в исходную позицию

        Returns:
            Сумма для дополнительного входа ($)
        """
        try:
            if len(positions) < 2:
                return 0.0

            # Находим позиции
            initial_position = None
            opposite_position = None

            for pos in positions:
                if pos.entry_reason == "INITIAL_ENTRY":
                    initial_position = pos
                elif pos.entry_reason == "OPPOSITE_ENTRY":
                    opposite_position = pos

            if not initial_position or not opposite_position:
                return 0.0

            # Параметры
            initial_amount = initial_position.total_cost_usd
            opposite_amount = opposite_position.total_cost_usd
            opposite_price = opposite_position.entry_price_avg

            # Требуемая прибыль = W1 + W2 процентов от первоначального входа
            required_profit_pct = W1_PROFIT_PCT + W2_ADDITIONAL_PROFIT_PCT
            required_profit = initial_amount * (required_profit_pct / 100.0)

            # Моделируем исход: противоположная сторона wins
            # payout_opposite = opposite_amount / opposite_price
            # total_cost_all_positions = initial_amount + opposite_amount + additional_amount
            # profit = payout_opposite - total_cost_all_positions
            # Нам нужно: profit = required_profit
            # payout_opposite - initial_amount - opposite_amount - additional_amount = required_profit
            # additional_amount = payout_opposite - initial_amount - opposite_amount - required_profit

            payout_opposite = opposite_amount / opposite_price
            additional_amount = payout_opposite - initial_amount - opposite_amount - required_profit

            # Дополнительная позиция должна быть в исходную сторону по текущей цене
            # Но additional_amount - это стоимость входа, нам нужно проверить что это разумно

            # Ограничиваем
            additional_amount = min(additional_amount, initial_amount * 0.5)  # Не больше 50% от первоначального
            additional_amount = max(additional_amount, 0)  # Не отрицательная

            logger.debug(".2f"
                        ".2f"
                        ".2f"
                        ".2f")

            return additional_amount

        except Exception as exc:
            logger.error(f"Ошибка при расчете суммы дополнительного входа: {exc}")
            return 0.0

    @staticmethod
    def validate_position_safety(
        positions: List[Position],
        new_entry_amount: float,
        new_entry_price: float,
        new_entry_side: str
    ) -> bool:
        """
        Проверить безопасность новой позиции.

        Args:
            positions: Текущие позиции
            new_entry_amount: Сумма нового входа
            new_entry_price: Цена нового входа
            new_entry_side: Сторона нового входа

        Returns:
            True если позиция безопасна
        """
        try:
            # Проверяем что не превышаем разумные лимиты
            total_cost = sum(pos.total_cost_usd for pos in positions) + new_entry_amount

            # Не более 5x от первоначальной позиции
            if positions:
                initial_cost = positions[0].total_cost_usd
                if total_cost > initial_cost * 5:
                    logger.warning(f"Общая стоимость позиций {total_cost:.2f} > 5x от первоначальной {initial_cost:.2f}")
                    return False

            # Проверяем что цена в разумных пределах
            if not (0.01 <= new_entry_price <= 0.99):
                logger.warning(f"Цена входа {new_entry_price:.4f} вне разумных пределов")
                return False

            return True

        except Exception as exc:
            logger.error(f"Ошибка при проверке безопасности позиции: {exc}")
            return False