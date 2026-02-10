# Polymarket Bot V2

Упрощенный бот для торговли на Polymarket с поддержкой симуляции (SIM MODE).

## 🎯 Возможности

- ✅ Загрузка и фильтрация маркетов Polymarket с кэшированием
- ✅ Мониторинг цен BTC/ETH/SOL с Binance и Polymarket RTDS
- ✅ Расчет индикаторов: RSI, MACD, ATR, SMA, Momentum, Volatility
- ✅ Получение orderbook и лучших bid/ask цен
- ✅ Вероятностный анализ (math_prob, market_prob, edge, p_hit, p_terminal)
- ✅ **SIM MODE** - тестирование стратегий без реальных денег
- ✅ Web UI для мониторинга и управления
- ✅ Position Manager для управления бюджетом

## 📦 Установка

1. Клонируйте репозиторий:
```bash
cd /Users/sanyadurnov/Documents/Polymarket_bot_V2
```

2. Создайте виртуальное окружение:
```bash
python3 -m venv venv
source venv/bin/activate  # На Windows: venv\Scripts\activate
```

3. Установите зависимости:
```bash
pip install -r requirements.txt
```

4. Настройте переменные окружения:
```bash
cp .env.example .env
# Отредактируйте .env файл, добавив свои ключи
```

## 🚀 Запуск

### Режим симуляции (по умолчанию):
```bash
python main.py
```

### Запуск Web UI:
```bash
python main.py --mode web
```

Откройте браузер: http://localhost:8000

### Режим тестирования:
```bash
python main.py --mode test
```

## ⚙️ Настройка

Все настройки находятся в файле `config.py`:

- `SIM_MODE = True` - включить режим симуляции
- `SIMULATION_INITIAL_BALANCE` - начальный баланс для симуляции
- `COINS` - список монет для мониторинга
- `AUTO_GENERATE_FILTERS` - автоматическая генерация фильтров
- `TRADING_STRATEGY` - выбор стратегии торговли:
  - `"default"` - стандартная стратегия с auto_entry и position_manager
  - `"soft_trading"` - мягкая стратегия без auto_entry (более консервативный подход)
- И многое другое...

## 📊 Структура проекта

```
Polymarket_bot_V2/
├── polymarket/          # Работа с Polymarket API
├── monitoring/          # Мониторинг цен (Binance + Polymarket)
├── indicators/          # Технические индикаторы
├── analysis/            # Вероятностный анализ
├── trading/             # Управление ордерами и позициями
├── storage/             # Хранение данных
├── web/                 # Web UI (FastAPI)
└── static/              # Frontend (HTML/CSS/JS)
```

## 🔐 Безопасность

- Никогда не коммитьте файл `.env` с реальными ключами
- В SIM MODE реальные ордера не создаются
- Для перехода в реальный режим измените `SIM_MODE = False` в `config.py`

## 📝 Лицензия

MIT
