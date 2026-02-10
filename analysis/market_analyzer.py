
"""
Market Analyzer - главный класс для комплексного анализа рынков Polymarket.
Объединяет все компоненты: orderbook, price monitoring, probability analysis.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Optional

from analysis.probability import PostEntryProbabilityAnalyzer

logger = logging.getLogger(__name__)


class MarketAnalyzer:
    """
    Главный анализатор рынка.
    Объединяет все компоненты системы для полного анализа рынка.
    """

    def __init__(
        self,
        price_monitor,
        polymarket_client,
        orderbook_analyzer,
    ):
        """
        Args:
            price_monitor: Экземпляр PriceMonitor из monitoring.price_monitor
            polymarket_client: Экземпляр PolymarketClient из polymarket.client
            orderbook_analyzer: Экземпляр OrderbookAnalyzer из polymarket.orderbook
        """
        self.price_monitor = price_monitor
        self.polymarket_client = polymarket_client
        self.orderbook_analyzer = orderbook_analyzer
        self.probability_analyzer = PostEntryProbabilityAnalyzer()

        # Единый сервис для получения price_to_beat
        from analysis.price_to_beat_service import PriceToBeatService
        self.price_to_beat_service = PriceToBeatService(price_monitor, polymarket_client)
    
    async def analyze_market(self, market_id: str) -> Optional[Dict]:
        """
        Выполнить полный анализ рынка.

        Args:
            market_id: ID рынка на Polymarket

        Returns:
            Полный анализ рынка или None если произошла ошибка
        """
        try:
            # 1. Получаем данные о рынке
            market_data = self.polymarket_client.get_market_data(market_id)
            if not market_data:
                logger.error("Не удалось получить данные рынка %s", market_id)
                return None

            # 2. Проверяем статус рынка СРАЗУ после получения данных
            market_closed = market_data.get("closed", False)
            market_active = market_data.get("active", True)
            market_locked = market_data.get("locked", False)

            # Конвертируем строковые значения
            if isinstance(market_closed, str):
                market_closed = market_closed.lower() in ("true", "1", "yes")
            if isinstance(market_active, str):
                market_active = market_active.lower() in ("true", "1", "yes")
            if isinstance(market_locked, str):
                market_locked = market_locked.lower() in ("true", "1", "yes")

            # Рынок неактивен если: закрыт ИЛИ не активен ИЛИ заблокирован
            market_inactive = market_closed or not market_active or (market_locked is True)

            title = (
                market_data.get("question")  # Polymarket API использует "question"
                or market_data.get("title")
                or market_data.get("name")
                or market_data.get("slug", "")
                or ""
            )

            # 3. Определяем символ (BTC/ETH/SOL) из названия
            symbol = self._infer_symbol(title)
            if not symbol:
                logger.warning("Не удалось определить символ из названия: %s", title)
                return None

            # 4. Получаем текущую цену актива из Binance (индикаторы)
            current_price = self.price_monitor.get_price(symbol)
            if not current_price:
                logger.warning("Не удалось получить текущую цену для %s из Binance", symbol)
                return None

            # 5. Получаем волатильность (всегда, независимо от статуса рынка)
            volatility = self.price_monitor.get_volatility(symbol)
            if not volatility:
                volatility = {}

            # Если рынок неактивен, возвращаем специальный ответ БЕЗ запроса ордербука
            if market_inactive:
                logger.info("Рынок %s неактивен (closed=%s, active=%s, locked=%s) - возвращаем статус inactive",
                           market_id, market_closed, market_active, market_locked)
                # Удаляем из активных рынков, если он там был
                self.orderbook_analyzer.remove_inactive_market(market_id)

                # Проверяем и закрываем позиции по этому рынку
                await self._close_market_positions_if_needed(market_id, symbol, market_data)
                return {
                    "market_id": market_id,
                    "title": title,
                    "symbol": symbol,
                    "status": "inactive",
                    "message": "Market is inactive",
                    "current_price": current_price,
                    "price_to_beat": current_price,  # Используем текущую цену
                    "deviation": {
                        "deviation_pct": 0.0,
                        "deviation_abs": 0.0,
                        "position": "AT_START",
                        "description": "Рынок неактивен"
                    },
                    "market_target": current_price,
                    "direction": "UP",
                    "orderbook": {
                        "message": "Market is inactive"
                    },
                    "volatility": volatility,
                    "probabilities": {
                        "up": {"edge": 0.0, "math_prob": 0.5},
                        "down": {"edge": 0.0, "math_prob": 0.5}
                    },
                    "indicators": {},
                    "time_metrics": {
                        "time_remaining_minutes": 0,
                        "market_duration_minutes": 0,
                        "minutes_to_close": 0,
                        "minutes_since_open": 0
                    },
                    "recommendation": {
                        "action": "HOLD",
                        "confidence": 0.0,
                        "reason": "Market is inactive"
                    },
                    "timestamp": datetime.now().isoformat(),
                }

            # 6. Рынок активен - добавляем в кэш orderbook для автоматического обновления
            self.orderbook_analyzer.add_active_market(market_id)

            # 7. Получаем orderbook и лучшие цены
            orderbook_prices = self.orderbook_analyzer.get_market_prices(market_id)

            # Для активных рынков получаем orderbook
            if not orderbook_prices:
                logger.warning("Не удалось получить orderbook для рынка %s", market_id)
                return None

            # 6. Временные метрики
            time_metrics = self._get_time_metrics(title)

            # 7. Получаем Price_to_beat (цена на момент открытия рынка)
            price_to_beat = await self.price_to_beat_service.get_price_to_beat(market_id)
            if price_to_beat is None:
                logger.debug(f"Не удалось получить price_to_beat для рынка {market_id}")
                return None

            # 8. Определяем market_target и direction на основе price_to_beat
            market_target = price_to_beat
            market_direction = "UP" if current_price < price_to_beat else "DOWN"

            # 🔍 DEBUG: Логируем market_target перед передачей в _calculate_probabilities
            logger.warning(f"🔍 DEBUG analyze_market: market_target={market_target}, price_to_beat={price_to_beat}, current_price={current_price}")
            if market_target < 1:
                logger.error(f"🚨🚨🚨 CRITICAL: market_target < $1 в analyze_market! market_target={market_target}")
                logger.error(f"   price_to_beat={price_to_beat}, current_price={current_price}")
                logger.error(f"   market_id={market_id}, symbol={symbol}")

            # 9. Получаем ATR для гибридной волатильности
            stats = self.price_monitor.get_stats(symbol)
            atr = stats.get("atr") if stats else None

            # 10. Рассчитываем вероятности для UP и DOWN
            probabilities = self._calculate_probabilities(
                current_price=current_price,
                market_target=market_target,
                market_direction=market_direction,
                volatility=volatility,
                orderbook_prices=orderbook_prices,
                time_remaining_minutes=time_metrics.get("time_remaining_minutes", 60),
                time_metrics=time_metrics,
                atr=atr,
            )

            # 11. Рассчитываем absorption probabilities (вероятность остаться выше/ниже таргета)
            absorption_probabilities = self._calculate_absorption_probabilities(
                current_price=current_price,
                market_target=market_target,
                volatility=volatility,
                time_remaining_minutes=time_metrics.get("time_remaining_minutes", 60),
                atr=atr,
            )

            # 11. Получаем индикаторы
            indicators = stats if stats else {}

            # 12. Генерируем рекомендацию
            recommendation = self._generate_recommendation(
                probabilities=probabilities,
                indicators=indicators,
                time_metrics=time_metrics,
                orderbook_prices=orderbook_prices,
            )

            deviation_info = self._calculate_deviation(current_price, price_to_beat)

            return {
                "market_id": market_id,
                "title": title,
                "symbol": symbol,
                "current_price": current_price,
                "price_to_beat": price_to_beat,
                "deviation": deviation_info,
                "market_target": market_target,
                "direction": market_direction,
                "orderbook": orderbook_prices,
                "volatility": volatility,
                "probabilities": probabilities,
                "absorption_probabilities": absorption_probabilities,
                "indicators": indicators,
                "time_metrics": time_metrics,
                "recommendation": recommendation,
                "timestamp": datetime.now().isoformat(),
            }
            
        except Exception as exc:
            logger.error("Ошибка при анализе рынка %s: %s", market_id, exc, exc_info=True)
            return None
    
    def _infer_symbol(self, title: str) -> Optional[str]:
        """
        Определить символ криптовалюты из названия рынка.
        
        Args:
            title: Название рынка
            
        Returns:
            "BTCUSDT", "ETHUSDT", "SOLUSDT" или None
        """
        title_lower = title.lower()
        
        if "bitcoin" in title_lower or "btc" in title_lower:
            return "BTCUSDT"
        elif "ethereum" in title_lower or "eth" in title_lower:
            return "ETHUSDT"
        elif "solana" in title_lower or "sol" in title_lower:
            return "SOLUSDT"
        
        return None
    

    
    def _get_time_metrics(self, title: str) -> Dict:
        """
        Получить временные метрики из названия рынка.

        Args:
            title: Название рынка

        Returns:
            {
                "time_remaining_minutes": float,
                "market_duration_minutes": float,
                "minutes_to_close": float,
                "minutes_since_open": float
            }
        """
        # Используем методы из polymarket_client для извлечения времени
        start_time = self.polymarket_client.get_market_start_time(title)
        end_time = self.polymarket_client.get_market_end_time(title)

        # Используем Polymarket время (ET)
        from app.filter_generator import get_polymarket_time
        now = get_polymarket_time()

        if start_time and end_time:
            # Время уже в правильном часовом поясе (ET)
            # Не конвертируем в UTC, оставляем как есть
            time_remaining = (end_time - now).total_seconds() / 60
            duration = (end_time - start_time).total_seconds() / 60
            since_open = (now - start_time).total_seconds() / 60
            to_close = time_remaining
        else:
            # Fallback значения
            time_remaining = 60.0
            duration = 15.0
            since_open = 0.0
            to_close = 60.0

        return {
            "time_remaining_minutes": max(0, time_remaining),
            "market_duration_minutes": duration,
            "minutes_to_close": max(0, to_close),
            "minutes_since_open": max(0, since_open),
            "start_time": start_time,  # Добавляем время открытия
            "end_time": end_time,     # Добавляем время закрытия
        }
    
    def _calculate_probabilities(
        self,
        current_price: float,
        market_target: float,
        market_direction: str,
        volatility: Dict,
        orderbook_prices: Dict,
        time_remaining_minutes: float,
        time_metrics: Dict,
        atr: Optional[float],
    ) -> Dict:
        # 🔍 DEBUG: Логируем входные параметры для отладки target_price
        logger.warning(f"🔍 DEBUG _calculate_probabilities: market_target={market_target}, current_price={current_price}, direction={market_direction}")
        if market_target < 1:
            logger.error(f"🚨🚨🚨 CRITICAL: market_target < $1! Это неправильная цена! market_target={market_target}")
            logger.error(f"   current_price={current_price}, direction={market_direction}")
            logger.error(f"   Проверьте откуда пришел этот target_price!")
            # Не возвращаем ошибку, продолжаем расчет, но логируем проблему
        """
        Рассчитать вероятности для UP и DOWN.

        Returns:
            {
                "up": {...},
                "down": {...}
            }
        """
        # Определяем продолжительность рынка
        market_duration = time_metrics.get("market_duration_minutes", 15.0)

        # Выбираем волатильность и период в зависимости от продолжительности рынка
        if market_duration >= 45:  # Часовые рынки (~60 мин)
            vol_pct = volatility.get("1h") or volatility.get("15m") or volatility.get("5m") or 1.0
            vol_period_minutes = 60.0  # 1 час
            vol_timeframe = "1h"
        else:  # 15-минутные рынки
            vol_pct = volatility.get("15m") or volatility.get("1h") or volatility.get("5m") or 1.0
            vol_period_minutes = 15.0  # 15 минут
            vol_timeframe = "15m"

        logger.info(f"DEBUG VOL: market_duration={market_duration}, vol_1h={volatility.get('1h')}, vol_15m={volatility.get('15m')}, vol_pct={vol_pct}, vol_period_minutes={vol_period_minutes}, time_remaining_minutes={time_remaining_minutes}")

        current_price_up = orderbook_prices.get("up_ask", 0.5)
        current_price_down = orderbook_prices.get("down_ask", 0.5)

        logger.info(f"PROB CALC: current_price={current_price}, target={market_target}, direction={market_direction}, up_price={current_price_up}, down_price={current_price_down}")

        # Конвертируем волатильность из процентов в десятичную форму для probability_analyzer
        vol_pct_decimal = vol_pct / 100.0  # 0.2939% → 0.002939 (decimal)

        # Рассчитываем для UP
        prob_up = self.probability_analyzer.analyze_opposite_side_buy(
            current_price_btc=current_price,
            market_target=market_target,
            market_direction=market_direction,
            opposite_side="UP",
            volatility_pct=vol_pct_decimal,  # Теперь в десятичной форме
            time_remaining_minutes=time_remaining_minutes,
            current_price_up=current_price_up,
            current_price_down=current_price_down,
            atr=atr,
            vol_period_minutes=vol_period_minutes,
        )

        # Рассчитываем для DOWN
        prob_down = self.probability_analyzer.analyze_opposite_side_buy(
            current_price_btc=current_price,
            market_target=market_target,
            market_direction=market_direction,
            opposite_side="DOWN",
            volatility_pct=vol_pct_decimal,  # Теперь в десятичной форме
            time_remaining_minutes=time_remaining_minutes,
            current_price_up=current_price_up,
            current_price_down=current_price_down,
            atr=atr,
            vol_period_minutes=vol_period_minutes,
        )

        # Расчет Std Dev для UI
        import math
        std_dev_calculation = {
            "volatility_pct": vol_pct,  # Уже в процентах
            "time_remaining_minutes": time_remaining_minutes,
            "vol_period_minutes": vol_period_minutes,
            "vol_timeframe": vol_timeframe,
            "sqrt_term": time_remaining_minutes / vol_period_minutes,
            "std_dev_pct": vol_pct * math.sqrt(time_remaining_minutes / vol_period_minutes) if vol_pct and vol_period_minutes > 0 else 0,
            "formula": "std_dev_pct = volatility_pct × √(time_remaining_minutes / vol_period_minutes)"
        }

        # Формула для отображения на UI
        formula_info = {
            "volatility_used": vol_pct,
            "vol_timeframe": vol_timeframe,
            "time_remaining_minutes": time_remaining_minutes,
            "current_price_up": current_price_up,
            "current_price_down": current_price_down,
            "formula": "P = 1 - Φ(z) где z = price_move_pct / std_dev_pct",
            "explanation": "Вероятность рассчитывается по нормальному распределению",
            "std_dev_calculation": std_dev_calculation
        }

        return {
            "up": {
                "math_prob": prob_up.math_probability,
                "market_prob": prob_up.market_probability,
                "edge": prob_up.edge,
                "reach_probability": prob_up.reach_probability,
                "kf": prob_up.kf,
                "z_score": prob_up.z_score,
                "std_dev_pct": prob_up.std_dev_pct,
                "expected_move_pct": prob_up.expected_move_pct,
                "reason": prob_up.reason,
                "formula": formula_info,
                "price_move_pct": prob_up.price_move_pct,
            },
            "down": {
                "math_prob": prob_down.math_probability,
                "market_prob": prob_down.market_probability,
                "edge": prob_down.edge,
                "reach_probability": prob_down.reach_probability,
                "kf": prob_down.kf,
                "z_score": prob_down.z_score,
                "std_dev_pct": prob_down.std_dev_pct,
                "expected_move_pct": prob_down.expected_move_pct,
                "reason": prob_down.reason,
                "formula": formula_info,
                "price_move_pct": prob_down.price_move_pct,
            },
        }
    
    # Удален метод _get_price_to_beat - теперь используется PriceToBeatService

    def _get_market_start_time(self, time_metrics: Dict) -> Optional[datetime]:
        """
        Получить время открытия рынка из time_metrics.

        Сначала пробуем start_time из названия вопроса (точное время),
        затем createdAt из API (приблизительное время).

        Args:
            time_metrics: Словарь с временными метриками

        Returns:
            Время открытия или None
        """
        logger.debug("Получение start_time из time_metrics: %s", time_metrics)
        try:
            # ПРИОРИТЕТ 1: start_time из названия вопроса (точное время открытия)
            start_time = time_metrics.get("start_time")
            if start_time:
                logger.debug("Время открытия рынка из названия: %s", start_time.isoformat())
                return start_time

            # ПРИОРИТЕТ 2: createdAt из API (приблизительное время создания)
            # Используем только если start_time не найден
            logger.warning("start_time не найден в time_metrics: %s", time_metrics)
            return None

        except Exception as exc:
            logger.error("Ошибка при получении времени открытия рынка: %s", exc)
            return None

    def _calculate_deviation(self, current_price: float, price_to_beat: float) -> Dict:
        """
        Рассчитать deviation (отклонение) от Price_to_beat.

        Args:
            current_price: Текущая цена актива
            price_to_beat: Цена на момент начала рынка

        Returns:
            {
                "deviation_pct": float,  # Отклонение в процентах
                "deviation_abs": float,  # Абсолютное отклонение
                "position": str,         # "UP", "DOWN", или "AT_START"
                "description": str      # Описание позиции
            }
        """
        if price_to_beat <= 0:
            return {
                "deviation_pct": 0.0,
                "deviation_abs": 0.0,
                "position": "UNKNOWN",
                "description": "Невозможно рассчитать deviation"
            }

        deviation_abs = current_price - price_to_beat
        deviation_pct = (deviation_abs / price_to_beat) * 100

        if abs(deviation_pct) < 0.01:  # Менее 0.01%
            position = "AT_START"
            description = "Рынок у начальной цены"
        elif deviation_pct > 0:
            position = "UP"
            description = f"Рынок выше начальной цены на {deviation_pct:+.2f}%"
        else:
            position = "DOWN"
            description = f"Рынок ниже начальной цены на {deviation_pct:+.2f}%"

        return {
            "deviation_pct": deviation_pct,
            "deviation_abs": deviation_abs,
            "position": position,
            "description": description
        }

    def _generate_recommendation(
        self,
        probabilities: Dict,
        indicators: Dict,
        time_metrics: Dict,
        orderbook_prices: Dict,
    ) -> Dict:
        """
        Сгенерировать рекомендацию на основе анализа.

        Returns:
            {
                "action": "BUY_UP" | "BUY_DOWN" | "HOLD" | "EXIT",
                "confidence": float (0-1),
                "reason": str
            }
        """
        # Простая логика рекомендации на основе edge
        up_edge = probabilities["up"]["edge"]
        down_edge = probabilities["down"]["edge"]

        # Минимальный edge для входа (5%)
        min_edge = 0.05

        if up_edge > min_edge and up_edge > down_edge:
            action = "BUY_UP"
            confidence = min(up_edge * 2, 1.0)  # edge 10% = confidence 20%
            reason = f"Положительный edge для UP: {up_edge*100:.1f}%"
        elif down_edge > min_edge and down_edge > up_edge:
            action = "BUY_DOWN"
            confidence = min(down_edge * 2, 1.0)
            reason = f"Положительный edge для DOWN: {down_edge*100:.1f}%"
        else:
            action = "HOLD"
            confidence = 0.5
            reason = "Недостаточный edge для входа"

        return {
            "action": action,
            "confidence": confidence,
            "reason": reason,
        }

    def _calculate_absorption_probabilities(
        self,
        current_price: float,
        market_target: float,
        volatility: Dict,
        time_remaining_minutes: float,
        atr: Optional[float],
    ) -> Dict:
        """
        Рассчитать absorption probabilities (вероятность остаться выше/ниже таргета до экспирации).

        Returns:
            {
                "up": {"absorption_prob": float},
                "down": {"absorption_prob": float}
            }
        """
        # Определяем продолжительность рынка
        # Выбираем волатильность в зависимости от продолжительности рынка
        vol_pct = volatility.get("15m") or volatility.get("1h") or volatility.get("5m") or 1.0
        vol_period_minutes = 60.0  # 60 минут для absorption (отличный от touch prob)

        # Конвертируем волатильность из ПРОЦЕНТОВ в ДЕСЯТИЧНУЮ ФОРМУ для calculate_hybrid_volatility
        vol_pct_decimal = vol_pct / 100.0

        # Гибридная волатильность
        vol_for_kf, _, _ = self.probability_analyzer.calculate_hybrid_volatility(
            vol_pct_decimal, atr, current_price
        )

        # Конвертируем обратно в проценты для calculate_absorption_probability
        vol_pct_for_calc = vol_for_kf * 100.0  # Метод ожидает проценты

        # Absorption probability для UP: P(S_T >= market_target)
        absorption_up = self.probability_analyzer.calculate_absorption_probability(
            current_price=current_price,
            barrier_price=market_target,
            volatility_pct=vol_pct_for_calc,
            time_remaining_minutes=time_remaining_minutes,
            vol_period_minutes=vol_period_minutes,
            absorption_type="up"
        )

        # Absorption probability для DOWN: P(S_T <= market_target)
        absorption_down = self.probability_analyzer.calculate_absorption_probability(
            current_price=current_price,
            barrier_price=market_target,
            volatility_pct=vol_pct_for_calc,
            time_remaining_minutes=time_remaining_minutes,
            vol_period_minutes=vol_period_minutes,
            absorption_type="down"
        )

        return {
            "up": {
                "absorption_prob": absorption_up,
            },
            "down": {
                "absorption_prob": absorption_down,
            },
        }

    async def _close_market_positions_if_needed(self, market_id: str, symbol: str, market_data: Dict) -> None:
        """
        Проверить и закрыть позиции по рынку, если рынок завершен.

        Args:
            market_id: ID рынка
            symbol: Символ актива
            market_data: Данные о рынке из API
        """
        try:
            from trading.position import position_storage, determine_market_outcome

            # Проверяем есть ли открытые позиции по этому рынку
            open_positions = [pos for pos in position_storage.get_open_positions()
                            if pos.market_id == market_id]

            if not open_positions:
                logger.debug(f"Нет открытых позиций для закрытия в рынке {market_id}")
                return

            logger.info(f"🎯 Обнаружено {len(open_positions)} открытых позиций в завершенном рынке {market_id}")

            # Получаем price_to_beat из кэша или market_data
            price_to_beat = self.price_to_beat_cache.get(market_id)
            if not price_to_beat:
                # Пробуем получить из market_data или используем текущую цену
                price_to_beat = self.price_monitor.get_price(symbol) or 1.0
                logger.warning(f"Price_to_beat не найден для {market_id}, используем текущую цену ${price_to_beat}")

            # Получаем время окончания рынка
            end_time = None
            if "endDate" in market_data:
                try:
                    end_time = datetime.fromisoformat(market_data["endDate"].replace('Z', '+00:00'))
                except:
                    pass

            if not end_time:
                logger.error(f"Не удалось получить время окончания для рынка {market_id}")
                return

            # Получаем цену на конец рынка из коллектора
            end_timestamp = int(end_time.timestamp())
            end_price = self.price_monitor.chainlink_collector.get_price_at_time(symbol, end_timestamp)

            if not end_price or end_price <= 0:
                logger.warning(f"Не удалось получить цену на конец рынка {market_id}, используем текущую цену")
                end_price = self.price_monitor.get_price(symbol) or price_to_beat

            logger.info(f"📊 Рынок {market_id}: price_to_beat=${price_to_beat:.2f}, end_price=${end_price:.2f}")

            # Определяем исход рынка
            outcome = determine_market_outcome(price_to_beat, end_price)
            logger.info(f"🏆 Исход рынка {market_id}: {outcome} (end_price ${end_price:.2f} {'<' if end_price < price_to_beat else '>='} price_to_beat ${price_to_beat:.2f})")

            # Закрываем все позиции по рынку
            closed_positions = position_storage.close_market_positions(market_id, outcome, end_price)

            if closed_positions:
                logger.info(f"✅ Закрыто {len(closed_positions)} позиций в рынке {market_id}")
            else:
                logger.warning(f"Не удалось закрыть позиции в рынке {market_id}")

        except Exception as exc:
            logger.error(f"Ошибка при закрытии позиций рынка {market_id}: {exc}")
