# Chainlink Historical API - Руководство по запуску

## 🎯 Обзор

Chainlink Historical API предоставляет исторические данные Chainlink Price Feeds для расчета **Price to beat** в Polymarket боте.

## 🏗️ Архитектура

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Polymarket    │    │  Chainlink API   │    │   Blockchain     │
│      Bot        │◄──►│   (localhost)    │◄──►│  (Ethereum)     │
│                 │    │    :3000         │    │                 │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

## 🚀 Быстрый запуск

### 1. Запуск Chainlink сервера (отдельный процесс)
```bash
# Вариант 1: Использовать скрипт
./start_chainlink.sh

# Вариант 2: Ручной запуск
cd quickstarts-historical-prices-api
npm run dev
```

### 2. Запуск Polymarket бота (в другом терминале)
```bash
source .venv/bin/activate
python3 main.py --mode web
```

## 📊 Проверка работы

### Проверить Chainlink API:
```bash
curl "http://localhost:3000/api/price?contractAddress=0x5f4eC3Df9cbd43714FE2740f5E3616155c5b8419&startTimestamp=1706745600&endTimestamp=1706749200&chain=mainnet&rpcUrl=https://eth-mainnet.alchemyapi.io/v2/demo"
```

### Проверить Web UI:
```
http://localhost:8000
```

## 🔧 Конфигурация

### Адреса контрактов (Ethereum mainnet):
- **BTC/USD**: `0xf4030086522a5beea4988f8ca5b36dbc97bee88c`
- **ETH/USD**: `0x5f4eC3Df9cbd43714fe2740f5e3616155c5b8419`
- **SOL/USD**: `0x4ffc43a60e009b551865a93d232e33fce9f01507`

### RPC URL:
По умолчанию используется Alchemy demo endpoint. Для продакшена замените на свой API key.

## 📈 Данные и производительность

### Частота обновлений Chainlink:
- **BTC/USD**: 1-6 обновлений в час
- **ETH/USD**: 1-4 обновления в час
- **Heartbeat**: 1 час (гарантированное обновление)

### Объем данных:
- **1 round**: ~72 байта
- **1 час**: 72-432 байта
- **1 день**: 1.7-10 KB
- **1 месяц**: 50-300 KB

### Кэширование:
- **Время кэша**: 15 минут
- **Частота чтения**: Раз в 3 часа достаточно

## 🛠️ Автозапуск (опционально)

### Для macOS (launchd):
```bash
# Создать plist файл в ~/Library/LaunchAgents/
# Содержимое: запуск ./start_chainlink.sh при логине
```

### Для Linux (systemd):
```bash
# Создать service файл
# Автозапуск при загрузке системы
```

## 🔍 Отладка

### Логи Chainlink сервера:
```bash
cd quickstarts-historical-prices-api
npm run dev 2>&1 | tee chainlink.log
```

### Проверка доступности:
```bash
# Python
python3 -c "
import requests
try:
    r = requests.get('http://localhost:3000/api/price', timeout=5)
    print(f'Статус: {r.status_code}')
except Exception as e:
    print(f'Ошибка: {e}')
"
```

## 🎯 Использование в коде

```python
from app.connectors.chainlink_historical import ChainlinkHistoricalConnector

# Получить исторические данные
connector = ChainlinkHistoricalConnector()
prices = await connector.get_historical_prices(
    symbol="BTCUSDT",
    start_timestamp=int(time.time()) - 3600,  # Последний час
    end_timestamp=int(time.time())
)

# Получить цену на конкретное время
price = await connector.get_price_at_time(
    symbol="BTCUSDT",
    timestamp=datetime.now() - timedelta(hours=1)
)
```

## ⚠️ Важные замечания

1. **Локальный сервер**: Chainlink не предоставляет публичный API
2. **RPC лимиты**: Используйте собственный RPC endpoint для продакшена
3. **Кэширование**: Данные кэшируются 15 минут для оптимизации
4. **Fallback**: При недоступности Chainlink используется текущая цена

## 🆘 Troubleshooting

### Ошибка "Cannot connect to localhost:3000"
```bash
# Проверить запущен ли сервер
ps aux | grep "npm run dev"

# Перезапустить
./start_chainlink.sh
```

### Ошибка RPC
```bash
# Проверить RPC URL в коде
# Заменить на свой Alchemy/Infura endpoint
```

### Пустые данные
```bash
# Проверить timestamp (Unix seconds)
# Проверить contract address
# Проверить RPC доступность