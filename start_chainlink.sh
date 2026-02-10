#!/bin/bash

# Скрипт для запуска Chainlink Historical API сервера
# Использование: ./start_chainlink.sh

echo "🚀 Запуск Chainlink Historical API сервера..."

# Переходим в директорию сервера
cd quickstarts-historical-prices-api

# Проверяем наличие node_modules
if [ ! -d "node_modules" ]; then
    echo "📦 Устанавливаем зависимости..."
    npm install
fi

# Запускаем сервер
echo "🌐 Chainlink сервер запускается на http://localhost:3000"
npm run dev