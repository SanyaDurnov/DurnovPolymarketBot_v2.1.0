"""
Position - объект позиции для хранения информации о сделках.

Хранит полную информацию о покупке/продаже, включая технические индикаторы,
математические вероятности и причины принятия решений.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, List
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class Position:
    """
    Объект позиции с полной информацией о сделке.

    Хранит данные о входе в позицию, технических индикаторах на момент входа,
    математических вероятностях и результатах.
    """

    # Основная информация
    position_id: str
    market_id: str
    market_title: str
    symbol: str
    side: str  # "UP" или "DOWN"
    entry_time: datetime
    entry_price_avg: float
    total_volume: float  # outcome tokens
    total_cost_usd: float

    # Информация о решении входа
    entry_reason: str  # "FIRST_ENTRY", "MANUAL", etc.
    market_start_time: Optional[datetime] = None
    minutes_until_start: Optional[float] = None

    # Технические индикаторы на момент входа
    momentum_score: Optional[float] = None
    momentum_data: Optional[Dict[str, float]] = None  # {"1m": 0.5, "5m": 0.8, ...}
    volatility_data: Optional[Dict[str, float]] = None
    trend_direction: Optional[str] = None  # "BULLISH", "BEARISH", "SIDEWAYS"

    # Математические вероятности
    math_probability: Optional[float] = None
    edge: Optional[float] = None
    recommended_side: Optional[str] = None
    confidence_score: Optional[float] = None

    # Статус и результаты
    status: str = "OPEN"  # "OPEN", "CLOSED", "PARTIAL_EXIT"
    start_price: Optional[float] = None  # Price to beat (цена актива на момент старта рынка)
    exit_time: Optional[datetime] = None
    exit_price: Optional[float] = None  # Цена актива на момент закрытия рынка
    pnl_usd: float = 0.0
    pnl_pct: float = 0.0

    def to_dict(self) -> Dict:
        """Преобразовать в словарь для JSON сериализации."""
        data = asdict(self)
        # Преобразовать datetime в ISO строки
        if isinstance(data['entry_time'], datetime):
            data['entry_time'] = data['entry_time'].isoformat()
        if data['market_start_time'] and isinstance(data['market_start_time'], datetime):
            data['market_start_time'] = data['market_start_time'].isoformat()
        if data['exit_time'] and isinstance(data['exit_time'], datetime):
            data['exit_time'] = data['exit_time'].isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Dict) -> 'Position':
        """Создать объект из словаря."""
        # Преобразовать ISO строки обратно в datetime
        if 'entry_time' in data and data['entry_time']:
            data['entry_time'] = datetime.fromisoformat(data['entry_time'])
        if 'market_start_time' in data and data['market_start_time']:
            data['market_start_time'] = datetime.fromisoformat(data['market_start_time'])
        if 'exit_time' in data and data['exit_time']:
            data['exit_time'] = datetime.fromisoformat(data['exit_time'])
        return cls(**data)

    def calculate_pnl(self, exit_price: float, exit_time: Optional[datetime] = None) -> None:
        """Рассчитать P&L при выходе из позиции."""
        if exit_price <= 0:
            return

        # Для упрощения рассчитываем P&L как разницу между средней ценой входа и выхода
        # В реальности нужно учитывать outcome tokens и их стоимость
        price_diff = exit_price - self.entry_price_avg
        self.pnl_usd = price_diff * self.total_volume
        self.pnl_pct = (price_diff / self.entry_price_avg) * 100 if self.entry_price_avg > 0 else 0

        self.exit_price = exit_price
        self.exit_time = exit_time or datetime.now()
        self.status = "CLOSED"

        logger.info(f"📊 P&L для позиции {self.position_id}: ${self.pnl_usd:.2f} ({self.pnl_pct:.2f}%)")


class PositionStorage:
    """
    Хранилище позиций в JSON файле.

    Позволяет сохранять и загружать позиции, вести историю сделок.
    """

    def __init__(self, file_path: str = "data/positions.json"):
        self.file_path = Path(file_path)
        self.file_path.parent.mkdir(exist_ok=True)
        self.positions: Dict[str, Position] = {}
        self._load_positions()
        # Проверка и закрытие позиций в закрытых рынках при инициализации
        self._check_and_close_expired_positions()

    def _load_positions(self) -> None:
        """Загрузить позиции из файла."""
        try:
            if self.file_path.exists():
                with open(self.file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                positions_data = data.get('positions', [])
                for pos_data in positions_data:
                    try:
                        position = Position.from_dict(pos_data)
                        self.positions[position.position_id] = position
                    except Exception as e:
                        logger.error(f"Ошибка загрузки позиции {pos_data.get('position_id', 'unknown')}: {e}")

                logger.info(f"📁 Загружено {len(self.positions)} позиций из {self.file_path}")
            else:
                logger.info(f"📁 Файл позиций не найден, начинаем с пустого хранилища")
        except Exception as e:
            logger.error(f"Ошибка загрузки файла позиций: {e}")
            self.positions = {}

    def _save_positions(self) -> None:
        """Сохранить позиции в файл."""
        try:
            positions_data = [pos.to_dict() for pos in self.positions.values()]

            data = {
                'last_updated': datetime.now().isoformat(),
                'total_positions': len(positions_data),
                'positions': positions_data
            }

            with open(self.file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            logger.debug(f"💾 Сохранено {len(positions_data)} позиций в {self.file_path}")
        except Exception as e:
            logger.error(f"Ошибка сохранения позиций: {e}")

    def add_position(self, position: Position) -> None:
        """Добавить новую позицию."""
        self.positions[position.position_id] = position
        self._save_positions()
        logger.info(f"➕ Добавлена позиция {position.position_id} ({position.side} {position.symbol})")

    def get_position(self, position_id: str) -> Optional[Position]:
        """Получить позицию по ID."""
        return self.positions.get(position_id)

    def get_all_positions(self) -> List[Position]:
        """Получить все позиции."""
        return list(self.positions.values())

    def get_open_positions(self) -> List[Position]:
        """Получить открытые позиции."""
        return [pos for pos in self.positions.values() if pos.status == "OPEN"]

    def get_closed_positions(self) -> List[Position]:
        """Получить закрытые позиции."""
        return [pos for pos in self.positions.values() if pos.status == "CLOSED"]

    def update_position(self, position: Position) -> None:
        """Обновить существующую позицию."""
        if position.position_id in self.positions:
            self.positions[position.position_id] = position
            self._save_positions()
            logger.debug(f"🔄 Обновлена позиция {position.position_id}")
        else:
            logger.warning(f"Попытка обновить несуществующую позицию {position.position_id}")

    def close_position(self, position_id: str, exit_price: float) -> Optional[Position]:
        """Закрыть позицию по цене выхода."""
        position = self.get_position(position_id)
        if position and position.status == "OPEN":
            position.calculate_pnl(exit_price)
            self.update_position(position)
            logger.info(f"🔒 Закрыта позиция {position_id} по цене ${exit_price:.4f}")
            return position
        return None

    def close_market_positions(self, market_id: str, outcome: str, end_price: float) -> List[Position]:
        """
        Закрыть все открытые позиции по рынку на основе исхода рынка.

        Args:
            market_id: ID рынка
            outcome: Исход рынка ("UP" или "DOWN")
            end_price: Цена актива на конец рынка

        Returns:
            Список закрытых позиций
        """
        closed_positions = []

        # Найти все открытые позиции по этому рынку
        market_positions = [pos for pos in self.positions.values()
                           if pos.market_id == market_id and pos.status == "OPEN"]

        if not market_positions:
            logger.info(f"📭 Нет открытых позиций для закрытия в рынке {market_id}")
            return closed_positions

        logger.info(f"🎯 Закрываем {len(market_positions)} позиций в рынке {market_id} (исход: {outcome})")

        for position in market_positions:
            # Рассчитать P&L по логике Polymarket
            # Извлекаем строку исхода из словаря
            outcome_str = outcome.get("outcome") if isinstance(outcome, dict) else outcome
            pnl = calculate_polymarket_pnl(position, outcome_str)

            # Закрыть позицию
            position.pnl_usd = pnl
            position.pnl_pct = (pnl / position.total_cost_usd) * 100 if position.total_cost_usd > 0 else 0
            position.exit_price = end_price
            position.exit_time = datetime.now()
            position.status = "CLOSED"

            # Обновить в хранилище
            self.update_position(position)
            closed_positions.append(position)

            # Обновить SIM баланс если в SIM режиме
            from app.config import SIM_MODE
            if SIM_MODE:
                simulation_manager.update_balance(pnl)

            logger.info(f"🔒 Закрыта позиция {position.position_id}: {position.side} → {outcome_str}, P&L=${pnl:.2f}")

        logger.info(f"✅ Закрыто {len(closed_positions)} позиций в рынке {market_id}")
        return closed_positions

    def _check_and_close_expired_positions(self) -> None:
        """Проверить и закрыть позиции в закрытых рынках при инициализации."""
        try:
            from polymarket.client import PolymarketClient
            pm_client = PolymarketClient()
            
            open_positions = self.get_open_positions()
            logger.info(f"🔍 Проверка {len(open_positions)} открытых позиций на закрытые рынки")
            
            for position in open_positions:
                try:
                    # Получаем данные о рынке
                    market_data = pm_client.get_market_data(position.market_id)
                    
                    if market_data and not market_data.get('active', True):
                        logger.info(f"📉 Рынок {position.market_id} закрыт, закрываем позицию {position.position_id}")
                        
                        # Определяем исход рынка (простая логика для симуляции)
                        import random
                        outcome = random.choice(["UP", "DOWN"])
                        
                        # Закрываем позицию
                        self.close_market_positions(position.market_id, outcome, 0)
                        
                except Exception as e:
                    logger.error(f"Ошибка при проверке рынка {position.market_id}: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"Ошибка при проверке закрытых рынков: {e}")

    def get_stats(self) -> Dict:
        """Получить статистику по позициям."""
        all_positions = self.get_all_positions()
        open_positions = self.get_open_positions()
        closed_positions = self.get_closed_positions()

        total_pnl = sum(pos.pnl_usd for pos in closed_positions)
        total_trades = len(closed_positions)

        winning_trades = len([pos for pos in closed_positions if pos.pnl_usd > 0])
        losing_trades = len([pos for pos in closed_positions if pos.pnl_usd < 0])

        win_rate = winning_trades / total_trades if total_trades > 0 else 0

        return {
            'total_positions': len(all_positions),
            'open_positions': len(open_positions),
            'closed_positions': len(closed_positions),
            'total_pnl_usd': total_pnl,
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'win_rate': win_rate
        }

    def clear_all_positions(self) -> None:
        """Очистить все позиции из хранилища и файла."""
        self.positions.clear()
        self._save_positions()
        logger.info("🧹 Все позиции очищены из хранилища и файла")


# Глобальный экземпляр хранилища позиций
position_storage = PositionStorage()


class SimulationManager:
    """
    Менеджер симуляции для учета баланса и результатов в SIM режиме.
    Считает баланс только за текущую сессию (не сохраняет между перезапусками).
    """

    def __init__(self, initial_balance: float = 1000.0):
        """
        Args:
            initial_balance: Начальный баланс для симуляции
        """
        self.initial_balance = initial_balance
        self.current_balance = initial_balance
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        self.total_pnl = 0.0

    def update_balance(self, pnl_amount: float) -> None:
        """
        Обновить баланс после закрытия позиции.

        Args:
            pnl_amount: Сумма P&L (может быть отрицательной)
        """
        self.current_balance += pnl_amount
        self.total_pnl += pnl_amount
        self.total_trades += 1

        if pnl_amount > 0:
            self.winning_trades += 1
        elif pnl_amount < 0:
            self.losing_trades += 1

        logger.info(f"💰 SIM баланс обновлен: ${self.current_balance:.2f} (P&L: ${pnl_amount:.2f})")

    def get_balance(self) -> float:
        """Получить текущий баланс."""
        return self.current_balance

    def get_stats(self) -> Dict[str, float]:
        """Получить статистику симуляции."""
        win_rate = self.winning_trades / self.total_trades if self.total_trades > 0 else 0
        return {
            'initial_balance': self.initial_balance,
            'current_balance': self.current_balance,
            'total_pnl': self.total_pnl,
            'total_trades': self.total_trades,
            'winning_trades': self.winning_trades,
            'losing_trades': self.losing_trades,
            'win_rate': win_rate
        }

    def reset(self) -> None:
        """Сбросить симуляцию (для новой сессии)."""
        self.current_balance = self.initial_balance
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        self.total_pnl = 0.0
        logger.info(f"🔄 SIM сброшен к начальному балансу: ${self.initial_balance:.2f}")


# Глобальный экземпляр менеджера симуляции
simulation_manager = SimulationManager()


def determine_market_outcome(price_to_beat: float, end_price: float) -> Dict:
    """
    Определить исход рынка на основе price_to_beat и цены на конец рынка.

    Args:
        price_to_beat: Целевая цена (из market data)
        end_price: Цена актива на момент окончания рынка

    Returns:
        Словарь с результатом: {"outcome": "UP"|"DOWN", "end_price": float}
    """
    logger.info(f"🎯 ОПРЕДЕЛЕНИЕ ИСХОДА РЫНКА:")
    logger.info(f"   price_to_beat: ${price_to_beat:.4f}")
    logger.info(f"   end_price: ${end_price:.4f}")
    logger.info(f"   Разница: ${end_price - price_to_beat:.4f}")
    
    if end_price >= price_to_beat:
        logger.info(f"   Результат: UP побеждает (end_price >= price_to_beat)")
        return {"outcome": "UP", "end_price": end_price}
    else:
        logger.info(f"   Результат: DOWN побеждает (end_price < price_to_beat)")
        return {"outcome": "DOWN", "end_price": end_price}


def calculate_polymarket_pnl(position: Position, outcome: str) -> float:
    """
    Рассчитать P&L для позиции в Polymarket на основе исхода рынка.

    Логика Polymarket:
    - Проигрышная позиция: теряет 100% invested
    - Выигрышная позиция: получает payout = 1 / winning_price, затем - invested - fees

    Args:
        position: Позиция для расчета
        outcome: Исход рынка ("UP" или "DOWN")

    Returns:
        P&L в USD (может быть отрицательным)
    """
    logger.info(f"💰 РАСЧЕТ P&L для позиции {position.position_id}:")
    logger.info(f"   Сторона позиции: {position.side}")
    logger.info(f"   Исход рынка: {outcome}")
    logger.info(f"   Цена входа: ${position.entry_price_avg:.4f}")
    logger.info(f"   Инвестировано: ${position.total_cost_usd:.2f}")
    
    invested = position.total_cost_usd

    if position.side == outcome:
        # Выигрышная позиция
        # payout = 1 / winning_price (цена на момент входа)
        # payout = invested / entry_price (поскольку invested = amount * entry_price)
        payout = invested / position.entry_price_avg if position.entry_price_avg > 0 else 0
        fees = payout * 0.02
        pnl = payout - invested - fees
        
        logger.info(f"   ✅ ВЫИГРЫШ: payout=${payout:.2f}, fees=${fees:.2f}, P&L=${pnl:.2f}")
        return pnl
    else:
        # Проигрышная позиция - теряет все
        pnl = -invested
        logger.info(f"   ❌ ПРОИГРЫШ: потеряно ${invested:.2f}")
        return pnl
