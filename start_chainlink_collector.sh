#!/bin/bash

# Скрипт для запуска Chainlink Price Collector
# Собирает цены BTC, ETH, SOL из Polymarket RTDS и сохраняет в файл
# Использование: ./start_chainlink_collector.sh [--force|-f] для немедленного запуска

echo "🚀 Запуск Polymarket Price Collector..."
echo "Цены BTC, ETH, SOL будут собираться из Polymarket RTDS и сохраняться в data/chainlink_btc_prices.json"
if [ "$FORCE_START" = "true" ]; then
    echo "🧪 Режим тестирования: немедленный запуск"
else
    echo "⏰ Обычный режим: запуск по расписанию (каждые 15 мин)"
fi
echo "Нажмите Ctrl+C для остановки"
echo ""

# Проверяем аргументы командной строки
FORCE_START=false
if [ "$1" = "--force" ] || [ "$1" = "-f" ]; then
    FORCE_START=true
    echo "🧪 Режим тестирования: немедленный запуск"
fi

# Запускаем коллектор
python3 -c "
import sys
sys.path.insert(0, '/Users/sanyadurnov/Documents/Polymarket_bot_V2')
import asyncio
from app.connectors.chainlink_price_collector import ChainlinkPriceCollector

async def main():
    collector = ChainlinkPriceCollector()
    try:
        # Конвертируем строку в boolean
        force_start = '$FORCE_START' == 'true'
        await collector.start_collection(force_start=force_start)
    except KeyboardInterrupt:
        print('\\nПолучен сигнал прерывания')
    finally:
        collector.stop_collection()
        print('Коллектор остановлен')

asyncio.run(main())
"
