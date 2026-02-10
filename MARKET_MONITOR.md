# 🔄 Market Monitor - Автоматическое закрытие позиций

## ✅ Что сделано

**Market Monitor теперь запускается автоматически!**

### Проблема
- MarketMonitor был реализован, но не запускался
- Позиции не закрывались автоматически при завершении рынков
- Приходилось закрывать вручную

### Решение
- Добавлен автозапуск в `web/app.py`
- Запускается для ОБЕИХ стратегий
- Работает в фоне каждые N минут

---

## 🎯 Как работает

### 1. Запуск
```python
# В startup_event (web/app.py)
market_monitor = MarketMonitor(
    polymarket_client=pm_client,
    price_monitor=price_monitor
)
asyncio.create_task(market_monitor.start_monitoring())
```

### 2. Мониторинг (каждые N минут)
```
config.MARKET_MONITOR_INTERVAL = 1  # минута по умолчанию
```

Каждую минуту:
1. Получает все открытые позиции
2. Группирует по рынкам
3. Проверяет статус каждого рынка
4. Закрывает позиции при завершении

### 3. Проверка завершения рынка

**Рынок считается завершенным если:**
- Статус: `"closed"`, `"resolved"`, `"cancelled"`
- ИЛИ: `end_date < текущее время`

### 4. Закрытие позиций

При завершении рынка:
1. Получает `price_to_beat` из PriceToBeatService
2. Получает `end_price` из коллектора
3. Определяет исход: `UP` или `DOWN`
4. Закрывает все позиции рынка
5. Рассчитывает P&L для каждой позиции

---

## 📊 Логи

### При запуске:
```
✓ Market Monitor запущен (интервал: 1 мин)
```

### При проверке позиций (каждую минуту):
```
🔍 Проверка 5 открытых позиций на завершение рынков
📊 Рынок 12345: статус=active, end_date=2026-02-07T13:00:00Z
⏳ Рынок 12345 еще активен
```

### При закрытии рынка:
```
🔍 Проверка 5 открытых позиций на завершение рынков
📊 Рынок 12345: статус=closed, end_date=2026-02-07T13:00:00Z
Рынок завершен по статусу: closed
🎯 Закрываем 3 позиций для рынка 12345
🏆 Исход рынка 12345: UP (end_price $95150.00 >= price_to_beat $95100.00)
✅ Закрыто 3 позиций для рынка 12345
   📝 Закрыта позиция pos_xxx: UP → UP, P&L=$5.00 (10.00%)
   📝 Закрыта позиция pos_yyy: DOWN → UP, P&L=-$10.00 (-100.00%)
   📝 Закрыта позиция pos_zzz: UP → UP, P&L=$3.00 (6.00%)
```

---

## ⚙️ Настройка интервала

В `config.py`:
```python
MARKET_MONITOR_INTERVAL = 1  # минута (по умолчанию)
```

**Рекомендации:**
- `1 минута` - для активной торговли (быстрое закрытие)
- `5 минут` - для нормального режима
- `15 минут` - для экономии ресурсов

**⚠️ Важно:**
- Слишком частая проверка → нагрузка на API
- Слишком редкая → позднее закрытие позиций

---

## 🔍 Статистика мониторинга

Market Monitor предоставляет метод `get_monitoring_stats()`:

```python
{
    "is_running": True,
    "open_positions_count": 5,
    "markets_being_monitored": 3,
    "monitor_interval_minutes": 1,
    "monitored_markets": ["12345", "12346", "12347"]
}
```

---

## 📁 Измененные файлы

### 1. web/app.py
**Добавлено:**
```python
# Импорты
import asyncio
from app import config
from trading.market_monitor import MarketMonitor

# Глобальная переменная
market_monitor: Optional[MarketMonitor] = None

# В startup_event
market_monitor = MarketMonitor(pm_client, price_monitor)
asyncio.create_task(market_monitor.start_monitoring())

# В shutdown_event
if market_monitor:
    market_monitor.stop_monitoring()
```

### 2. trading/market_monitor.py
**Уже было реализовано, только не запускалось!**

---

## 🎓 Логика определения исхода

### 1. Получение данных
```python
price_to_beat = await price_to_beat_service.get_price_to_beat(market_id)
end_price = price_to_beat_service.get_end_price(market_id)
```

### 2. Определение исхода
```python
if end_price >= price_to_beat:
    outcome = "UP"
else:
    outcome = "DOWN"
```

### 3. Расчет P&L

Для каждой позиции:
```python
if position.side == outcome:
    # Выиграл
    pnl = position.total_volume - position.total_cost_usd
else:
    # Проиграл
    pnl = -position.total_cost_usd
```

---

## ✅ Преимущества

1. **Автоматическое закрытие** - не нужно следить вручную
2. **Точный расчет P&L** - для каждой позиции
3. **Работает для обеих стратегий** - default и soft_trading
4. **Настраиваемый интервал** - можно адаптировать под нужды
5. **Надежное определение исхода** - использует price_to_beat и end_price

---

## 🐛 Troubleshooting

### Проблема: "Позиции не закрываются"

**Проверка 1:** Market Monitor запущен?
```bash
# Смотрим логи при старте
python main.py --mode web | grep "Market Monitor"
```
Должно быть: `✓ Market Monitor запущен (интервал: 1 мин)`

**Проверка 2:** Есть ли открытые позиции?
```bash
# В логах каждую минуту должно быть
# 🔍 Проверка X открытых позиций на завершение рынков
```

**Проверка 3:** Рынок действительно завершен?
- Проверьте `end_date` рынка
- Проверьте `state` рынка

### Проблема: "Неправильный исход рынка"

**Причина 1:** Нет `price_to_beat`
- Проверьте PriceToBeatService
- Убедитесь что коллектор работает

**Причина 2:** Нет `end_price`
- Проверьте что коллектор собрал цену на момент окончания
- Используется текущая цена как fallback

### Проблема: "Слишком частые проверки API"

**Решение:** Увеличьте интервал
```python
MARKET_MONITOR_INTERVAL = 5  # 5 минут вместо 1
```

---

## 📈 Мониторинг в реальном времени

Логи Market Monitor можно фильтровать:

```bash
# Только Market Monitor
python main.py --mode web 2>&1 | grep "Market Monitor\|🔍\|🎯\|🏆"

# Только закрытия позиций
python main.py --mode web 2>&1 | grep "Закрыта позиция"

# Только P&L
python main.py --mode web 2>&1 | grep "P&L="
```

---

## ✅ Готово!

Market Monitor теперь работает автоматически для обеих стратегий!

```bash
# Запустите приложение
python main.py --mode web

# Market Monitor запустится автоматически
# Каждую минуту проверяет позиции
# Автоматически закрывает при завершении рынков
```

**Больше не нужно следить вручную! 🔄✅**
