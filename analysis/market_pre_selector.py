"""
Market Pre-Selector - предварительный отбор рынков для входа.

Отбирает рынки, которые начинаются через заданное время (например, 1 минуту)
и анализирует их momentum для выбора лучших кандидатов для входа.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from app.config import settings
from app.app_config import app_config
from app.filter_generator import get_polymarket_time
from polymarket.client import PolymarketClient
from monitoring.price_monitor import PriceMonitor

logger = logging.getLogger(__name__)
logger.setLevel(logging.WARNING)  # Отключаем INFO логи, оставляем только WARNING и выше


class MarketPreSelector:
    """
    Предварительный отбор рынков для входа в позицию.

    Запускается за определенное время до начала рынков и отбирает
    рынки с лучшими momentum условиями для входа.
    """

    def __init__(self, polymarket_client: PolymarketClient, price_monitor: PriceMonitor):
        """
        Args:
            polymarket_client: Клиент для работы с Polymarket API
            price_monitor: Монитор цен для анализа индикаторов
        """
        self.pm_client = polymarket_client
        self.price_monitor = price_monitor

    def select_markets_starting_soon(
        self,
        minutes_ahead: int = app_config.best_markets_pre_selector_minutes_ahead,
        symbols: List[str] = None
    ) -> List[Dict]:
        """
        Найти рынки, начинающиеся через 0-3 минуты максимум.

        Args:
            minutes_ahead: Максимальное время до начала (по умолчанию 3 минуты)
            symbols: Список символов для фильтрации (BTC, ETH, SOL)

        Returns:
            Список рынков с временем начала 0-3 минуты
        """
        if symbols is None:
            symbols = ["BTC", "ETH", "SOL", "Bitcoin", "Ethereum", "Solana"]

        logger.info("Поиск рынков, начинающихся через 0-%s минут для символов: %s", minutes_ahead, symbols)

        try:
            # Получаем все доступные рынки
            all_markets = self.pm_client.get_markets()
            if not all_markets:
                logger.warning("Не удалось получить список рынков")
                return []

            selected_markets = []
            current_time = get_polymarket_time()

            for market in all_markets[:100]:  # Увеличиваем лимит для поиска
                if not isinstance(market, dict):
                    continue

                market_id = str(market.get("id", ""))
                title = (
                    market.get("title")
                    or market.get("question")
                    or market.get("name")
                    or market.get("slug", "")
                    or ""
                )

                if not title or not market_id:
                    continue

                # Проверяем, содержит ли название нужный символ
                symbol_found = False
                for symbol in symbols:
                    if symbol.upper() in title.upper():
                        symbol_found = True
                        break

                if not symbol_found:
                    logger.info("Рынок '%s' отсеян: не содержит символы %s", title[:50], symbols)
                    continue

                # Извлекаем время начала рынка
                start_time = self.pm_client.get_market_start_time(title)
                if not start_time:
                    logger.info("Рынок '%s' отсеян: не удалось распарсить время", title[:50])
                    continue

                # Проверяем время начала: от 0 до minutes_ahead минут
                minutes_until_start = (start_time - current_time).total_seconds() / 60
                if 0 <= minutes_until_start <= minutes_ahead:
                    market_info = {
                        "market_id": market_id,
                        "title": title,
                        "symbol": self._extract_symbol_from_title(title, symbols),
                        "start_time": start_time,
                        "minutes_until_start": minutes_until_start,
                        "market_data": market
                    }
                    selected_markets.append(market_info)
                    logger.debug("Найден рынок через %.1f мин: %s", minutes_until_start, title[:50])
                else:
                    logger.info("Рынок '%s' отсеян: время %.1f мин вне диапазона 0-%s мин",
                               title[:50], minutes_until_start, minutes_ahead)

            logger.info("Найдено %s рынков, начинающихся через 0-%s минут", len(selected_markets), minutes_ahead)
            if selected_markets:
                logger.info("Список найденных рынков:")
                for i, market in enumerate(selected_markets[:5], 1):  # Показываем первые 5
                    logger.info("  %s) %s: через %.1f мин",
                               i, market["title"][:60], market["minutes_until_start"])
                if len(selected_markets) > 5:
                    logger.info("  ... и еще %s рынков", len(selected_markets) - 5)
            return selected_markets

        except Exception as exc:
            logger.error("Ошибка при поиске рынков: %s", exc, exc_info=True)
            return []

    def analyze_market_momentum(self, market_id: str) -> Optional[Dict]:
        """
        Проанализировать momentum для конкретного рынка.

        Args:
            market_id: ID рынка

        Returns:
            Словарь с анализом momentum или None при ошибке
        """
        try:
            # Получаем данные рынка
            market_data = self.pm_client.get_market_data(market_id)
            if not market_data:
                logger.warning("Не удалось получить данные рынка %s", market_id)
                return None

            # Определяем символ из названия
            title = (
                market_data.get("question")
                or market_data.get("title")
                or market_data.get("name")
                or ""
            )

            symbol = self._extract_symbol_from_title(title, ["BTC", "ETH", "SOL", "Bitcoin", "Ethereum", "Solana"])
            if not symbol:
                logger.warning("Не удалось определить символ для рынка %s", market_id)
                return None

            # Получаем статистику индикаторов
            # Преобразуем символ в формат Binance (BTC -> BTCUSDT, ETH -> ETHUSDT, SOL -> SOLUSDT)
            binance_symbol = f"{symbol}USDT"
            stats = self.price_monitor.get_stats(binance_symbol)
            if not stats:
                logger.warning("Не удалось получить статистику для символа %s (пробовали %s) - stats is None", symbol, binance_symbol)
                # Попробуем получить latest_stats напрямую
                latest_stats = getattr(self.price_monitor, 'latest_stats', {})
                if binance_symbol in latest_stats:
                    stats = latest_stats[binance_symbol]
                    logger.info("Нашли данные в latest_stats для %s", binance_symbol)
                else:
                    logger.warning("Данные не найдены даже в latest_stats для %s", binance_symbol)
                    return None

            momentum_data = stats.get("momentums", {})
            volatility_data = stats.get("volatility", {})

            # Рассчитываем momentum score
            momentum_score = self._calculate_momentum_score(momentum_data)

            # Определяем направление тренда
            trend_direction = self._determine_trend_direction(momentum_data)

            analysis = {
                "market_id": market_id,
                "symbol": symbol,
                "title": title,
                "momentum_score": momentum_score,
                "trend_direction": trend_direction,
                "momentum_data": momentum_data,
                "volatility_data": volatility_data,
                "current_price": stats.get("price"),
                "timestamp": stats.get("timestamp")
            }

            logger.debug("Анализ momentum для %s (%s): score=%.3f, direction=%s",
                        market_id, symbol, momentum_score, trend_direction)
            return analysis

        except Exception as exc:
            logger.error("Ошибка при анализе momentum для рынка %s: %s", market_id, exc, exc_info=True)
            return None

    def select_best_momentum_markets(
        self,
        markets: List[Dict],
        min_score: float = 0.5,
        max_markets: int = 3
    ) -> Dict:
        """
        Каскадный отбор рынков по иерархическим критериям с разделением по типам:

        Уровень 1: 2 из 3 таймфреймов + 15m > |2%| (идеальные условия)
        Уровень 2: Только 15m > |2%| (хорошие условия)
        Уровень 3: Максимальный доступный momentum (любые условия)

        Args:
            markets: Список рынков для анализа
            min_score: Минимальный momentum score для отбора
            max_markets: Максимальное количество рынков для возврата в каждой категории

        Returns:
            Словарь с разделением по типам рынков:
            {
                "15m_markets": [...],  # Лучшие 15-минутные рынки
                "1h_markets": [...],   # Лучшие часовые рынки
                "all_markets": [...]   # Лучшие рынки из всех типов
            }
        """
        logger.info("Каскадный анализ momentum для %s рынков", len(markets))
        logger.info("Список рынков для анализа:")
        for i, market in enumerate(markets, 1):
            logger.info("  %s) %s", i, market.get("title", "")[:60])

        # Анализируем все рынки один раз
        analyzed_markets = []
        for market in markets:
            market_id = market.get("market_id")
            if not market_id:
                continue

            logger.debug("Анализируем рынок %s: %s", market_id, market.get("title", "")[:50])
            analysis = self.analyze_market_momentum(market_id)
            if analysis:
                # Используем правильный title из исходного market вместо market_data
                correct_title = market.get("title", analysis.get("title", ""))
                analysis["title"] = correct_title

                # Добавляем информацию о времени начала
                analysis.update({
                    "start_time": market.get("start_time"),
                    "minutes_until_start": market.get("minutes_until_start")
                })
                # Добавляем тип рынка
                analysis["market_type"] = self._get_market_type(correct_title)
                # Добавляем рекомендуемую сторону входа на основе momentum основного таймфрейма
                market_type = analysis["market_type"]
                primary_tf = "15m" if market_type == "15m" else "1h"
                primary_momentum = analysis.get("momentum_data", {}).get(primary_tf, 0)
                analysis["recommended_side"] = self._get_recommended_side(primary_momentum)
                analyzed_markets.append(analysis)
                logger.debug("Рынок %s проанализирован: symbol=%s, type=%s, momentum_15m=%s",
                           market_id, analysis.get("symbol"), analysis.get("market_type"),
                           analysis.get("momentum_data", {}).get("15m"))
            else:
                logger.warning("Не удалось проанализировать рынок %s", market_id)

        if not analyzed_markets:
            logger.warning("Не удалось проанализировать ни один рынок")
            return {"15m_markets": [], "1h_markets": [], "all_markets": []}

        # Группируем рынки по типам
        markets_15m = [m for m in analyzed_markets if m.get("market_type") == "15m"]
        markets_1h = [m for m in analyzed_markets if m.get("market_type") == "1h"]

        logger.info("Группировка по типам: 15m=%s, 1h=%s", len(markets_15m), len(markets_1h))
        logger.info("Примеры группировки:")
        for market in analyzed_markets[:10]:  # Показываем первые 10
            logger.info("  %s: type=%s", market.get("title", "")[:60], market.get("market_type"))

        # Каскадный отбор для каждой группы с сортировкой по соответствующему momentum
        top_15m = self._cascade_selection(markets_15m, max_markets, sort_by="15m") if markets_15m else []
        top_1h = self._cascade_selection(markets_1h, max_markets, sort_by="1h") if markets_1h else []
        top_all = self._cascade_selection(analyzed_markets, max_markets, sort_by="score")

        logger.info("Каскадный отбор завершен:")
        logger.info("  15m рынков отобрано: %s", len(top_15m))
        logger.info("  1h рынков отобрано: %s", len(top_1h))
        logger.info("  Всего рынков отобрано: %s", len(top_all))

        return {
            "15m_markets": top_15m,
            "1h_markets": top_1h,
            "all_markets": top_all
        }

    def _cascade_selection(self, analyzed_markets: List[Dict], max_markets: int, sort_by: str = "score") -> List[Dict]:
        """
        Каскадный отбор рынков по уровням строгости критериев.

        Args:
            analyzed_markets: Список проанализированных рынков
            max_markets: Максимальное количество для возврата
            sort_by: Как сортировать - "score", "15m", "1h"

        Returns:
            Отобранные рынки
        """
        # Функция для получения ключа сортировки
        def get_sort_key(market):
            if sort_by == "15m":
                return abs(market.get("momentum_data", {}).get("15m", 0))
            elif sort_by == "1h":
                return abs(market.get("momentum_data", {}).get("1h", 0))
            else:  # "score"
                return market.get("momentum_score", 0)

        # Уровень 1: Строгие критерии (2 из 3 таймфреймов + 15m > |2%|)
        level1_markets = [
            market for market in analyzed_markets
            if self._meets_strict_criteria(market)
        ]

        if level1_markets:
            logger.info("Уровень 1: найдено %s рынков со строгими критериями", len(level1_markets))
            sorted_markets = sorted(level1_markets, key=get_sort_key, reverse=True)
            return sorted_markets[:max_markets]

        # Уровень 2: Ослабленные критерии (только 15m > |2%|)
        level2_markets = [
            market for market in analyzed_markets
            if self._meets_relaxed_criteria(market)
        ]

        if level2_markets:
            logger.info("Уровень 2: найдено %s рынков с ослабленными критериями", len(level2_markets))
            sorted_markets = sorted(level2_markets, key=get_sort_key, reverse=True)
            return sorted_markets[:max_markets]

        # Уровень 3: Минимальные критерии (максимальный momentum)
        logger.info("Уровень 3: используем минимальные критерии (все доступные рынки)")
        sorted_markets = sorted(analyzed_markets, key=get_sort_key, reverse=True)
        return sorted_markets[:max_markets]

    def _meets_strict_criteria(self, analysis: Dict) -> bool:
        """
        Строгие критерии входа:
        1. Минимум 2 из 3 таймфреймов в одном направлении
        2. 15m momentum > |2%|

        Args:
            analysis: Результат анализа momentum

        Returns:
            True если соответствует строгим критериям
        """
        momentum_data = analysis.get("momentum_data", {})

        # Критерий 1: 15m momentum > |2%|
        momentum_15m = momentum_data.get("15m")
        if momentum_15m is None or abs(momentum_15m) <= 0.02:  # |2%| = 0.02
            return False

        # Критерий 2: Минимум 2 из 3 таймфреймов в одном направлении
        timeframes = ["1m", "5m", "15m"]
        positive_count = 0
        negative_count = 0

        for tf in timeframes:
            value = momentum_data.get(tf)
            if value is not None:
                if value > 0.001:  # Положительный
                    positive_count += 1
                elif value < -0.001:  # Отрицательный
                    negative_count += 1

        # Минимум 2 из 3 в одном направлении
        min_agreement = 2
        return positive_count >= min_agreement or negative_count >= min_agreement

    def _meets_relaxed_criteria(self, analysis: Dict) -> bool:
        """
        Ослабленные критерии входа:
        Только 15m momentum > |2%|

        Args:
            analysis: Результат анализа momentum

        Returns:
            True если соответствует ослабленным критериям
        """
        momentum_data = analysis.get("momentum_data", {})

        # Единственный критерий: 15m momentum > |2%|
        momentum_15m = momentum_data.get("15m")
        market_id = analysis.get("market_id", "unknown")
        title = analysis.get("title", "")[:50]

        if momentum_15m is None:
            logger.debug("Рынок %s (%s): momentum_15m is None", market_id, title)
            return False

        if abs(momentum_15m) <= 0.02:
            logger.debug("Рынок %s (%s): momentum_15m=%.4f <= 0.02", market_id, title, momentum_15m)
            return False

        logger.debug("Рынок %s (%s): прошел критерий momentum_15m=%.4f", market_id, title, momentum_15m)
        return True

    def _meets_entry_criteria(self, analysis: Dict) -> bool:
        """
        Проверить, соответствует ли рынок критериям входа:
        Только 15m momentum > |2%|

        Args:
            analysis: Результат анализа momentum

        Returns:
            True если соответствует критериям
        """
        momentum_data = analysis.get("momentum_data", {})

        # Единственный критерий: 15m momentum > |2%|
        momentum_15m = momentum_data.get("15m")
        if momentum_15m is None or abs(momentum_15m) <= 0.02:  # |2%| = 0.02
            return False

        return True

    def _get_recommended_side(self, primary_momentum: float) -> str:
        """
        Определить рекомендуемую сторону входа по знаку momentum.

        Args:
            primary_momentum: Momentum основного таймфрейма

        Returns:
            "UP" если momentum >= 0, "DOWN" если momentum < 0
        """
        return "UP" if primary_momentum >= 0 else "DOWN"

    def _extract_symbol_from_title(self, title: str, symbols: List[str]) -> Optional[str]:
        """
        Извлечь символ из названия рынка.

        Args:
            title: Название рынка
            symbols: Список возможных символов

        Returns:
            Найденный символ или None
        """
        if not title:
            return None

        # Маппинг полных названий на сокращения для Binance
        symbol_mapping = {
            "BITCOIN": "BTC",
            "ETHEREUM": "ETH",
            "SOLANA": "SOL"
        }

        title_upper = title.upper()
        for symbol in symbols:
            if symbol.upper() in title_upper:
                # Если нашли полное название, возвращаем сокращение
                return symbol_mapping.get(symbol.upper(), symbol.upper())

        return None

    def _calculate_momentum_score(self, momentum_data: Dict) -> float:
        """
        Рассчитать общий momentum score на основе данных по разным таймфреймам.

        Args:
            momentum_data: Словарь с momentum по таймфреймам

        Returns:
            Score от 0 до 1 (выше = лучше для входа)
        """
        if not momentum_data:
            return 0.0

        # Весовые коэффициенты для разных таймфреймов
        weights = {
            "1m": 0.1,   # Краткосрочный - низкий вес
            "5m": 0.2,   # Среднесрочный
            "15m": 0.3,  # Важный таймфрейм
            "1h": 0.4    # Долгосрочный тренд - высокий вес
        }

        total_weight = 0
        weighted_sum = 0

        for timeframe, weight in weights.items():
            momentum_value = momentum_data.get(timeframe)
            if momentum_value is not None:
                # Нормализуем momentum (предполагаем диапазон -5% до +5%)
                # Преобразуем в score от 0 до 1
                normalized = max(0, min(1, (momentum_value + 5) / 10))
                weighted_sum += normalized * weight
                total_weight += weight

        if total_weight == 0:
            return 0.0

        return weighted_sum / total_weight

    def _determine_trend_direction(self, momentum_data: Dict) -> str:
        """
        Определить направление тренда на основе momentum данных.

        Args:
            momentum_data: Словарь с momentum по таймфреймам

        Returns:
            "BULLISH", "BEARISH", или "NEUTRAL"
        """
        if not momentum_data:
            return "NEUTRAL"

        # Считаем положительные и отрицательные momentum
        positive_count = 0
        negative_count = 0

        for timeframe, value in momentum_data.items():
            if value is None:
                continue

            if value > 0.1:  # Положительный momentum > 0.1%
                positive_count += 1
            elif value < -0.1:  # Отрицательный momentum < -0.1%
                negative_count += 1

        total_signals = positive_count + negative_count

        if total_signals == 0:
            return "NEUTRAL"

        # Если больше 60% сигналов в одном направлении
        if positive_count / total_signals > 0.6:
            return "BULLISH"
        elif negative_count / total_signals > 0.6:
            return "BEARISH"
        else:
            return "NEUTRAL"

    def _get_market_type(self, title: str) -> str:
        """
        Определить тип рынка по названию.

        Args:
            title: Название рынка

        Returns:
            "15m" для 15-минутных рынков, "1h" для часовых
        """
        has_minutes = any(pattern in title for pattern in [":00", ":15", ":30", ":45"])
        market_type = "15m" if has_minutes else "1h"
        logger.debug("Market type for '%s': %s (has_minutes: %s)", title, market_type, has_minutes)
        return market_type
