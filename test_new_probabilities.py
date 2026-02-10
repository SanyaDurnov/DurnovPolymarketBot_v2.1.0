#!/usr/bin/env python3
"""
Тесты для нового упрощенного интерфейса calculate_probabilities.
"""

import unittest
import sys
import os
sys.path.append(os.getcwd())

from analysis.probability import PostEntryProbabilityAnalyzer


class TestNewProbabilities(unittest.TestCase):
    """Тесты для нового упрощенного интерфейса."""

    def setUp(self):
        """Настройка тестов."""
        self.analyzer = PostEntryProbabilityAnalyzer()

    def test_calculate_probabilities_basic(self):
        """Тест базового расчета вероятностей."""
        print("\n" + "="*80)
        print("ТЕСТ: calculate_probabilities с реальными данными")
        print("="*80)
        
        # Данные из задания пользователя
        current_price = 2100.0
        target_up = 2200.0
        target_down = 2000.0
        volatility_pct = 0.06  # 6% в десятичной форме
        time_remaining_minutes = 8.0
        vol_period_minutes = 15.0  # 15-минутная волатильность
        
        print(f"Входные данные:")
        print(f"  current_price = {current_price}")
        print(f"  target_up = {target_up}")
        print(f"  target_down = {target_down}")
        print(f"  volatility_pct = {volatility_pct} ({volatility_pct*100:.1f}%)")
        print(f"  time_remaining_minutes = {time_remaining_minutes}")
        print(f"  vol_period_minutes = {vol_period_minutes}")
        
        result = self.analyzer.calculate_probabilities(
            current_price=current_price,
            target_up=target_up,
            target_down=target_down,
            volatility_pct=volatility_pct,
            time_remaining_minutes=time_remaining_minutes,
            vol_period_minutes=vol_period_minutes,
        )
        
        print(f"\nРЕЗУЛЬТАТ:")
        print(f"  p_up = {result['p_up']:.6f} ({result['p_up']*100:.3f}%)")
        print(f"  p_down = {result['p_down']:.6f} ({result['p_down']*100:.3f}%)")
        
        # Проверки
        self.assertIsInstance(result, dict)
        self.assertIn('p_up', result)
        self.assertIn('p_down', result)
        self.assertGreaterEqual(result['p_up'], 0.0)
        self.assertLessEqual(result['p_up'], 1.0)
        self.assertGreaterEqual(result['p_down'], 0.0)
        self.assertLessEqual(result['p_down'], 1.0)
        
        # Для этих параметров вероятности должны быть очень низкими
        self.assertLess(result['p_up'], 0.01)  # Меньше 1%
        self.assertLess(result['p_down'], 0.01)  # Меньше 1%

    def test_calculate_probabilities_symmetric(self):
        """Тест симметричных целей."""
        print("\n" + "="*80)
        print("ТЕСТ: calculate_probabilities с симметричными целями")
        print("="*80)
        
        current_price = 100.0
        target_up = 110.0  # +10%
        target_down = 90.0  # -10%
        volatility_pct = 0.05  # 5%
        time_remaining_minutes = 60.0
        vol_period_minutes = 60.0
        
        print(f"Входные данные:")
        print(f"  current_price = {current_price}")
        print(f"  target_up = {target_up} (+10%)")
        print(f"  target_down = {target_down} (-10%)")
        print(f"  volatility_pct = {volatility_pct} ({volatility_pct*100:.1f}%)")
        print(f"  time_remaining_minutes = {time_remaining_minutes}")
        print(f"  vol_period_minutes = {vol_period_minutes}")
        
        result = self.analyzer.calculate_probabilities(
            current_price=current_price,
            target_up=target_up,
            target_down=target_down,
            volatility_pct=volatility_pct,
            time_remaining_minutes=time_remaining_minutes,
            vol_period_minutes=vol_period_minutes,
        )
        
        print(f"\nРЕЗУЛЬТАТ:")
        print(f"  p_up = {result['p_up']:.6f} ({result['p_up']*100:.3f}%)")
        print(f"  p_down = {result['p_down']:.6f} ({result['p_down']*100:.3f}%)")
        
        # Проверки
        self.assertGreater(result['p_up'], 0.0)
        self.assertGreater(result['p_down'], 0.0)
        self.assertLess(result['p_up'], 1.0)
        self.assertLess(result['p_down'], 1.0)
        
        # Для симметричных целей и нормальной волатильности вероятности должны быть разумными
        self.assertGreater(result['p_up'], 0.001)  # Больше 0.1%
        self.assertGreater(result['p_down'], 0.001)  # Больше 0.1%

    def test_calculate_probabilities_high_volatility(self):
        """Тест с высокой волатильностью."""
        print("\n" + "="*80)
        print("ТЕСТ: calculate_probabilities с высокой волатильностью")
        print("="*80)
        
        current_price = 100.0
        target_up = 120.0  # +20%
        target_down = 80.0  # -20%
        volatility_pct = 0.20  # 20% - очень высокая волатильность
        time_remaining_minutes = 60.0
        vol_period_minutes = 60.0
        
        print(f"Входные данные:")
        print(f"  current_price = {current_price}")
        print(f"  target_up = {target_up} (+20%)")
        print(f"  target_down = {target_down} (-20%)")
        print(f"  volatility_pct = {volatility_pct} ({volatility_pct*100:.1f}%)")
        print(f"  time_remaining_minutes = {time_remaining_minutes}")
        print(f"  vol_period_minutes = {vol_period_minutes}")
        
        result = self.analyzer.calculate_probabilities(
            current_price=current_price,
            target_up=target_up,
            target_down=target_down,
            volatility_pct=volatility_pct,
            time_remaining_minutes=time_remaining_minutes,
            vol_period_minutes=vol_period_minutes,
        )
        
        print(f"\nРЕЗУЛЬТАТ:")
        print(f"  p_up = {result['p_up']:.6f} ({result['p_up']*100:.3f}%)")
        print(f"  p_down = {result['p_down']:.6f} ({result['p_down']*100:.3f}%)")
        
        # Проверки
        self.assertGreater(result['p_up'], 0.0)
        self.assertGreater(result['p_down'], 0.0)
        self.assertLess(result['p_up'], 1.0)
        self.assertLess(result['p_down'], 1.0)
        
        # С высокой волатильностью вероятности должны быть выше
        self.assertGreater(result['p_up'], 0.01)  # Больше 1%
        self.assertGreater(result['p_down'], 0.01)  # Больше 1%

    def test_calculate_probabilities_edge_cases(self):
        """Тест граничных случаев."""
        print("\n" + "="*80)
        print("ТЕСТ: calculate_probabilities граничные случаи")
        print("="*80)
        
        # Тест 1: Цены на целях
        print(f"\n--- Тест 1: Цены на целях ---")
        current_price = 100.0
        target_up = 100.0  # Текущая цена = цели
        target_down = 100.0  # Текущая цена = цели
        volatility_pct = 0.05
        time_remaining_minutes = 60.0
        vol_period_minutes = 60.0
        
        result = self.analyzer.calculate_probabilities(
            current_price=current_price,
            target_up=target_up,
            target_down=target_down,
            volatility_pct=volatility_pct,
            time_remaining_minutes=time_remaining_minutes,
            vol_period_minutes=vol_period_minutes,
        )
        
        print(f"  current_price = {current_price}, target_up = {target_up}, target_down = {target_down}")
        print(f"  p_up = {result['p_up']:.6f} ({result['p_up']*100:.3f}%)")
        print(f"  p_down = {result['p_down']:.6f} ({result['p_down']*100:.3f}%)")
        
        # При price = target, p_up должно быть ~0.5, p_down должно быть ~0.5
        self.assertAlmostEqual(result['p_up'], 0.5, places=1)
        self.assertAlmostEqual(result['p_down'], 0.5, places=1)
        
        # Тест 2: Очень маленькое время
        print(f"\n--- Тест 2: Очень маленькое время ---")
        time_remaining_minutes = 0.1  # Почти нулевое время
        
        result = self.analyzer.calculate_probabilities(
            current_price=current_price,
            target_up=target_up,
            target_down=target_down,
            volatility_pct=volatility_pct,
            time_remaining_minutes=time_remaining_minutes,
            vol_period_minutes=vol_period_minutes,
        )
        
        print(f"  time_remaining_minutes = {time_remaining_minutes}")
        print(f"  p_up = {result['p_up']:.6f} ({result['p_up']*100:.3f}%)")
        print(f"  p_down = {result['p_down']:.6f} ({result['p_down']*100:.3f}%)")
        
        # При очень маленьком времени вероятности должны быть близки к 0.5
        self.assertAlmostEqual(result['p_up'], 0.5, places=1)
        self.assertAlmostEqual(result['p_down'], 0.5, places=1)

    def test_calculate_probabilities_15min_vs_60min(self):
        """Тест сравнения 15-минутной и 60-минутной волатильности."""
        print("\n" + "="*80)
        print("ТЕСТ: Сравнение 15-минутной и 60-минутной волатильности")
        print("="*80)
        
        current_price = 100.0
        target_up = 110.0
        target_down = 90.0
        volatility_pct = 0.05
        time_remaining_minutes = 30.0
        
        # Тест с 15-минутной волатильностью
        result_15min = self.analyzer.calculate_probabilities(
            current_price=current_price,
            target_up=target_up,
            target_down=target_down,
            volatility_pct=volatility_pct,
            time_remaining_minutes=time_remaining_minutes,
            vol_period_minutes=15.0,
        )
        
        # Тест с 60-минутной волатильностью
        result_60min = self.analyzer.calculate_probabilities(
            current_price=current_price,
            target_up=target_up,
            target_down=target_down,
            volatility_pct=volatility_pct,
            time_remaining_minutes=time_remaining_minutes,
            vol_period_minutes=60.0,
        )
        
        print(f"Входные данные:")
        print(f"  current_price = {current_price}")
        print(f"  target_up = {target_up}")
        print(f"  target_down = {target_down}")
        print(f"  volatility_pct = {volatility_pct} ({volatility_pct*100:.1f}%)")
        print(f"  time_remaining_minutes = {time_remaining_minutes}")
        
        print(f"\nРЕЗУЛЬТАТЫ:")
        print(f"  15-min vol: p_up = {result_15min['p_up']:.6f} ({result_15min['p_up']*100:.3f}%), p_down = {result_15min['p_down']:.6f} ({result_15min['p_down']*100:.3f}%)")
        print(f"  60-min vol: p_up = {result_60min['p_up']:.6f} ({result_60min['p_up']*100:.3f}%), p_down = {result_60min['p_down']:.6f} ({result_60min['p_down']*100:.3f}%)")
        
        # Проверки
        self.assertGreater(result_15min['p_up'], 0.0)
        self.assertGreater(result_15min['p_down'], 0.0)
        self.assertGreater(result_60min['p_up'], 0.0)
        self.assertGreater(result_60min['p_down'], 0.0)
        
        # С 15-минутной волатильностью (более реактивной) вероятности могут быть выше
        # Но это зависит от конкретных параметров


if __name__ == '__main__':
    unittest.main(verbosity=2)