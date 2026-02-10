"""
Orderbook Analyzer - работа с orderbook Polymarket.
Получение и парсинг orderbook, извлечение лучших bid/ask цен.
Кэширование orderbook данных для снижения нагрузки на API.
"""

import asyncio
import logging
import time
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class OrderbookAnalyzer:
    """
    Анализатор orderbook для Polymarket.
    Получает orderbook и извлекает лучшие bid/ask цены для UP и DOWN.
    Кэширует данные для снижения количества API запросов.
    """

    # Интервал обновления кэша (1 секунда)
    CACHE_UPDATE_INTERVAL = 1.0

    def __init__(self, polymarket_client):
        """
        Args:
            polymarket_client: Экземпляр PolymarketClient из polymarket.client
        """
        self.polymarket_client = polymarket_client

        # Кэш orderbook данных: market_id -> {"data": dict, "timestamp": float, "parsed": dict}
        self.orderbook_cache: Dict[str, Dict] = {}

        # Список активных рынков для обновления
        self.active_markets: set = set()

        # Отслеживание времени последней активности: market_id -> timestamp
        self.last_activity: Dict[str, float] = {}

        # Максимальное время бездействия для рынков без позиций (5 минут)
        self.MAX_INACTIVE_TIME_NO_POSITIONS = 300  # 5 минут

        # Флаг работы обновления кэша
        self.cache_updater_running = False
        self.cache_updater_task: Optional[asyncio.Task] = None
    
    def get_orderbook(self, market_id: str) -> Optional[dict]:
        """
        Получить raw orderbook для market_id.
        
        Args:
            market_id: ID рынка на Polymarket
            
        Returns:
            Orderbook dict или None если не удалось получить
        """
        try:
            return self.polymarket_client.get_orderbook(market_id)
        except Exception as exc:
            logger.error("Ошибка при получении orderbook для market %s: %s", market_id, exc)
            return None
    
    def get_best_bid_ask(self, orderbook: dict) -> Optional[Dict]:
        """
        Извлечь лучшие bid/ask цены для UP и DOWN из orderbook.

        Новый формат: Polymarket возвращает orderbook для каждого outcome отдельно.
        Формат данных:
        {
            "token_ids": ["id1", "id2"],
            "orderbooks": {
                "outcome_0": {...},  # orderbook для первого outcome (UP)
                "outcome_1": {...},  # orderbook для второго outcome (DOWN)
            }
        }

        Args:
            orderbook: Dict с orderbooks для всех outcomes

        Returns:
            {
                "up_bid": float,
                "up_ask": float,
                "down_bid": float,
                "down_ask": float,
                "up_spread": float,
                "down_spread": float,
                "up_bid_size": float,
                "up_ask_size": float,
                "down_bid_size": float,
                "down_ask_size": float
            }
            или None если не удалось извлечь
        """
        if not orderbook:
            return None

        try:
            # Новый формат: orderbook содержит token_ids и orderbooks для каждого outcome
            token_ids = orderbook.get("token_ids", [])
            orderbooks = orderbook.get("orderbooks", {})

            if not orderbooks:
                logger.warning("Orderbook не содержит orderbooks")
                return None

            # Извлекаем данные для каждого outcome
            up_data = None
            down_data = None

            # outcome_0 обычно UP, outcome_1 обычно DOWN
            if "outcome_0" in orderbooks:
                up_data = self._extract_best_prices(orderbooks["outcome_0"])
            if "outcome_1" in orderbooks:
                down_data = self._extract_best_prices(orderbooks["outcome_1"])

            # Если данных недостаточно, возвращаем None
            if not up_data and not down_data:
                logger.debug("Не удалось извлечь данные ни для одного outcome (orderbook может быть пустым или рынок неактивен)")
                return None

            # Формируем результат
            result = {
                "up_bid": up_data.get("bid") if up_data else None,
                "up_ask": up_data.get("ask") if up_data else None,
                "down_bid": down_data.get("bid") if down_data else None,
                "down_ask": down_data.get("ask") if down_data else None,
                "up_spread": up_data.get("spread") if up_data else None,
                "down_spread": down_data.get("spread") if down_data else None,
                "up_bid_size": up_data.get("bid_size") if up_data else None,
                "up_ask_size": up_data.get("ask_size") if up_data else None,
                "down_bid_size": down_data.get("bid_size") if down_data else None,
                "down_ask_size": down_data.get("ask_size") if down_data else None,
            }

            logger.debug("Orderbook analysis complete: UP=%s, DOWN=%s",
                        "✓" if up_data else "✗", "✓" if down_data else "✗")

            return result

        except Exception as exc:
            logger.error("Ошибка при парсинге orderbook: %s", exc)
            return None

    def _extract_best_prices(self, single_orderbook: dict) -> Optional[Dict]:
        """
        Извлечь лучшие цены из orderbook для одного outcome.

        Args:
            single_orderbook: Orderbook dict для одного outcome

        Returns:
            {
                "bid": float,
                "ask": float,
                "spread": float,
                "bid_size": float,
                "ask_size": float
            } или None
        """
        try:
            bids = single_orderbook.get("bids", [])
            asks = single_orderbook.get("asks", [])

            if not bids or not asks:
                return None

            # Извлекаем цены
            bid_prices = [float(order.get("price", 0)) for order in bids if isinstance(order, dict)]
            ask_prices = [float(order.get("price", 0)) for order in asks if isinstance(order, dict)]

            if not bid_prices or not ask_prices:
                return None

            # Лучшие цены
            best_bid = max(bid_prices)
            best_ask = min(ask_prices)

            # Размеры лучших ордеров
            best_bid_order = next((order for order in bids if float(order.get("price", 0)) == best_bid), {})
            best_ask_order = next((order for order in asks if float(order.get("price", 0)) == best_ask), {})

            best_bid_size = float(best_bid_order.get("size", 0))
            best_ask_size = float(best_ask_order.get("size", 0))

            # Spread
            spread = best_ask - best_bid

            return {
                "bid": best_bid,
                "ask": best_ask,
                "spread": spread,
                "bid_size": best_bid_size,
                "ask_size": best_ask_size,
            }

        except Exception as exc:
            logger.debug("Ошибка при извлечении цен из orderbook: %s", exc)
            return None
    
    def _get_best_price(self, orders: list, side: str) -> Optional[float]:
        """
        Получить лучшую цену из списка ордеров.
        Для bid - максимальная цена (самая выгодная для продажи)
        Для ask - минимальная цена (самая выгодная для покупки)

        Args:
            orders: Список ордеров [{"price": float, "size": float}, ...]
            side: "bid" или "ask"

        Returns:
            Лучшая цена или None
        """
        if not orders:
            return None

        try:
            prices = []

            # Собираем все цены из ордеров
            for order in orders:
                if isinstance(order, dict):
                    price = order.get("price")
                    if price is not None:
                        prices.append(float(price))
                elif isinstance(order, (list, tuple)) and len(order) >= 1:
                    prices.append(float(order[0]))

            if not prices:
                return None

            # Возвращаем лучшую цену
            if side == "bid":
                # Для bid - максимальная цена (самая выгодная для продажи)
                return max(prices)
            elif side == "ask":
                # Для ask - минимальная цена (самая выгодная для покупки)
                return min(prices)
            else:
                # По умолчанию возвращаем первую цену
                return prices[0]

        except Exception as exc:
            logger.debug("Ошибка при извлечении цены: %s", exc)
            return None
    
    def _get_best_size(self, orders: list, side: str) -> Optional[float]:
        """
        Получить размер лучшего ордера.
        
        Args:
            orders: Список ордеров
            side: "bid" или "ask"
            
        Returns:
            Размер или None
        """
        if not orders:
            return None
        
        try:
            for order in orders:
                if isinstance(order, dict):
                    size = order.get("size")
                    if size is not None:
                        return float(size)
                elif isinstance(order, (list, tuple)) and len(order) >= 2:
                    return float(order[1])
            
            return None
        except Exception as exc:
            logger.debug("Ошибка при извлечении размера: %s", exc)
            return None
    
    def start_cache_updater(self) -> None:
        """Запустить фоновый обновлятор кэша orderbook."""
        if self.cache_updater_running:
            return

        self.cache_updater_running = True
        self.cache_updater_task = asyncio.create_task(self._cache_update_loop())
        logger.info("Запущен кэш orderbook (обновление каждые %.1f сек)", self.CACHE_UPDATE_INTERVAL)

    def stop_cache_updater(self) -> None:
        """Остановить фоновый обновлятор кэша."""
        self.cache_updater_running = False
        if self.cache_updater_task:
            self.cache_updater_task.cancel()
            try:
                asyncio.wait_for(self.cache_updater_task, timeout=5.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass
        logger.info("Остановлен кэш orderbook")

    def add_active_market(self, market_id: str) -> None:
        """Добавить рынок в список активных для кэширования."""
        self.active_markets.add(market_id)
        logger.debug("Добавлен активный рынок для кэша: %s", market_id)

    def remove_active_market(self, market_id: str) -> None:
        """Удалить рынок из списка активных."""
        self.active_markets.discard(market_id)
        # Очищаем кэш для этого рынка
        if market_id in self.orderbook_cache:
            del self.orderbook_cache[market_id]
        # Удаляем из отслеживания активности
        if market_id in self.last_activity:
            del self.last_activity[market_id]
        logger.debug("Удален активный рынок из кэша: %s", market_id)

    def remove_inactive_market(self, market_id: str) -> None:
        """Удалить неактивный рынок из списка активных."""
        if market_id in self.active_markets:
            self.active_markets.discard(market_id)
            # Очищаем кэш для этого рынка
            if market_id in self.orderbook_cache:
                del self.orderbook_cache[market_id]
            # Удаляем из отслеживания активности
            if market_id in self.last_activity:
                del self.last_activity[market_id]
            logger.info("Удален неактивный рынок из кэша: %s", market_id)

    async def _cache_update_loop(self) -> None:
        """Фоновый цикл обновления кэша orderbook."""
        while self.cache_updater_running:
            try:
                current_time = time.time()

                # Очищаем неактивные рынки и рынки без позиций
                markets_to_remove = []
                for market_id in list(self.active_markets):
                    # Проверяем, есть ли позиции для этого рынка
                    has_positions = self._market_has_positions(market_id)

                    if not has_positions:
                        # Для рынков без позиций проверяем время последней активности
                        last_active = self.last_activity.get(market_id, current_time)
                        inactive_time = current_time - last_active

                        if inactive_time > self.MAX_INACTIVE_TIME_NO_POSITIONS:
                            markets_to_remove.append(market_id)
                            logger.info("Удален рынок без позиций (неактивен %.1f мин): %s",
                                       inactive_time / 60, market_id)

                # Удаляем неактивные рынки
                for market_id in markets_to_remove:
                    self.remove_active_market(market_id)

                # Обновляем кэш для оставшихся активных рынков
                tasks = []
                for market_id in list(self.active_markets):
                    tasks.append(self._update_market_cache(market_id))

                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)

                # Ждем до следующего обновления
                await asyncio.sleep(self.CACHE_UPDATE_INTERVAL)

            except Exception as exc:
                logger.error("Ошибка в цикле обновления кэша orderbook: %s", exc)
                await asyncio.sleep(1.0)  # Небольшая пауза при ошибке

    async def _update_market_cache(self, market_id: str) -> None:
        """Обновить кэш для конкретного рынка."""
        try:
            # Получаем свежие данные
            orderbook_data = self.polymarket_client.get_orderbook(market_id)
            if orderbook_data:
                # Парсим данные
                parsed_data = self.get_best_bid_ask(orderbook_data)

                # Сохраняем в кэш
                self.orderbook_cache[market_id] = {
                    "data": orderbook_data,
                    "parsed": parsed_data,
                    "timestamp": time.time()
                }

                # Обновляем время последней активности
                self.last_activity[market_id] = time.time()

                logger.debug("Обновлен кэш orderbook для рынка %s", market_id)
            else:
                # Не удалось получить orderbook - возможно рынок неактивен
                # Удаляем его из активных рынков, чтобы не пытаться больше
                logger.info("Не удалось получить orderbook для рынка %s - удаляем из активных", market_id)
                self.remove_active_market(market_id)

        except Exception as exc:
            logger.debug("Ошибка обновления кэша для рынка %s: %s", market_id, exc)
            # При ошибке тоже удаляем из активных, чтобы не зациклиться
            logger.info("Ошибка при обновлении кэша для рынка %s - удаляем из активных", market_id)
            self.remove_active_market(market_id)

    def _market_has_positions(self, market_id: str) -> bool:
        """
        Проверить, есть ли открытые позиции для данного рынка.

        Args:
            market_id: ID рынка

        Returns:
            True если есть позиции, False иначе
        """
        try:
            # Импортируем position_storage
            from trading.position import position_storage

            # Получаем открытые позиции
            open_positions = position_storage.get_open_positions()

            # Проверяем, есть ли позиции для этого рынка
            for position in open_positions:
                if position.market_id == market_id:
                    return True

            return False

        except Exception as exc:
            logger.debug("Ошибка при проверке позиций для рынка %s: %s", market_id, exc)
            # В случае ошибки считаем, что позиций нет (безопаснее)
            return False

    def get_cached_orderbook(self, market_id: str) -> Optional[dict]:
        """
        Получить orderbook из кэша.

        Args:
            market_id: ID рынка

        Returns:
            Кэшированные данные orderbook или None
        """
        cache_entry = self.orderbook_cache.get(market_id)
        if cache_entry:
            age = time.time() - cache_entry["timestamp"]
            if age < self.CACHE_UPDATE_INTERVAL * 2:  # Данные не старше 2 секунд
                return cache_entry["data"]
            else:
                logger.debug("Кэш orderbook устарел для рынка %s (возраст: %.1f сек)", market_id, age)

        return None

    def get_cached_prices(self, market_id: str) -> Optional[Dict]:
        """
        Получить распарсенные цены из кэша.

        Args:
            market_id: ID рынка

        Returns:
            Кэшированные распарсенные цены или None
        """
        cache_entry = self.orderbook_cache.get(market_id)
        if cache_entry:
            age = time.time() - cache_entry["timestamp"]
            if age < self.CACHE_UPDATE_INTERVAL * 2:  # Данные не старше 2 секунд
                return cache_entry["parsed"]
            else:
                logger.debug("Кэш цен устарел для рынка %s (возраст: %.1f сек)", market_id, age)

        return None

    def get_market_prices(self, market_id: str) -> Optional[Dict]:
        """
        Получить лучшие цены для рынка (использует кэш если доступен).

        Args:
            market_id: ID рынка

        Returns:
            Dict с best bid/ask ценами или None
        """
        # Сначала пробуем получить из кэша
        cached_prices = self.get_cached_prices(market_id)
        if cached_prices:
            logger.debug("Возвращены кэшированные цены для рынка %s", market_id)
            return cached_prices

        # Если нет в кэше, делаем прямой запрос (fallback)
        logger.debug("Цены не найдены в кэше, делаем прямой запрос для рынка %s", market_id)
        orderbook = self.get_orderbook(market_id)
        if not orderbook:
            return None

        return self.get_best_bid_ask(orderbook)
