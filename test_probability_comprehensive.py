#!/usr/bin/env python3
"""
Комплексные тесты для probability.py с подробным логированием всех расчетов.
"""

import unittest
import sys
import os
import logging
sys.path.append(os.getcwd())

from analysis.probability import PostEntryProbabilityAnalyzer


# Настройка логирования для подробного вывода
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


class TestProbabilityComprehensive(unittest.TestCase):
    """Комплексные тесты для проверки всех расчетов."""

    def setUp(self):
        """Настройка тестов."""
        self.analyzer = PostEntryProbabilityAnalyzer()
        
        # Данные для тестов из задания пользователя
        self.test_data = {
            'current_price': 2100.0,
            'price_to_beat': 2200.0,
            'vol_15m': 0.06,  # 6% в десятичной форме
            'minutes_to_end': 8.0,
            'current_price_up': 0.6,  # 60%
            'current_price_down': 0.4,  # 40%
        }

    def test_opposite_side_buy_with_user_data(self):
        """Тест analyze_opposite_side_buy с реальными данными пользователя."""
        print("\n" + "="*80)
        print("ТЕСТ: analyze_opposite_side_buy с реальными данными")
        print("="*80)
        
        # Данные из задания
        current_price_btc = self.test_data['current_price']
        market_target = self.test_data['price_to_beat']
        volatility_pct = self.test_data['vol_15m']
        time_remaining_minutes = self.test_data['minutes_to_end']
        current_price_up = self.test_data['current_price_up']
        current_price_down = self.test_data['current_price_down']
        
        print(f"Входные данные:")
        print(f"  current_price_btc = {current_price_btc}")
        print(f"  market_target = {market_target}")
        print(f"  volatility_pct = {volatility_pct} ({volatility_pct*100:.2f}%)")
        print(f"  time_remaining_minutes = {time_remaining_minutes}")
        print(f"  current_price_up = {current_price_up} ({current_price_up*100:.0f}%)")
        print(f"  current_price_down = {current_price_down} ({current_price_down*100:.0f}%)")
        
        # Тест для UP направления рынка
        print(f"\n--- Тест 1: market_direction=UP, opposite_side=DOWN ---")
        result_up_down = self.analyzer.analyze_opposite_side_buy(
            current_price_btc=current_price_btc,
            market_target=market_target,
            market_direction="UP",
            opposite_side="DOWN",
            volatility_pct=volatility_pct,
            time_remaining_minutes=time_remaining_minutes,
            current_price_up=current_price_up,
            current_price_down=current_price_down,
            vol_period_minutes=15.0,  # 15-минутная волатильность
        )
        
        self._print_result_details("UP->DOWN", result_up_down)
        
        # Тест для DOWN направления рынка
        print(f"\n--- Тест 2: market_direction=DOWN, opposite_side=UP ---")
        result_down_up = self.analyzer.analyze_opposite_side_buy(
            current_price_btc=current_price_btc,
            market_target=market_target,
            market_direction="DOWN",
            opposite_side="UP",
            volatility_pct=volatility_pct,
            time_remaining_minutes=time_remaining_minutes,
            current_price_up=current_price_up,
            current_price_down=current_price_down,
            vol_period_minutes=15.0,  # 15-минутная волатильность
        )
        
        self._print_result_details("DOWN->UP", result_down_up)
        
        # Проверки
        self.assertGreaterEqual(result_up_down.math_probability, 0.0)
        self.assertLessEqual(result_up_down.math_probability, 1.0)
        self.assertGreaterEqual(result_down_up.math_probability, 0.0)
        self.assertLessEqual(result_down_up.math_probability, 1.0)

    def test_same_side_add_with_user_data(self):
        """Тест analyze_same_side_add с реальными данными."""
        print("\n" + "="*80)
        print("ТЕСТ: analyze_same_side_add с реальными данными")
        print("="*80)
        
        # Данные из задания
        current_price_btc = self.test_data['current_price']
        market_target = self.test_data['price_to_beat']
        volatility_pct = self.test_data['vol_15m']
        time_remaining_minutes = self.test_data['minutes_to_end']
        current_price_up = self.test_data['current_price_up']
        current_price_down = self.test_data['current_price_down']
        
        print(f"Входные данные:")
        print(f"  current_price_btc = {current_price_btc}")
        print(f"  market_target = {market_target}")
        print(f"  volatility_pct = {volatility_pct} ({volatility_pct*100:.2f}%)")
        print(f"  time_remaining_minutes = {time_remaining_minutes}")
        print(f"  current_price_up = {current_price_up} ({current_price_up*100:.0f}%)")
        print(f"  current_price_down = {current_price_down} ({current_price_down*100:.0f}%)")
        
        # Тест для UP позиции
        print(f"\n--- Тест 1: market_direction=UP, position_side=UP ---")
        result_up_up = self.analyzer.analyze_same_side_add(
            current_price_btc=current_price_btc,
            market_target=market_target,
            market_direction="UP",
            volatility_pct=volatility_pct,
            time_remaining_minutes=time_remaining_minutes,
            current_price_up=current_price_up,
            current_price_down=current_price_down,
            position_side="UP",
            vol_period_minutes=15.0,
        )
        
        self._print_result_details("UP->UP", result_up_up)
        
        # Тест для DOWN позиции
        print(f"\n--- Тест 2: market_direction=DOWN, position_side=DOWN ---")
        result_down_down = self.analyzer.analyze_same_side_add(
            current_price_btc=current_price_btc,
            market_target=market_target,
            market_direction="DOWN",
            volatility_pct=volatility_pct,
            time_remaining_minutes=time_remaining_minutes,
            current_price_up=current_price_up,
            current_price_down=current_price_down,
            position_side="DOWN",
            vol_period_minutes=15.0,
        )
        
        self._print_result_details("DOWN->DOWN", result_down_down)

    def test_exit_bad_with_user_data(self):
        """Тест analyze_exit_bad с реальными данными."""
        print("\n" + "="*80)
        print("ТЕСТ: analyze_exit_bad с реальными данными")
        print("="*80)
        
        # Данные из задания
        current_price_btc = self.test_data['current_price']
        market_target = self.test_data['price_to_beat']
        volatility_pct = self.test_data['vol_15m']
        time_remaining_minutes = self.test_data['minutes_to_end']
        current_price_up = self.test_data['current_price_up']
        current_price_down = self.test_data['current_price_down']
        
        print(f"Входные данные:")
        print(f"  current_price_btc = {current_price_btc}")
        print(f"  market_target = {market_target}")
        print(f"  volatility_pct = {volatility_pct} ({volatility_pct*100:.2f}%)")
        print(f"  time_remaining_minutes = {time_remaining_minutes}")
        print(f"  current_price_up = {current_price_up} ({current_price_up*100:.0f}%)")
        print(f"  current_price_down = {current_price_down} ({current_price_down*100:.0f}%)")
        
        # Тест для UP позиции
        print(f"\n--- Тест 1: position_side=UP ---")
        result_up = self.analyzer.analyze_exit_bad(
            current_price_btc=current_price_btc,
            market_target=market_target,
            market_direction="UP",
            volatility_pct=volatility_pct,
            time_remaining_minutes=time_remaining_minutes,
            current_price_up=current_price_up,
            current_price_down=current_price_down,
            position_side="UP",
            vol_period_minutes=15.0,
        )
        
        self._print_result_details("EXIT UP", result_up)
        
        # Тест для DOWN позиции
        print(f"\n--- Тест 2: position_side=DOWN ---")
        result_down = self.analyzer.analyze_exit_bad(
            current_price_btc=current_price_btc,
            market_target=market_target,
            market_direction="DOWN",
            volatility_pct=volatility_pct,
            time_remaining_minutes=time_remaining_minutes,
            current_price_up=current_price_up,
            current_price_down=current_price_down,
            position_side="DOWN",
            vol_period_minutes=15.0,
        )
        
        self._print_result_details("EXIT DOWN", result_down)

    def test_edge_cases(self):
        """Тест граничных случаев."""
        print("\n" + "="*80)
        print("ТЕСТ: Граничные случаи")
        print("="*80)
        
        # Очень маленькая волатильность
        print(f"\n--- Тест: Очень маленькая волатильность ---")
        result_low_vol = self.analyzer.analyze_opposite_side_buy(
            current_price_btc=100.0,
            market_target=101.0,
            market_direction="UP",
            opposite_side="DOWN",
            volatility_pct=0.0001,  # Очень маленькая волатильность
            time_remaining_minutes=60.0,
            current_price_up=0.5,
            current_price_down=0.5,
            vol_period_minutes=60.0,
        )
        
        self._print_result_details("Low Volatility", result_low_vol)
        
        # Очень большое время
        print(f"\n--- Тест: Очень большое время ---")
        result_long_time = self.analyzer.analyze_opposite_side_buy(
            current_price_btc=100.0,
            market_target=110.0,
            market_direction="UP",
            opposite_side="DOWN",
            volatility_pct=0.05,
            time_remaining_minutes=1440.0,  # 24 часа
            current_price_up=0.5,
            current_price_down=0.5,
            vol_period_minutes=60.0,
        )
        
        self._print_result_details("Long Time", result_long_time)

    def _print_result_details(self, test_name: str, result):
        """Печать подробных результатов расчета."""
        print(f"\n{test_name} РЕЗУЛЬТАТЫ:")
        print(f"  KF (коэффициент): {result.kf:.6f}")
        print(f"  Math Probability: {result.math_probability:.6f} ({result.math_probability*100:.3f}%)")
        print(f"  Market Probability: {result.market_probability:.6f} ({result.market_probability*100:.3f}%)")
        print(f"  Edge: {result.edge:.6f} ({result.edge*100:.3f}%)")
        print(f"  Expected Move: {result.expected_move_pct:.6f} ({result.expected_move_pct*100:.3f}%)")
        print(f"  Relative Deviation: {result.relative_deviation_pct:.3f}%")
        print(f"  Reason: {result.reason}")
        print(f"  Current Price: {result.current_price}")
        print(f"  Target Price: {result.target_price}")
        print(f"  Volatility: {result.volatility_pct:.6f} ({result.volatility_pct*100:.3f}%)")
        print(f"  Time Remaining: {result.time_remaining_minutes} min")
        print(f"  Time in Hours: {result.time_in_hours:.3f} h")
        print(f"  Price Move: {result.price_move_pct:.6f} ({result.price_move_pct*100:.3f}%)")
        print(f"  Std Dev: {result.std_dev_pct:.6f} ({result.std_dev_pct*100:.3f}%)")
        print(f"  Z-Score: {result.z_score:.6f}")
        print(f"  Reach Probability: {result.reach_probability:.6f} ({result.reach_probability*100:.3f}%)")
        print(f"  Inverted: {result.inverted}")

    def test_hybrid_volatility_calculation(self):
        """Тест расчета гибридной волатильности."""
        print("\n" + "="*80)
        print("ТЕСТ: Гибридная волатильность")
        print("="*80)
        
        current_price = 100.0
        atr = 2.0  # ATR в долларах
        volatility_current_pct = 0.05  # 5% текущая волатильность
        
        vol_for_kf, atr_pct, vol_current = self.analyzer.calculate_hybrid_volatility(
            volatility_current_pct, atr, current_price
        )
        
        print(f"Входные данные:")
        print(f"  current_price = {current_price}")
        print(f"  atr = {atr}")
        print(f"  volatility_current_pct = {volatility_current_pct} ({volatility_current_pct*100:.1f}%)")
        
        print(f"\nРезультаты:")
        print(f"  ATR % = {atr_pct:.6f} ({atr_pct*100:.3f}%)")
        print(f"  Current Vol % = {vol_current:.6f} ({vol_current*100:.3f}%)")
        print(f"  Hybrid Vol % = {vol_for_kf:.6f} ({vol_for_kf*100:.3f}%)")
        
        # Проверка: ATR% = ATR/price
        expected_atr_pct = atr / current_price
        self.assertAlmostEqual(atr_pct, expected_atr_pct, places=6)
        
        # Проверка: гибридная волатильность должна быть >= floor
        from app.config import VOLATILITY_FLOOR
        self.assertGreaterEqual(vol_for_kf, VOLATILITY_FLOOR)


if __name__ == '__main__':
    unittest.main(verbosity=2)