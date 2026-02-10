# 🚀 Автоматический запуск Soft Trading

## ✅ Что сделано

Soft Trading стратегия теперь **автоматически запускается** при старте приложения, если в настройках выбрана эта стратегия!

### Изменения в коде

#### 1. **web/app.py** - автоматический запуск

**Импорты добавлены:**
```python
from trading.position_manager_soft_trading import (
    create_position_manager_soft,
    stop_all_position_managers_soft
)
from app.config import TRADING_STRATEGY
```

**Логика запуска в `@app.on_event("startup")`:**

```python
if TRADING_STRATEGY == "soft_trading":
    # SOFT TRADING: Запускаем менеджеры для активных рынков
    logger.info("🌙 Запуск SOFT TRADING стратегии...")

    markets = pm_client.get_markets()

    for market in markets[:10]:  # Начинаем с 10 рынков
        market_id = market.get("id")

        # Создаем менеджер
        manager = create_position_manager_soft(
            market_id=market_id,
            polymarket_client=pm_client,
            order_manager=order_manager,
            price_monitor=price_monitor
        )

        # Запускаем без начальной позиции
        asyncio.create_task(manager.start_management())

else:
    # DEFAULT: Запускаем auto_entry систему
    auto_entry_system = init_auto_entry_system(...)
    auto_entry_system.start_scheduler()
```

**Логика остановки в `@app.on_event("shutdown")`:**

```python
if TRADING_STRATEGY == "soft_trading":
    stop_all_position_managers_soft()
else:
    stop_all_position_managers()
```

---

## 🎯 Как использовать

### Вариант 1: Через .env файл (рекомендуется)

**1. Откройте `.env`:**
```bash
nano .env
```

**2. Добавьте или измените:**
```bash
TRADING_STRATEGY=soft_trading
```

**3. Сохраните и запустите:**
```bash
python main.py --mode web
```

### Вариант 2: Через config.py

**1. Откройте `app/config.py`:**
```bash
nano app/config.py
```

**2. Найдите и измените:**
```python
TRADING_STRATEGY = "soft_trading"  # Было: "default"
```

**3. Сохраните и запустите:**
```bash
python main.py --mode web
```

---

## 📊 Что увидите в логах

### При запуске с soft_trading:

```
INFO - Polymarket Bot V2
INFO - Режим: SIMULATION
INFO - Монеты: ['Bitcoin', 'Ethereum', 'Solana']

INFO - 📊 Выбранная стратегия: soft_trading
INFO - 🌙 Запуск SOFT TRADING стратегии...
INFO - 📊 Найдено 45 активных рынков

INFO - PositionManagerSoftTrading инициализирован для рынка 12345
INFO - ✅ Запущен soft trading для рынка 12345
INFO - PositionManagerSoftTrading инициализирован для рынка 12346
INFO - ✅ Запущен soft trading для рынка 12346
... (для каждого рынка)

INFO - 🚀 Начато управление позициями SOFT TRADING для рынка 12345
INFO -    📊 Без начальной позиции, мониторим рынок
INFO - ✓ Soft Trading менеджеры запущены
INFO - ✓ Все компоненты инициализированы
```

### При запуске с default:

```
INFO - Polymarket Bot V2
INFO - Режим: SIMULATION
INFO - Монеты: ['Bitcoin', 'Ethereum', 'Solana']

INFO - 📊 Выбранная стратегия: default
INFO - 🎯 Запуск DEFAULT стратегии (auto_entry)...
INFO - ✓ Система автоматического входа запущена
INFO - ✓ Планировщик запущен в фоне
INFO - ✓ Все компоненты инициализированы
```

### Периодические логи (каждые 5 сек):

```
📊 [market_12345] СТАТУС SOFT TRADING MANAGER (каждые 5 сек)
   📂 Позиций: 0
   📈 Вероятности: недоступны
   💰 Цены: недоступны
   ⏰ Активен: True
   🔄 Следующий статус через 5 секунд
```

### При покупке:

```
🎯 [market_12345] ПОКУПКА UP!
   📊 Edge: 6.50% > 5.00%
   💰 Цена: $0.4800
   💵 Сумма: $10.00

💰 Вход в позицию UP на сумму $10.00 по цене $0.4800
✅ Успешный вход в позицию pos_12345_xxx (SOFT_TRADE_ENTRY)
   📊 Позиций UP: 1, DOWN: 0
```

---

## 🔧 Настройка количества рынков

По умолчанию запускаются менеджеры для **10 рынков** (для безопасности).

Чтобы изменить это, отредактируйте `web/app.py`:

```python
# Было:
for market in markets[:10]:  # Начинаем с 10 рынков

# Изменить на:
for market in markets[:20]:  # 20 рынков
# или
for market in markets:  # ВСЕ рынки (не рекомендуется!)
```

**⚠️ Внимание:** Большое количество рынков может:
- Нагружать систему
- Потреблять много памяти
- Замедлять работу

Рекомендуется начать с 5-10 рынков и постепенно увеличивать.

---

## 🎓 Фильтрация рынков

Можно добавить фильтрацию перед запуском менеджеров:

```python
# Пример в web/app.py
for market in markets:
    # Фильтр 1: Только 15-минутные рынки
    title = market.get("title", "")
    if not any(pattern in title for pattern in [":00-", ":15-", ":30-", ":45-"]):
        continue

    # Фильтр 2: Только Bitcoin
    if "Bitcoin" not in title:
        continue

    # Создаем менеджер...
```

---

## 🐛 Troubleshooting

### Проблема: "Не запускается soft trading"

**Проверка 1:** Убедитесь что стратегия установлена:
```bash
python -c "from app import config; print(f'Strategy: {config.TRADING_STRATEGY}')"
```

Должно быть: `Strategy: soft_trading`

**Проверка 2:** Проверьте логи при запуске:
```bash
python main.py --mode web 2>&1 | grep "стратегия"
```

Должно быть: `📊 Выбранная стратегия: soft_trading`

**Проверка 3:** Проверьте что есть активные рынки:
```bash
python main.py --mode web 2>&1 | grep "Найдено"
```

Должно быть: `📊 Найдено XX активных рынков`

### Проблема: "Менеджеры запустились, но нет покупок"

**Причина 1:** Edge не достигает порога (5%)
- Проверьте в логах: `Edge: X.XX% > 5.00%`
- Уменьшите порог в config.py: `SOFT_TRADE_EDGE_ENTER = 3.0`

**Причина 2:** Вероятности не рассчитываются
- Проверьте логи: `📈 Вероятности: недоступны`
- Убедитесь что PriceMonitor работает
- Проверьте что данные Binance/Polymarket поступают

**Причина 3:** Cooldown активен
- После каждой покупки ждет 5 секунд
- Настраивается: `SOFT_TRADE_COOLDOWN_AFTER_BUY = 5.0`

### Проблема: "Слишком много покупок"

**Решение 1:** Увеличьте cooldown:
```python
SOFT_TRADE_COOLDOWN_AFTER_BUY = 30.0  # 30 секунд
```

**Решение 2:** Увеличьте порог edge:
```python
SOFT_TRADE_EDGE_ENTER = 8.0  # Только при высоком edge
```

**Решение 3:** Увеличьте порог улучшения:
```python
SOFT_TRADE_MIN_IMPROVEMENT_PCT = 5.0  # Требуем 5% улучшения
```

---

## 📈 Мониторинг

### Просмотр активных рынков в web UI:

1. Откройте браузер: `http://localhost:8000`
2. Перейдите в раздел "Активные позиции"
3. Увидите все рынки с soft trading менеджерами

### Просмотр логов в реальном времени:

```bash
# Все логи
python main.py --mode web

# Только soft trading
python main.py --mode web 2>&1 | grep "SOFT"

# Только покупки
python main.py --mode web 2>&1 | grep "ПОКУПКА"

# Только статус
python main.py --mode web 2>&1 | grep "СТАТУС"
```

---

## 🎯 Рекомендуемые настройки

### Для начала (консервативно):
```python
SOFT_TRADE_EDGE_ENTER = 7.0  # Высокий порог
SOFT_TRADE_FIRST_POSITION_USD = 5.0  # Малые позиции
SOFT_TRADE_MAX_LOSS_PCT = 3.0  # Малый риск
SOFT_TRADE_MIN_IMPROVEMENT_PCT = 3.0  # Требуем улучшения
SOFT_TRADE_COOLDOWN_AFTER_BUY = 30.0  # Редкие покупки

# В web/app.py:
for market in markets[:5]:  # Только 5 рынков
```

### После тестирования (сбалансировано):
```python
SOFT_TRADE_EDGE_ENTER = 5.0
SOFT_TRADE_FIRST_POSITION_USD = 10.0
SOFT_TRADE_MAX_LOSS_PCT = 5.0
SOFT_TRADE_MIN_IMPROVEMENT_PCT = 2.0
SOFT_TRADE_COOLDOWN_AFTER_BUY = 10.0

# В web/app.py:
for market in markets[:10]:  # 10 рынков
```

### Агрессивно (только после успешного тестирования!):
```python
SOFT_TRADE_EDGE_ENTER = 3.0
SOFT_TRADE_FIRST_POSITION_USD = 20.0
SOFT_TRADE_MAX_LOSS_PCT = 10.0
SOFT_TRADE_MIN_IMPROVEMENT_PCT = 1.0
SOFT_TRADE_COOLDOWN_AFTER_BUY = 5.0

# В web/app.py:
for market in markets[:20]:  # 20 рынков
```

---

## ⚠️ Важные напоминания

1. ✅ **Всегда тестируйте в SIM_MODE сначала!**
   ```python
   SIM_MODE = True  # в config.py
   ```

2. ✅ **Начинайте с малых сумм**
   ```python
   SOFT_TRADE_FIRST_POSITION_USD = 5.0
   ```

3. ✅ **Мониторьте логи первые 30 минут**
   - Проверьте что покупки происходят
   - Убедитесь что edge рассчитывается
   - Проверьте средние цены

4. ✅ **Не забывайте о комиссиях**
   - Каждая покупка ~2%
   - Учитывайте в расчетах

5. ✅ **Всегда можно остановить**
   - Ctrl+C для остановки
   - Все позиции закроются при закрытии рынков

---

**Готово! Запускайте и мониторьте! 🚀🌙**

Вопросы? Смотрите:
- [SOFT_TRADING_STRATEGY.md](SOFT_TRADING_STRATEGY.md) - полное описание
- [SOFT_TRADING_QUICKSTART.md](SOFT_TRADING_QUICKSTART.md) - быстрый старт
- [STRATEGIES.md](STRATEGIES.md) - сравнение стратегий
