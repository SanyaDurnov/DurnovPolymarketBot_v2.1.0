#!/bin/bash
# Скрипт для отслеживания логов бота в реальном времени
# Использование: ./watch_logs.sh

echo "==================================================================="
echo "📊 Мониторинг логов Polymarket Bot V2"
echo "==================================================================="
echo ""
echo "Отслеживание файла: logs/trading_bot.log"
echo "Фильтры: auto_entry, position_manager, вход в позицию, opposite entry"
echo ""
echo "Для выхода нажмите Ctrl+C"
echo "==================================================================="
echo ""

# Следить за логами с фильтром по ключевым словам
tail -f logs/trading_bot.log | grep --line-buffered -E \
  "auto_entry|position_manager|Position Manager|🎯|🛒|💰|📊.*СТАТУС|Opposite entry|Additional entry|вероятность|УСЛОВИЯ ДЛЯ ВХОДА|Начинаем вход"
