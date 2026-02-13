#!/usr/bin/env python3
"""
Тест функции объединения позиций в PositionManagerBalancedTrading
"""

import asyncio
from datetime import datetime, timezone
from trading.position import Position
from trading.position_manager_balanced_trading import PositionManagerBalancedTrading


async def test_merge_positions():
    """Тестируем функцию объединения позиций."""

    # Создаем тестовый менеджер
    manager = PositionManagerBalancedTrading("test_market", None, None, None)

    # Создаем тестовые позиции UP с разными ценами
    pos1 = Position(
        position_id="test_pos_1",
        market_id="test_market",
        market_title="Test Market",
        symbol="BTCUSDT",
        side="UP",
        entry_time=datetime.now(timezone.utc),
        entry_price_avg=0.40,
        total_volume=10.0,
        total_cost_usd=4.0,
        entry_reason="TEST_1"
    )

    pos2 = Position(
        position_id="test_pos_2",
        market_id="test_market",
        market_title="Test Market",
        symbol="BTCUSDT",
        side="UP",
        entry_time=datetime.now(timezone.utc),
        entry_price_avg=0.50,
        total_volume=10.0,
        total_cost_usd=5.0,
        entry_reason="TEST_2"
    )

    pos3 = Position(
        position_id="test_pos_3",
        market_id="test_market",
        market_title="Test Market",
        symbol="BTCUSDT",
        side="UP",
        entry_time=datetime.now(timezone.utc),
        entry_price_avg=0.60,
        total_volume=5.0,
        total_cost_usd=3.0,
        entry_reason="TEST_3"
    )

    # Добавляем позиции в менеджер
    manager.positions_up = [pos1, pos2, pos3]
    manager.positions = [pos1, pos2, pos3]

    print("📊 ДО объединения:")
    print(f"   Позиций UP: {len(manager.positions_up)}")
    total_cost = sum(p.total_cost_usd for p in manager.positions_up)
    total_volume = sum(p.total_volume for p in manager.positions_up)
    avg_price = total_cost / total_volume if total_volume > 0 else 0
    print(f"   Общая стоимость: ${total_cost:.2f}")
    print(f"   Средняя цена: ${avg_price:.4f}")
    for i, pos in enumerate(manager.positions_up):
        print(f"      {i+1}. ${pos.total_cost_usd:.2f} @ ${pos.entry_price_avg:.4f} ({pos.entry_reason})")
    print()

    # Объединяем позиции
    result = await manager.merge_positions_by_side("UP")

    print("🔄 РЕЗУЛЬТАТ объединения:")
    print(f"   Успешно: {result}")
    print(f"   Позиций UP после: {len(manager.positions_up)}")
    print(f"   Всего позиций: {len(manager.positions)}")

    if manager.positions_up:
        merged_pos = manager.positions_up[0]
        print("\n📈 ОБЪЕДИНЕННАЯ ПОЗИЦИЯ:")
        print(f"   Стоимость: ${merged_pos.total_cost_usd:.2f}")
        print(f"   Средняя цена: ${merged_pos.entry_price_avg:.4f}")
        print(f"   Причина: {merged_pos.entry_reason}")
        print(f"   Время входа: {merged_pos.entry_time}")

    print("\n✅ Тест завершен!")


if __name__ == "__main__":
    asyncio.run(test_merge_positions())