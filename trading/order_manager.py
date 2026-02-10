"""
Order Manager - управление покупками и продажами с поддержкой SIM MODE.
"""

import logging
from typing import Dict, Optional

from trading.position_simulator import PositionSimulator

logger = logging.getLogger(__name__)


class OrderManager:
    """
    Управление ордерами с поддержкой режима симуляции (SIM MODE).
    
    В SIM MODE: все ордера симулируются через PositionSimulator.
    В REAL MODE: ордера отправляются на Polymarket через polymarket_client.
    """
    
    def __init__(
        self,
        polymarket_client,
        orderbook_analyzer=None,
        sim_mode: bool = True,
        initial_balance: float = 10000.0,
        trading_fee_pct: float = 0.02,
    ):
        """
        Args:
            polymarket_client: Экземпляр PolymarketClient
            orderbook_analyzer: Анализатор orderbook (опционально)
            sim_mode: True = симуляция, False = реальная торговля
            initial_balance: Начальный баланс для симуляции
            trading_fee_pct: Процент комиссии (по умолчанию 2%)
        """
        self.polymarket_client = polymarket_client
        self.orderbook_analyzer = orderbook_analyzer
        self.sim_mode = sim_mode
        
        # Инициализируем симулятор если в SIM MODE
        self.simulator = None
        if self.sim_mode:
            self.simulator = PositionSimulator(
                initial_balance=initial_balance,
                trading_fee_pct=trading_fee_pct,
            )
            logger.info("OrderManager инициализирован в SIM MODE (баланс: $%.2f)", initial_balance)
        else:
            logger.warning("OrderManager инициализирован в REAL MODE")
    
    def buy_outcome(
        self,
        market_id: str,
        side: str,
        amount_usdc: float,
        price: float,
    ) -> Dict:
        """
        Купить исход (UP или DOWN).
        
        Args:
            market_id: ID рынка
            side: "UP" или "DOWN"
            amount_usdc: Сумма в USDC
            price: Лимитная цена
            
        Returns:
            {
                "success": bool,
                "mode": "SIM" | "REAL",
                "side": str,
                "amount": float,
                "price": float,
                "order": dict (только для REAL mode)
            }
        """
        side = side.upper()
        
        if self.sim_mode:
            # Симуляция покупки
            logger.info("[SIM] BUY %s @ $%.4f (amount: $%.2f)", side, price, amount_usdc)
            
            # В симуляции покупка успешна если есть баланс
            if self.simulator and amount_usdc <= self.simulator.current_balance:
                success = True
                message = f"Симулирована покупка {side}"
            else:
                success = False
                message = "Недостаточно средств для симуляции"
            
            return {
                "success": success,
                "mode": "SIM",
                "side": side,
                "amount": amount_usdc,
                "price": price,
                "message": message,
            }
        else:
            # Реальная покупка через Polymarket
            logger.info("[REAL] BUY %s @ $%.4f (amount: $%.2f)", side, price, amount_usdc)
            
            try:
                # Определяем outcome: 0 = UP, 1 = DOWN
                outcome = 0 if side == "UP" else 1
                
                order = self.polymarket_client.buy_outcome(
                    market_id=market_id,
                    outcome=outcome,
                    amount_usdc=amount_usdc,
                    max_price=price,
                )
                
                success = order is not None
                
                return {
                    "success": success,
                    "mode": "REAL",
                    "side": side,
                    "amount": amount_usdc,
                    "price": price,
                    "order": order,
                }
            except Exception as exc:
                logger.error("Ошибка при создании BUY ордера: %s", exc)
                return {
                    "success": False,
                    "mode": "REAL",
                    "side": side,
                    "amount": amount_usdc,
                    "price": price,
                    "error": str(exc),
                }
    
    def sell_outcome(
        self,
        market_id: str,
        side: str,
        amount_usdc: float,
        price: float,
    ) -> Dict:
        """
        Продать исход (UP или DOWN).
        
        Args:
            market_id: ID рынка
            side: "UP" или "DOWN"
            amount_usdc: Сумма в USDC
            price: Лимитная цена
            
        Returns:
            Аналогично buy_outcome
        """
        side = side.upper()
        
        if self.sim_mode:
            # Симуляция продажи
            logger.info("[SIM] SELL %s @ $%.4f (amount: $%.2f)", side, price, amount_usdc)
            
            return {
                "success": True,
                "mode": "SIM",
                "side": side,
                "amount": amount_usdc,
                "price": price,
                "message": f"Симулирована продажа {side}",
            }
        else:
            # Реальная продажа через Polymarket
            logger.info("[REAL] SELL %s @ $%.4f (amount: $%.2f)", side, price, amount_usdc)
            
            try:
                outcome = 0 if side == "UP" else 1
                
                order = self.polymarket_client.sell_outcome(
                    market_id=market_id,
                    outcome=outcome,
                    amount_usdc=amount_usdc,
                    min_price=price,
                )
                
                success = order is not None
                
                return {
                    "success": success,
                    "mode": "REAL",
                    "side": side,
                    "amount": amount_usdc,
                    "price": price,
                    "order": order,
                }
            except Exception as exc:
                logger.error("Ошибка при создании SELL ордера: %s", exc)
                return {
                    "success": False,
                    "mode": "REAL",
                    "side": side,
                    "amount": amount_usdc,
                    "price": price,
                    "error": str(exc),
                }
    
    def get_open_positions(self) -> list:
        """
        Получить список открытых позиций.
        
        Returns:
            Список позиций
        """
        if self.sim_mode and self.simulator:
            return list(self.simulator.positions.values())
        else:
            # TODO: Реализовать получение реальных позиций через API
            logger.warning("Получение реальных позиций пока не реализовано")
            return []
    
    def get_closed_positions(self) -> list:
        """
        Получить список закрытых позиций.
        
        Returns:
            Список закрытых позиций
        """
        if self.sim_mode and self.simulator:
            return self.simulator.closed_positions
        else:
            # TODO: Реализовать получение реальных закрытых позиций
            return []
    
    def get_stats(self) -> Dict:
        """
        Получить статистику торговли.
        
        Returns:
            {
                "mode": "SIM" | "REAL",
                "initial_balance": float,
                "current_balance": float,
                "total_pnl": float,
                "pnl_pct": float,
                "total_fees": float,
                "open_positions": int,
                "closed_positions": int,
                "winning_positions": int,
                "losing_positions": int,
                "win_rate": float
            }
        """
        if self.sim_mode and self.simulator:
            stats = self.simulator.get_stats()
            stats["mode"] = "SIM"
            return stats
        else:
            # TODO: Реализовать получение реальной статистики
            return {
                "mode": "REAL",
                "message": "Real stats not implemented yet",
            }
    
    def get_balance(self) -> float:
        """
        Получить текущий баланс.
        
        Returns:
            Баланс в USDC
        """
        if self.sim_mode and self.simulator:
            return self.simulator.current_balance
        else:
            # TODO: Получить реальный баланс через API
            balance = self.polymarket_client.get_balance()
            if balance:
                # Извлекаем USDC баланс
                # Формат зависит от API
                return float(balance.get("usdc", 0))
            return 0.0
