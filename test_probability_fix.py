#!/usr/bin/env python3
"""
Тест для проверки исправления проблемы с UP Touch Prob и Down Touch Prob.

Проверяет правильность расчетов вероятностей после исправления единиц измерения.
"""

import unittest
import sys
import os
sys.path.append(os.getcwd())

from analysis.probability import PostEntryProbabilityAnalyzer


class TestProbabilityFix(unittest.TestCase):
    """Тесты для проверки исправления вероятностей."""

    def setUp(self):
        """Настройка тестов."""
        self.analyzer = PostEntryProbabilityAnalyzer()

    def test_calculate_reach_probability_units_consistency(self):
        """Тест что calculate_reach_probability правильно работает с десятичными единицами."""
        # Тестовый случай: цена 100, цель 105, волатильность 0.05 (5%), время 60 мин, период 60 мин
        current_price = 100.0
        target_price = 105.0
        volatility_pct = 0.05  # 5% в десятичной форме
        time_remaining = 60.0
        vol_period = 60.0

        # Ожидаемое движение цены: (105-100)/100 = 0.05 (5%)
        expected_price_move = 0.05

        # Ожидаемое std_dev: 0.05 * sqrt(60/60) = 0.05
        expected_std_dev = 0.05

        # Ожидаемый z-score: 0.05 / 0.05 = 1.0
        expected_z = 1.0

        # Вероятность: 1 - Φ(1.0) ≈ 1 - 0.8413 = 0.1587
        expected_prob = 1.0 - 0.8413  # Примерно 0.1587

        result = self.analyzer.calculate_reach_probability(
            current_price, target_price, volatility_pct, time_remaining, vol_period
        )

        # Проверяем что результат в разумных пределах
        self.assertGreater(result, 0.1)
        self.assertLess(result, 0.25)
        print(f"Reach probability: {result:.4f} (expected ~{expected_prob:.4f})")

    def test_calculate_reach_details_units_consistency(self):
        """Тест что calculate_reach_details возвращает правильные значения."""
        current_price = 100.0
        target_price = 105.0
        volatility_pct = 0.05
        time_remaining = 60.0
        vol_period = 60.0

        reach_prob, price_move_pct, std_dev_pct, z_score, time_in_hours = (
            self.analyzer.calculate_reach_details(
                current_price, target_price, volatility_pct, time_remaining, vol_period
            )
        )

        # price_move_pct должен быть в десятичной форме: 0.05
        self.assertAlmostEqual(price_move_pct, 0.05, places=4)

        # std_dev_pct должен быть в десятичной форме: 0.05
        self.assertAlmostEqual(std_dev_pct, 0.05, places=4)

        # z_score должен быть правильным: 0.05 / 0.05 = 1.0
        self.assertAlmostEqual(z_score, 1.0, places=2)

        # reach_prob должен быть разумным
        self.assertGreater(reach_prob, 0.1)
        self.assertLess(reach_prob, 0.25)

        print(f"Reach details: prob={reach_prob:.4f}, price_move={price_move_pct:.4f}, std_dev={std_dev_pct:.4f}, z={z_score:.4f}")

    def test_analyze_opposite_side_buy_touch_probabilities(self):
        """Тест что UP Touch Prob и Down Touch Prob рассчитываются правильно."""
        # Тестовый сценарий
        current_price_btc = 100.0
        market_target = 105.0  # Цель выше текущей цены
        market_direction = "UP"  # Рынок идет вверх
        volatility_pct = 0.05  # Волатильность в десятичной форме
        time_remaining_minutes = 60.0
        current_price_up = 0.6  # 60% вероятность для UP
        current_price_down = 0.4  # 40% вероятность для DOWN
        vol_period_minutes = 60.0

        # Анализируем для UP стороны (opposite side когда market_direction=UP)
        result_up = self.analyzer.analyze_opposite_side_buy(
            current_price_btc=current_price_btc,
            market_target=market_target,
            market_direction=market_direction,
            opposite_side="UP",
            volatility_pct=volatility_pct,
            time_remaining_minutes=time_remaining_minutes,
            current_price_up=current_price_up,
            current_price_down=current_price_down,
            vol_period_minutes=vol_period_minutes,
        )

        # Анализируем для DOWN стороны
        result_down = self.analyzer.analyze_opposite_side_buy(
            current_price_btc=current_price_btc,
            market_target=market_target,
            market_direction=market_direction,
            opposite_side="DOWN",
            volatility_pct=volatility_pct,
            time_remaining_minutes=time_remaining_minutes,
            current_price_up=current_price_up,
            current_price_down=current_price_down,
            vol_period_minutes=vol_period_minutes,
        )

        # Проверяем что вероятности в разумных пределах (учитывая гибридную волатильность)
        # С гибридной волатильностью (0.05 * 0.4 = 0.02) вероятность должна быть ~0.006
        self.assertGreater(result_up.math_probability, 0.005)
        self.assertLess(result_up.math_probability, 0.01)
        self.assertGreater(result_down.math_probability, 0.99)
        self.assertLess(result_down.math_probability, 1.01)

        # Для market_direction=UP и current_price < target:
        # reach_prob_up = reach_prob_raw (вероятность достичь target)
        # reach_prob_down = 1.0 (уже ниже target)

        print(f"UP Touch Prob: {result_up.math_probability:.4f}")
        print(f"Down Touch Prob: {result_down.math_probability:.4f}")

    def test_analyze_exit_bad_p_hit_calculation(self):
        """Тест что p_hit в analyze_exit_bad рассчитывается правильно."""
        current_price_btc = 100.0
        market_target = 105.0  # Цель выше
        market_direction = "UP"
        volatility_pct = 0.05
        time_remaining_minutes = 60.0
        current_price_up = 0.6
        current_price_down = 0.4
        position_side = "UP"  # UP позиция, цель выше
        vol_period_minutes = 60.0

        result = self.analyzer.analyze_exit_bad(
            current_price_btc=current_price_btc,
            market_target=market_target,
            market_direction=market_direction,
            volatility_pct=volatility_pct,
            time_remaining_minutes=time_remaining_minutes,
            current_price_up=current_price_up,
            current_price_down=current_price_down,
            position_side=position_side,
            vol_period_minutes=vol_period_minutes,
        )

        # kf содержит p_hit для UP позиции
        p_hit = result.kf

        # С гибридной волатильностью (0.05 * 0.4 = 0.02) p_hit должен быть ~0.006
        self.assertGreater(p_hit, 0.005)
        self.assertLess(p_hit, 0.01)

        print(f"p_hit for UP position: {p_hit:.4f}")


if __name__ == '__main__':
    unittest.main()