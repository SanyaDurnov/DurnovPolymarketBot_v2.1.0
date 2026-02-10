"""
Price To Beat Service - единый сервис для получения цены открытия рынка.

Обеспечивает получение price_to_beat для всех компонентов системы.
Использует кэширование, получение из коллектора и fallback логику.
"""

import logging
from datetime import datetime, timezone
from typing import Optional, Dict

logger = logging.getLogger(__name__)


class PriceToBeatService:
    """
    Сервис для получения цены открытия рынка (price_to_beat).

    Отвечает за:
    - Кэширование price_to_beat для производительности
    - Получение данных из коллектора
    - Fallback на текущую цену при отсутствии данных
    - Определение символа, времени открытия и продолжительности рынка
    """

    def __init__(self, price_monitor, polymarket_client):
        """
        Args:
            price_monitor: PriceMonitor для получения цен
            polymarket_client: PolymarketClient для получения данных рынка
        """
        self.price_monitor = price_monitor
        self.pm_client = polymarket_client
        # Расширенный кэш: market_id -> {price_to_beat, symbol, market_duration, title}
        self.cache: Dict[str, Dict] = {}

    def get_market_info(self, market_id: str) -> Optional[Dict]:
        """
        Получить всю информацию о рынке: start_time, end_time, symbol (БЕЗ price_to_beat).
        Сначала проверяет кэш, потом вычисляет.

        Args:
            market_id: ID рынка

        Returns:
            Словарь с информацией о рынке или None
        """
        # Проверяем кэш
        if market_id in self.cache:
            cached_data = self.cache[market_id]
            logger.debug(f"✅ Найдено в кэше: {market_id}")
            return cached_data

        # Вычисляем времена и symbol (БЕЗ price_to_beat для скорости)
        market_info = self._get_market_times_and_symbol(market_id)
        if market_info is not None:
            self.cache[market_id] = market_info
            logger.debug(f"💾 Кэшировано (без price_to_beat): {market_id}")

        return market_info

    async def get_price_to_beat(self, market_id: str) -> Optional[float]:
        """
        Получить price_to_beat для рынка.

        Args:
            market_id: ID рынка

        Returns:
            Price_to_beat (цена открытия) или None при ошибке
        """
        try:
            # Проверяем кэш сначала
            if market_id in self.cache:
                cached_data = self.cache[market_id]
                cached_price = cached_data.get("price_to_beat")
                logger.info(f"💾 Price_to_beat для рынка {market_id} из кэша: ${cached_price}")
                logger.info(f"   📊 Кэш содержит: symbol={cached_data.get('symbol')}, duration={cached_data.get('market_duration')}, title='{cached_data.get('title', '')[:50]}...'")
                return cached_price

            logger.info(f"🔍 Запрос Price_to_beat для рынка {market_id} (кэш пуст)")

            # Определяем cached_data для случаев, когда market_id нет в кэше
            cached_data = self.cache.get(market_id) if market_id in self.cache else None

            # Получаем данные о рынке из Market Service cache (приоритет)
            from polymarket.market_cache_reader import get_cached_market_by_id, add_market_to_cache
            market_data = get_cached_market_by_id(market_id)

            # Fallback на API если рынка нет в кэше (manual entry, новые рынки)
            if not market_data:
                logger.warning(f"⚠️  Рынок {market_id} не найден в кэше Market Service, запрашиваем из API")
                market_data = self.pm_client.get_market_data(market_id)
                if not market_data:
                    logger.debug(f"Не удалось получить данные рынка {market_id} даже из API")
                    return None
                logger.info(f"✅ Получены данные рынка {market_id} из API (fallback)")

                # Добавляем в кэш для следующих запросов
                add_market_to_cache(market_data)
                logger.info(f"💾 Рынок {market_id} добавлен в кэш после API fallback")

            # Извлекаем title и определяем символ и продолжительность
            title = market_data.get("question") or market_data.get("title") or ""
            symbol = self._infer_symbol_from_title(title)
            market_duration = self._determine_market_duration(title)
            
            if not symbol:
                logger.debug(f"Не удалось определить символ из названия: {title}")
                return None

            # Получаем время открытия рынка
            start_time = self._get_market_start_time_from_data(market_data)
            if not start_time:
                logger.debug(f"Не удалось определить время открытия рынка {market_id}")
                return None

            # Получаем время окончания рынка (для кэша) - ТОЛЬКО если его нет
            end_time = None
            if not cached_data or not cached_data.get("end_time"):
                end_date_str = market_data.get("endDate")
                if end_date_str:
                    try:
                        end_time = datetime.fromisoformat(end_date_str.replace('Z', '+00:00'))
                        logger.debug(f"✅ end_time получен из endDate: {end_time}")
                    except Exception as e:
                        logger.debug(f"Ошибка парсинга endDate '{end_date_str}': {e}")
                else:
                    logger.debug("❌ endDate не найден в market_data")
            else:
                logger.debug("✅ end_time уже есть в кэше, не обновляем")

            # Проверяем, не в будущем ли время открытия
            now = datetime.now(timezone.utc)
            if start_time > now:
                logger.debug(f"Рынок {market_id} еще не начался (открытие: {start_time})")
                return None

            # Получаем цену из коллектора
            ts = int(start_time.timestamp())
            logger.debug(f"Запрашиваем цену из коллектора для {symbol} на timestamp {ts}")
            price_to_beat = self.price_monitor.chainlink_collector.get_price_at_time(symbol, ts)

            if price_to_beat and price_to_beat > 0:
                if price_to_beat < 1:
                    logger.error(f"🚨🚨🚨 CRITICAL: Коллектор вернул цену < $1 для {market_id}!")
                    logger.error(f"   symbol={symbol}, timestamp={ts}, price_to_beat={price_to_beat}")
                    return None

                logger.info(f"✅ Price_to_beat для рынка {market_id}: ${price_to_beat}")
                logger.info(f"   📦 Сохраняем в кэш: symbol={symbol}, duration={market_duration}, end_time={end_time}")

                # Сохраняем все данные в расширенный кэш
                self.cache[market_id] = {
                    "price_to_beat": price_to_beat,
                    "symbol": symbol,
                    "market_duration": market_duration,
                    "title": title,
                    "start_time": start_time.isoformat() if start_time else None,
                    "end_time": end_time.isoformat() if end_time else None
                }
                return price_to_beat
            else:
                # Fallback: используем текущую цену
                current_price = self.price_monitor.get_price(symbol)
                if current_price:
                    logger.warning(f"🔴 CRITICAL: Коллектор не имеет данных для {market_id}! Используем текущую цену ${current_price} как price_to_beat")
                    logger.warning(f"   symbol={symbol}, timestamp={ts}, start_time={start_time}")
                    
                    logger.warning(f"   📦 Сохраняем fallback в кэш: symbol={symbol}, duration={market_duration}, title='{title[:50]}...'")
                    
                    # Сохраняем fallback данные в расширенный кэш
                    self.cache[market_id] = {
                        "price_to_beat": current_price,
                        "symbol": symbol,
                        "market_duration": market_duration,
                        "title": title,
                        "start_time": start_time.isoformat() if start_time else None
                    }
                    return current_price
                else:
                    logger.error(f"Не удалось получить даже текущую цену для {symbol}")
                    return None

        except Exception as exc:
            logger.error(f"Ошибка при получении price_to_beat для {market_id}: {exc}")
            return None

    def get_market_start_time(self, market_id: str) -> Optional[int]:
        """
        Получить время начала рынка по market_id.
        Использует кэш через get_market_info.
        
        Args:
            market_id: ID рынка
            
        Returns:
            Время начала рынка в timestamp или None
        """
        market_info = self.get_market_info(market_id)
        if market_info:
            return market_info.get('start_time')
        return None

    def get_market_end_time(self, market_id: str) -> Optional[int]:
        """
        Получить время окончания рынка по market_id.
        Использует кэш через get_market_info.
        
        Args:
            market_id: ID рынка
            
        Returns:
            Время окончания рынка в timestamp или None
        """
        market_info = self.get_market_info(market_id)
        if market_info:
            return market_info.get('end_time')
        return None

    def get_end_price(self, market_id: str) -> Optional[float]:
        """
        Получить end_price для рынка по времени закрытия.
        Использует кэш через get_market_info.
        
        Args:
            market_id: ID рынка
            
        Returns:
            End_price (цена закрытия) или None
        """
        try:
            # Получаем информацию о рынке
            market_info = self.get_market_info(market_id)
            if not market_info:
                logger.warning(f"❌ Не удалось получить информацию о рынке {market_id}")
                return None

            end_time = market_info.get('end_time')
            symbol = market_info.get('symbol')
            
            if not end_time or not symbol:
                logger.warning(f"❌ Не удалось получить end_time или symbol для {market_id}")
                return None

            # Преобразуем end_time в timestamp если это datetime объект
            try:
                if isinstance(end_time, str):
                    # Если это строка в ISO формате, конвертируем в timestamp
                    end_time_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
                    end_time_ts = int(end_time_dt.timestamp())
                elif isinstance(end_time, (int, float)):
                    end_time_ts = int(end_time)
                else:
                    logger.error(f"Некорректный формат end_time для {market_id}: {type(end_time)}")
                    return None
            except Exception as e:
                logger.error(f"Ошибка преобразования end_time в timestamp для {market_id}: {e}")
                return None

            # Получаем end_price из коллектора по времени закрытия
            logger.debug(f"Запрашиваем end_price из коллектора для {symbol} на timestamp {end_time_ts}")
            end_price = self.price_monitor.chainlink_collector.get_price_at_time(symbol, end_time_ts)

            if end_price and end_price > 0:
                logger.info(f"✅ End_price для рынка {market_id}: ${end_price}")
                return end_price
            else:
                # Fallback: используем текущую цену
                current_price = self.price_monitor.get_price(symbol)
                if current_price:
                    logger.warning(f"🔴 CRITICAL: Коллектор не имеет данных для end_price {market_id}! Используем текущую цену ${current_price}")
                    return current_price
                else:
                    logger.error(f"Не удалось получить даже текущую цену для {symbol}")
                    return None

        except Exception as exc:
            logger.error(f"Ошибка при получении end_price для {market_id}: {exc}")
            return None

    def clear_market_cache(self, market_id: str) -> None:
        """Очистить кэш для конкретного рынка."""
        if market_id in self.cache:
            del self.cache[market_id]
            logger.info(f"🧹 Кэш очищен для рынка {market_id}")

    def _get_market_title(self, market_id: str) -> Optional[str]:
        """
        Получить market_title для рынка.
        
        Args:
            market_id: ID рынка
            
        Returns:
            Название рынка или None
        """
        try:
            market_data = self.pm_client.get_market_data(market_id)
            if market_data:
                return market_data.get("question") or market_data.get("title") or ""
            return None
        except Exception as e:
            logger.error(f"Ошибка получения market_title для {market_id}: {e}")
            return None

    def _get_symbol_from_market_id(self, market_id: str) -> Optional[str]:
        """
        Получить символ рынка по market_id.
        
        Args:
            market_id: ID рынка
            
        Returns:
            Символ (BTCUSDT, ETHUSDT, SOLUSDT) или None
        """
        try:
            market_title = self._get_market_title(market_id)
            if market_title:
                return self._infer_symbol_from_title(market_title)
            return None
        except Exception as e:
            logger.error(f"Ошибка получения символа для {market_id}: {e}")
            return None

    async def get_market_duration(self, market_id: str) -> Optional[str]:
        """
        Получить продолжительность рынка по market_id.
        Сначала проверяет кэш, потом вычисляет.
        
        Args:
            market_id: ID рынка
            
        Returns:
            "15m" или "1h" или None
        """
        # Проверяем кэш
        if market_id in self.cache:
            cached_data = self.cache[market_id]
            duration = cached_data.get("market_duration")
            if duration:
                logger.debug(f"💾 Market duration для рынка {market_id} из кэша: {duration}")
                return duration

        # Если нет в кэше - вычисляем и кэшируем
        market_info = await self._calculate_market_info(market_id)
        if market_info is not None:
            self.cache[market_id] = market_info
            duration = market_info.get("market_duration")
            logger.debug(f"🆕 Market duration для рынка {market_id} получен: {duration}")
            return duration
        
        return None

    def _get_market_duration(self, market_id: str) -> Optional[str]:
        """
        Получить продолжительность рынка по market_id.
        
        Args:
            market_id: ID рынка
            
        Returns:
            "15m" или "1h" или None
        """
        try:
            market_title = self._get_market_title(market_id)
            if market_title:
                return self._determine_market_duration(market_title)
            return None
        except Exception as e:
            logger.error(f"Ошибка получения продолжительности для {market_id}: {e}")
            return None

    async def _calculate_price_to_beat(self, market_id: str) -> Optional[float]:
        """
        Вычислить price_to_beat для рынка.
        
        Args:
            market_id: ID рынка
            
        Returns:
            Price_to_beat или None
        """
        try:
            # Получаем market_title для извлечения временных меток
            market_title = self._get_market_title(market_id)
            if not market_title:
                logger.warning(f"❌ Не удалось получить market_title для {market_id}")
                return None

            # Извлекаем start_time из market_title
            start_time = self._parse_market_start_time(market_title)
            if not start_time:
                logger.warning(f"❌ Не удалось извлечь start_time из {market_title}")
                return None

            # Получаем символ
            symbol = self._get_symbol_from_market_id(market_id)
            if not symbol:
                logger.warning(f"❌ Не удалось определить символ для {market_id}")
                return None

            # Получаем цену из коллектора
            # start_time уже может быть timestamp (int/float) или datetime объектом
            if isinstance(start_time, (int, float)):
                ts = int(start_time)
            else:
                ts = int(start_time.timestamp())
                
            logger.debug(f"Запрашиваем цену из коллектора для {symbol} на timestamp {ts}")
            price_to_beat = self.price_monitor.chainlink_collector.get_price_at_time(symbol, ts)

            if price_to_beat and price_to_beat > 0:
                if price_to_beat < 1:
                    logger.error(f"🚨🚨🚨 CRITICAL: Коллектор вернул цену < $1 для {market_id}!")
                    logger.error(f"   symbol={symbol}, timestamp={ts}, price_to_beat={price_to_beat}")
                    return None

                logger.info(f"✅ Price_to_beat для рынка {market_id}: ${price_to_beat}")
                return price_to_beat
            else:
                # Fallback: используем текущую цену
                current_price = self.price_monitor.get_price(symbol)
                if current_price:
                    logger.warning(f"🔴 CRITICAL: Коллектор не имеет данных для {market_id}! Используем текущую цену ${current_price} как price_to_beat")
                    logger.warning(f"   symbol={symbol}, timestamp={ts}, start_time={start_time}")
                    return current_price
                else:
                    logger.error(f"Не удалось получить даже текущую цену для {symbol}")
                    return None

        except Exception as e:
            logger.error(f"Ошибка вычисления price_to_beat для {market_id}: {e}")
            return None

    async def get_symbol(self, market_id: str) -> Optional[str]:
        """
        Получить символ рынка по market_id.
        Сначала проверяет кэш, потом вычисляет.
        
        Args:
            market_id: ID рынка
            
        Returns:
            Символ (BTCUSDT, ETHUSDT, SOLUSDT) или None
        """
        # Проверяем кэш
        if market_id in self.cache:
            cached_data = self.cache[market_id]
            symbol = cached_data.get("symbol")
            if symbol:
                logger.debug(f"💾 Symbol для рынка {market_id} из кэша: {symbol}")
                return symbol

        # Если нет в кэше - вычисляем и кэшируем
        market_info = await self._calculate_market_info(market_id)
        if market_info is not None:
            self.cache[market_id] = market_info
            symbol = market_info.get("symbol")
            logger.debug(f"🆕 Symbol для рынка {market_id} получен: {symbol}")
            return symbol
        
        return None

    def _get_market_times_and_symbol(self, market_id: str) -> Optional[Dict]:
        """
        Получить времена и symbol для рынка (БЕЗ price_to_beat).
        Синхронный метод для быстрого получения данных.

        Args:
            market_id: ID рынка

        Returns:
            Словарь с временами и symbol или None
        """
        try:
            # Получаем market_data
            market_data = self.pm_client.get_market_data(market_id)
            if not market_data:
                logger.warning(f"❌ Не удалось получить market_data для {market_id}")
                return None

            market_title = market_data.get("question") or market_data.get("title") or ""

            # Получаем временные метки
            start_time = None
            end_time = None

            # Способ 1: Из полей startDate/endDate (приоритет)
            start_date_str = market_data.get("startDate")
            end_date_str = market_data.get("endDate")

            if end_date_str:
                try:
                    end_time_dt = datetime.fromisoformat(end_date_str.replace('Z', '+00:00'))
                    end_time = int(end_time_dt.timestamp())
                    logger.debug(f"✅ end_time получен из endDate: {end_time_dt}")
                except Exception as e:
                    logger.debug(f"Ошибка парсинга endDate '{end_date_str}': {e}")

            if start_date_str:
                try:
                    start_time_dt = datetime.fromisoformat(start_date_str.replace('Z', '+00:00'))
                    start_time = int(start_time_dt.timestamp())
                    logger.debug(f"✅ start_time получен из startDate: {start_time_dt}")
                except Exception as e:
                    logger.debug(f"Ошибка парсинга startDate '{start_date_str}': {e}")

            # Способ 2: Парсим из title (fallback)
            if not start_time and market_title:
                start_time = self._parse_market_start_time(market_title)
                if start_time:
                    logger.debug(f"✅ start_time получен из title")

            if not end_time and market_title:
                end_time = self._parse_market_end_time(market_title)
                if end_time:
                    logger.debug(f"✅ end_time получен из title")

            # Получаем symbol
            symbol = self._infer_symbol_from_title(market_title) if market_title else None

            if not symbol:
                logger.warning(f"❌ Не удалось определить symbol для {market_id}")
                return None

            # Конвертируем временные метки в ISO формат
            start_time_iso = None
            end_time_iso = None

            if isinstance(start_time, (int, float)):
                start_time_iso = datetime.fromtimestamp(start_time, tz=timezone.utc).isoformat()
            elif hasattr(start_time, 'isoformat'):
                start_time_iso = start_time.isoformat()

            if isinstance(end_time, (int, float)):
                end_time_iso = datetime.fromtimestamp(end_time, tz=timezone.utc).isoformat()
            elif hasattr(end_time, 'isoformat'):
                end_time_iso = end_time.isoformat()

            # Определяем market_duration
            market_duration = self._determine_market_duration(market_title) if market_title else "1h"

            return {
                'symbol': symbol,
                'market_duration': market_duration,
                'start_time': start_time_iso,
                'end_time': end_time_iso,
                'title': market_title
            }

        except Exception as e:
            logger.error(f"Ошибка получения times/symbol для {market_id}: {e}")
            return None

    async def _calculate_market_info(self, market_id: str) -> Optional[Dict]:
        """
        Вычислить всю информацию о рынке: price_to_beat, start_time, end_time, symbol.

        Args:
            market_id: ID рынка

        Returns:
            Словарь с информацией о рынке или None
        """
        try:
            # Получаем market_data для извлечения endDate/startDate напрямую
            market_data = self.pm_client.get_market_data(market_id)
            if not market_data:
                logger.warning(f"❌ Не удалось получить market_data для {market_id}")
                return None

            market_title = market_data.get("question") or market_data.get("title") or ""
            if not market_title:
                logger.warning(f"❌ Не удалось получить market_title для {market_id}")
                return None

            # Пытаемся получить временные метки напрямую из market_data (приоритет)
            start_time = None
            end_time = None

            # Способ 1: Из полей startDate/endDate (если есть)
            start_date_str = market_data.get("startDate")
            end_date_str = market_data.get("endDate")

            if end_date_str:
                try:
                    end_time_dt = datetime.fromisoformat(end_date_str.replace('Z', '+00:00'))
                    end_time = int(end_time_dt.timestamp())
                    logger.debug(f"✅ end_time получен из endDate: {end_time_dt}")
                except Exception as e:
                    logger.debug(f"Ошибка парсинга endDate '{end_date_str}': {e}")

            if start_date_str:
                try:
                    start_time_dt = datetime.fromisoformat(start_date_str.replace('Z', '+00:00'))
                    start_time = int(start_time_dt.timestamp())
                    logger.debug(f"✅ start_time получен из startDate: {start_time_dt}")
                except Exception as e:
                    logger.debug(f"Ошибка парсинга startDate '{start_date_str}': {e}")

            # Способ 2: Парсим из title (fallback)
            if not start_time:
                start_time = self._parse_market_start_time(market_title)
                if start_time:
                    logger.debug(f"✅ start_time получен из title: {start_time}")

            if not end_time:
                end_time = self._parse_market_end_time(market_title)
                if end_time:
                    logger.debug(f"✅ end_time получен из title: {end_time}")

            if not start_time or not end_time:
                logger.warning(f"❌ Не удалось извлечь временные метки для {market_id}")
                logger.warning(f"   start_time={start_time}, end_time={end_time}")
                logger.warning(f"   startDate={start_date_str}, endDate={end_date_str}")
                logger.warning(f"   title={market_title[:100]}")
                return None

            # Получаем символ
            symbol = self._get_symbol_from_market_id(market_id)
            if not symbol:
                logger.warning(f"❌ Не удалось определить символ для {market_id}")
                return None

            # Получаем market_duration
            market_duration = self._get_market_duration(market_id)
            if not market_duration:
                logger.warning(f"❌ Не удалось получить market_duration для {market_id}")
                return None

            # Получаем price_to_beat
            price_to_beat = await self._calculate_price_to_beat(market_id)
            if price_to_beat is None:
                logger.warning(f"❌ Не удалось вычислить price_to_beat для {market_id}")
                return None

            # Конвертируем временные метки в ISO формат для сохранения в кэш
            start_time_iso = None
            end_time_iso = None
            
            if isinstance(start_time, (int, float)):
                start_time_iso = datetime.fromtimestamp(start_time, tz=timezone.utc).isoformat()
            elif hasattr(start_time, 'isoformat'):
                start_time_iso = start_time.isoformat()
                
            if isinstance(end_time, (int, float)):
                end_time_iso = datetime.fromtimestamp(end_time, tz=timezone.utc).isoformat()
            elif hasattr(end_time, 'isoformat'):
                end_time_iso = end_time.isoformat()

            return {
                'price_to_beat': price_to_beat,
                'symbol': symbol,
                'market_duration': market_duration,
                'start_time': start_time_iso,
                'end_time': end_time_iso,
                'title': market_title
            }

        except Exception as e:
            logger.error(f"Ошибка вычисления market_info для {market_id}: {e}")
            return None

    def _parse_market_start_time(self, market_title: str) -> Optional[int]:
        """
        Извлечь время начала рынка из market_title.
        
        Args:
            market_title: Название рынка
            
        Returns:
            Время начала в timestamp или None
        """
        try:
            # Используем существующую функцию из polymarket/client.py
            start_time = self.pm_client.get_market_start_time(market_title)
            if start_time:
                # Если это datetime объект, конвертируем в timestamp
                if hasattr(start_time, 'timestamp'):
                    return int(start_time.timestamp())
                # Если это уже timestamp (int/float), возвращаем как есть
                elif isinstance(start_time, (int, float)):
                    return int(start_time)
            return None
        except Exception as e:
            logger.error(f"Ошибка парсинга start_time из {market_title}: {e}")
            return None

    def _parse_market_end_time(self, market_title: str) -> Optional[int]:
        """
        Извлечь время окончания рынка из market_title.
        
        Args:
            market_title: Название рынка
            
        Returns:
            Время окончания в timestamp или None
        """
        try:
            # Используем существующую функцию из polymarket/client.py
            end_time = self.pm_client.get_market_end_time(market_title)
            if end_time:
                # Если это datetime объект, конвертируем в timestamp
                if hasattr(end_time, 'timestamp'):
                    return int(end_time.timestamp())
                # Если это уже timestamp (int/float), возвращаем как есть
                elif isinstance(end_time, (int, float)):
                    return int(end_time)
            return None
        except Exception as e:
            logger.error(f"Ошибка парсинга end_time из {market_title}: {e}")
            return None

    def _infer_symbol_from_title(self, title: str) -> Optional[str]:
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

    def _determine_market_duration(self, title: str) -> str:
        """
        Определить продолжительность рынка по названию.
        
        Args:
            title: Название рынка
            
        Returns:
            "15m" для 15-минутных рынков, "1h" для часовых
        """
        # 15-минутные рынки содержат минуты в названии (:00PM-, :15PM-, etc.)
        is_quarter_hour = any(pattern in title for pattern in [
            ":00AM-", ":00PM-", ":15AM-", ":15PM-", ":30AM-", ":30PM-", ":45AM-", ":45PM-"
        ])
        
        return "15m" if is_quarter_hour else "1h"

    def _get_market_start_time_from_data(self, market_data: Dict) -> Optional[datetime]:
        """
        Получить время открытия рынка из market_data.

        ВАЖНО: Приоритет отдается парсингу из TITLE (реальное время торговли),
        а НЕ полю startDate (время создания рынка в API).
        """
        try:
            # Способ 1 (ПРИОРИТЕТ): Парсим время торговли из названия
            title = market_data.get("question") or market_data.get("title") or ""
            start_time = self.pm_client.get_market_start_time(title)
            if start_time:
                logger.debug(f"✅ Время старта получено из title: {start_time}")
                return start_time

            # Способ 2 (Fallback): Используем startDate (может быть время создания, не торговли!)
            start_date_str = market_data.get("startDate")
            if start_date_str:
                try:
                    parsed_time = datetime.fromisoformat(start_date_str.replace('Z', '+00:00'))
                    logger.warning(f"⚠️  Используем startDate (может быть неточно): {parsed_time}")
                    return parsed_time
                except Exception as e:
                    logger.debug(f"Ошибка парсинга startDate '{start_date_str}': {e}")

            # Способ 3 (Last resort): Fallback на createdAt
            created_at = market_data.get("createdAt")
            if created_at:
                try:
                    parsed_time = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    logger.warning(f"⚠️  Используем createdAt (неточно): {parsed_time}")
                    return parsed_time
                except:
                    pass

            return None
        except Exception as exc:
            logger.debug(f"Ошибка при получении времени открытия: {exc}")
            return None




    def clear_cache(self) -> None:
        """Очистить кэш."""
        self.cache.clear()
        logger.info("Кэш price_to_beat очищен")

    def get_cache_stats(self) -> Dict:
        """Получить статистику кэша."""
        cached_data = []
        for market_id, data in self.cache.items():
            cached_data.append({
                "market_id": market_id,
                "price_to_beat": data.get("price_to_beat"),
                "symbol": data.get("symbol"),
                "market_duration": data.get("market_duration"),
                "title": data.get("title", "")[:50] + "..." if data.get("title") else None
            })
        
        return {
            "cached_markets": len(self.cache),
            "market_ids": list(self.cache.keys()),
            "detailed_cache": cached_data
        }
