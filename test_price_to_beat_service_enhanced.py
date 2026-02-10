#!/usr/bin/env python3
"""
Тест для проверки расширенного PriceToBeatService.
Проверяет работу новых методов: get_symbol, get_market_duration, get_market_info.
"""

import asyncio
import logging
import sys
from datetime import datetime, timezone

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Добавляем путь к проекту
sys.path.insert(0, '.')

from analysis.price_to_beat_service import PriceToBeatService
from app.config import settings
from polymarket.client import PolymarketClient
from monitoring.price_monitor import PriceMonitor


async def test_enhanced_price_to_beat_service():
    """Тест расширенного PriceToBeatService."""
    logger.info("=" * 60)
    logger.info("ТЕСТ РАСШИРЕННОГО PriceToBeatService")
    logger.info("=" * 60)
    
    try:
        # 1. Инициализация компонентов
        logger.info("1. Инициализация компонентов...")
        pm_client = PolymarketClient()
        price_monitor = PriceMonitor()
        price_to_beat_service = PriceToBeatService(price_monitor, pm_client)
        
        # 2. Получение рынков
        logger.info("2. Получение рынков...")
        markets = pm_client.get_markets()
        if not markets:
            logger.error("Не удалось получить рынки")
            return 1
        
        logger.info(f"Получено {len(markets)} рынков")
        
        # 3. Тестирование на первых 3 рынках
        test_markets = markets[:3]
        logger.info(f"Тестируем на {len(test_markets)} рынках")
        
        for i, market in enumerate(test_markets, 1):
            market_id = str(market.get("id", ""))
            title = market.get("title") or market.get("question") or "N/A"
            
            logger.info(f"\n--- Тест рынка {i}: {market_id} ---")
            logger.info(f"Название: {title[:80]}")
            
            # 4. Тест get_price_to_beat
            logger.info("Тест get_price_to_beat...")
            price_to_beat = await price_to_beat_service.get_price_to_beat(market_id)
            if price_to_beat:
                logger.info(f"✅ Price_to_beat: ${price_to_beat}")
            else:
                logger.warning("❌ Price_to_beat не получен")
                continue
            
            # 5. Тест get_symbol
            logger.info("Тест get_symbol...")
            symbol = price_to_beat_service.get_symbol(market_id)
            if symbol:
                logger.info(f"✅ Symbol: {symbol}")
            else:
                logger.warning("❌ Symbol не получен")
            
            # 6. Тест get_market_duration
            logger.info("Тест get_market_duration...")
            duration = price_to_beat_service.get_market_duration(market_id)
            if duration:
                logger.info(f"✅ Market duration: {duration}")
            else:
                logger.warning("❌ Market duration не получена")
            
            # 7. Тест get_market_info
            logger.info("Тест get_market_info...")
            market_info = price_to_beat_service.get_market_info(market_id)
            if market_info:
                logger.info("✅ Market info:")
                for key, value in market_info.items():
                    logger.info(f"   {key}: {value}")
            else:
                logger.warning("❌ Market info не получена")
            
            # 8. Проверка кэша
            logger.info("Проверка кэша...")
            cache_stats = price_to_beat_service.get_cache_stats()
            logger.info(f"Кэш содержит {cache_stats['cached_markets']} рынков")
        
        # 9. Статистика кэша
        logger.info("\n--- Статистика кэша ---")
        cache_stats = price_to_beat_service.get_cache_stats()
        logger.info(f"Всего закэшировано рынков: {cache_stats['cached_markets']}")
        
        if cache_stats['detailed_cache']:
            logger.info("Детали кэша:")
            for item in cache_stats['detailed_cache']:
                logger.info(f"  {item['market_id']}: {item['symbol']} ({item['market_duration']}) - ${item['price_to_beat']}")
        
        logger.info("\n" + "=" * 60)
        logger.info("ТЕСТ ЗАВЕРШЕН УСПЕШНО")
        logger.info("=" * 60)
        
        return 0
        
    except Exception as exc:
        logger.error("❌ Ошибка при тестировании: %s", exc, exc_info=True)
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(test_enhanced_price_to_beat_service())
    sys.exit(exit_code)