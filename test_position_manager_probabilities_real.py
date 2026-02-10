#!/usr/bin/env python3
"""
Тесты для нового метода calculate_probabilities_for_position_manager с реальными данными.
"""

import unittest
import sys
import os
sys.path.append(os.getcwd())

from analysis.probability import PostEntryProbabilityAnalyzer


class TestPositionManagerProbabilitiesReal(unittest.TestCase):
    """Тесты для нового метода calculate_probabilities_for_position_manager с реальными данными."""

    def setUp(self):
        """Настройка тестов."""
        self.analyzer = PostEntryProbabilityAnalyzer()

    def test_calculate_probabilities_for_position_manager_real_data(self):
        """Тест с реальными данными из position_manager."""
        print("\n" + "="*80)
        print("ТЕСТ: calculate_probabilities_for_position_manager с реальными данными")
        print("="*80)
        
        # Данные из position_manager
        current_price = 2100.0
        target_price = 2100.0
        volatility_pct = 0.06  # 6%
        time_remaining_minutes = 8.0
        market_direction = "UP"  # current_price < target_price
        current_price_up = 0.5
        current_price_down = 0.5
        atr = 50.0
        vol_period_minutes = 15.0
        
        result = self.analyzer.calculate_probabilities_for_position_manager(
            current_price=current_price,
            target_price=target_price,
            volatility_pct=volatility_pct,
            time_remaining_minutes=time_remaining_minutes,
            market_direction=market_direction,
            current_price_up=current_price_up,
            current_price_down=current_price_down,
            atr=atr,
            vol_period_minutes=vol_period_minutes,
        )
        
        print(f"\nРЕЗУЛЬТАТ:")
        print(f"  p_up = {result['p_up']*100:.3f}%")
        print(f"  p_down = {result['p_down']*100:.3f}%")
        print(f"  volatility_used = {result['volatility_used']*100:.2f}%")
        print(f"  atr_used = {result['atr_used']}")
        print(f"  market_direction = {result['market_direction']}")
        print(f"  edge_up = {result['edge_up']*100:.3f}%")
        print(f"  edge_down = {result['edge_down']*100:.3f}%")
        
        # Проверки
        self.assertIsInstance(result, dict)
        self.assertIn('p_up', result)
        self.assertIn('p_down', result)
        self.assertGreaterEqual(result['p_up'], 0.0)
        self.assertLessEqual(result['p_up'], 1.0)
        self.assertGreaterEqual(result['p_down'], 0.0)
        self.assertLessEqual(result['p_down'], 1.0)
        
        # При price = target, p_up и p_down должны быть близки к 0.5
        self.assertAlmostEqual(result['p_up'], 0.5, places=1)
        self.assertAlmostEqual(result['p_down'], 0.5, places=1)

    def test_calculate_probabilities_for_position_manager_up_target(self):
        """Тест когда target выше текущей цены."""
        print("\n" + "="*80)
        print("ТЕСТ: calculate_probabilities_for_position_manager target выше цены")
        print("="*80)
        
        current_price = 2000.0
        target_price = 2100.0
        volatility_pct = 0.06  # 6%
        time_remaining_minutes = 15.0
        market_direction = "UP"  # current_price < target_price
        current_price_up = 0.5
        current_price_down = 0.5
        atr = 50.0
        vol_period_minutes = 15.0
        
        result = self.analyzer.calculate_probabilities_for_position_manager(
            current_price=current_price,
            target_price=target_price,
            volatility_pct=volatility_pct,
            time_remaining_minutes=time_remaining_minutes,
            market_direction=market_direction,
            current_price_up=current_price_up,
            current_price_down=current_price_down,
            atr=atr,
            vol_period_minutes=vol_period_minutes,
        )
        
        print(f"\nРЕЗУЛЬТАТ:")
        print(f"  p_up = {result['p_up']*100:.3f}%")
        print(f"  p_down = {result['p_down']*100:.3f}%")
        print(f"  volatility_used = {result['volatility_used']*100:.2f}%")
        print(f"  atr_used = {result['atr_used']}")
        print(f"  market_direction = {result['market_direction']}")
        print(f"  edge_up = {result['edge_up']*100:.3f}%")
        print(f"  edge_down = {result['edge_down']*100:.3f}%")
        
        # Проверки
        self.assertGreater(result['p_up'], 0.0)
        self.assertLess(result['p_up'], 1.0)
        self.assertGreater(result['p_down'], 0.0)
        self.assertLess(result['p_down'], 1.0)
        
        # Так как target выше цены, p_up должно быть меньше 0.5, p_down больше 0.5
        self.assertLess(result['p_up'], 0.5)
        self.assertGreater(result['p_down'], 0.5)

    def test_calculate_probabilities_for_position_manager_down_target(self):
        """Тест когда target ниже текущей цены."""
        print("\n" + "="*80)
        print("ТЕСТ: calculate_probabilities_for_position_manager target ниже цены")
        print("="*80)
        
        current_price = 2200.0
        target_price = 2100.0
        volatility_pct = 0.06  # 6%
        time_remaining_minutes = 15.0
        market_direction = "DOWN"  # current_price > target_price
        current_price_up = 0.5
        current_price_down = 0.5
        atr = 50.0
        vol_period_minutes = 15.0
        
        result = self.analyzer.calculate_probabilities_for_position_manager(
            current_price=current_price,
            target_price=target_price,
            volatility_pct=volatility_pct,
            time_remaining_minutes=time_remaining_minutes,
            market_direction=market_direction,
            current_price_up=current_price_up,
            current_price_down=current_price_down,
            atr=atr,
            vol_period_minutes=vol_period_minutes,
        )
        
        print(f"\nРЕЗУЛЬТАТ:")
        print(f"  p_up = {result['p_up']*100:.3f}%")
        print(f"  p_down = {result['p_down']*100:.3f}%")
        print(f"  volatility_used = {result['volatility_used']*100:.2f}%")
        print(f"  atr_used = {result['atr_used']}")
        print(f"  market_direction = {result['market_direction']}")
        print(f"  edge_up = {result['edge_up']*100:.3f}%")
        print(f"  edge_down = {result['edge_down']*100:.3f}%")
        
        # Проверки
        self.assertGreater(result['p_up'], 0.0)
        self.assertLess(result['p_up'], 1.0)
        self.assertGreater(result['p_down'], 0.0)
        self.assertLess(result['p_down'], 1.0)
        
        # Так как target ниже цены, p_up должно быть больше 0.5, p_down меньше 0.5
        self.assertGreater(result['p_up'], 0.5)
        self.assertLess(result['p_down'], 0.5)

    def test_calculate_probabilities_for_position_manager_different_timeframes(self):
        """Тест разных таймфреймов волатильности."""
        print("\n" + "="*80)
        print("ТЕСТ: calculate_probabilities_for_position_manager разные таймфреймы")
        print("="*80)
        
        current_price = 2100.0
        target_price = 2100.0
        volatility_pct = 0.06  # 6%
        time_remaining_minutes = 30.0
        market_direction = "UP"
        current_price_up = 0.5
        current_price_down = 0.5
        atr = 50.0
        
        # Тест 15-минутной волатильности
        print(f"\n--- Тест 1: 15-минутная волатильность ---")
        result_15min = self.analyzer.calculate_probabilities_for_position_manager(
            current_price=current_price,
            target_price=target_price,
            volatility_pct=volatility_pct,
            time_remaining_minutes=time_remaining_minutes,
            market_direction=market_direction,
            current_price_up=current_price_up,
            current_price_down=current_price_down,
            atr=atr,
            vol_period_minutes=15.0,
        )
        
        print(f"  vol_period_minutes = 15.0")
        print(f"  p_up = {result_15min['p_up']*100:.3f}%")
        print(f"  p_down = {result_15min['p_down']*100:.3f}%")
        print(f"  edge_up = {result_15min['edge_up']*100:.3f}%")
        print(f"  edge_down = {result_15min['edge_down']*100:.3f}%")
        
        # Тест 60-минутной волатильности
        print(f"\n--- Тест 2: 60-минутная волатильность ---")
        result_60min = self.analyzer.calculate_probabilities_for_position_manager(
            current_price=current_price,
            target_price=target_price,
            volatility_pct=volatility_pct,
            time_remaining_minutes=time_remaining_minutes,
            market_direction=market_direction,
            current_price_up=current_price_up,
            current_price_down=current_price_down,
            atr=atr,
            vol_period_minutes=60.0,
        )
        
        print(f"  vol_period_minutes = 60.0")
        print(f"  p_up = {result_60min['p_up']*100:.3f}%")
        print(f"  p_down = {result_60min['p_down']*100:.3f}%")
        print(f"  edge_up = {result_60min['edge_up']*100:.3f}%")
        print(f"  edge_down = {result_60min['edge_down']*100:.3f}%")
        
        # Проверки
        self.assertGreater(result_15min['p_up'], 0.0)
        self.assertLess(result_15min['p_up'], 1.0)
        self.assertGreater(result_15min['p_down'], 0.0)
        self.assertLess(result_15min['p_down'], 1.0)
        
        self.assertGreater(result_60min['p_up'], 0.0)
        self.assertLess(result_60min['p_up'], 1.0)
        self.assertGreater(result_60min['p_down'], 0.0)
        self.assertLess(result_60min['p_down'], 1.0)

    def test_calculate_probabilities_for_position_manager_edge_cases(self):
        """Тест граничных случаев."""
        print("\n" + "="*80)
        print("ТЕСТ: calculate_probabilities_for_position_manager граничные случаи")
        print("="*80)
        
        volatility_pct = 0.06  # 6%
        market_direction = "UP"
        current_price_up = 0.5
        current_price_down = 0.5
        atr = 50.0
        vol_period_minutes = 15.0
        
        # Тест 1: Очень маленькое время
        print(f"\n--- Тест 1: Очень маленькое время ---")
        current_price = 2100.0
        target_price = 2100.0
        time_remaining_minutes = 0.1  # Почти нулевое время
        
        result = self.analyzer.calculate_probabilities_for_position_manager(
            current_price=current_price,
            target_price=target_price,
            volatility_pct=volatility_pct,
            time_remaining_minutes=time_remaining_minutes,
            market_direction=market_direction,
            current_price_up=current_price_up,
            current_price_down=current_price_down,
            atr=atr,
            vol_period_minutes=vol_period_minutes,
        )
        
        print(f"  time_remaining_minutes = {time_remaining_minutes}")
        print(f"  p_up = {result['p_up']*100:.3f}%")
        print(f"  p_down = {result['p_down']*100:.3f}%")
        print(f"  edge_up = {result['edge_up']*100:.3f}%")
        print(f"  edge_down = {result['edge_down']*100:.3f}%")
        
        # При очень маленьком времени и price = target, вероятности должны быть близки к 0.5
        self.assertAlmostEqual(result['p_up'], 0.5, places=1)
        self.assertAlmostEqual(result['p_down'], 0.5, places=1)
        
        # Тест 2: Очень большое время
        print(f"\n--- Тест 2: Очень большое время ---")
        time_remaining_minutes = 1440.0  # 24 часа
        
        result = self.analyzer.calculate_probabilities_for_position_manager(
            current_price=current_price,
            target_price=target_price,
            volatility_pct=volatility_pct,
            time_remaining_minutes=time_remaining_minutes,
            market_direction=market_direction,
            current_price_up=current_price_up,
            current_price_down=current_price_down,
            atr=atr,
            vol_period_minutes=vol_period_minutes,
        )
        
        print(f"  time_remaining_minutes = {time_remaining_minutes}")
        print(f"  p_up = {result['p_up']*100:.3f}%")
        print(f"  p_down = {result['p_down']*100:.3f}%")
        print(f"  edge_up = {result['edge_up']*100:.3f}%")
        print(f"  edge_down = {result['edge_down']*100:.3f}%")
        
        # При очень большом времени и price = target, вероятности должны быть близки к 0.5
        self.assertAlmostEqual(result['p_up'], 0.5, places=1)
        self.assertAlmostEqual(result['p_down'], 0.5, places=1)


if __name__ == '__main__':
    unittest.main(verbosity=2)