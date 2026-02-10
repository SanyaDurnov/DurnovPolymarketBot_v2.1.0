# ✅ Soft Trading - Финальная реализация

## 🎯 Как работает

### Запуск по расписанию (как auto_entry)

**1. MarketPreSelector выбирает лучшие рынки**
- 15-минутные рынки (если включено)
- Часовые рынки (если включено)
- На основе momentum и других критериев

**2. За N минут до старта рынка (настраивается)**
```python
FIRST_ENTRY_MINUTES_BEFORE_START = 1  # За 1 минуту
```

**3. Запускается PositionManagerSoftTrading**
- БЕЗ начальной покупки
- Только мониторинг и покупки по условиям

**4. Менеджер работает до закрытия рынка**
- Мониторит edge для UP и DOWN
- Покупает при edge > 5%
- Усредняет позиции
- Цель: avg_UP + avg_DOWN < $1.00

---

## 📁 Созданные файлы

### Основная логика
1. **trading/soft_trading_entry.py** ⭐ NEW!
   - Система запуска по расписанию
   - Аналог auto_entry для soft trading
   - Выбор рынков через MarketPreSelector

2. **trading/position_manager_soft_trading.py**
   - Менеджер позиций для soft trading
   - Мониторинг и покупки по условиям
   - Арбитражная логика

### Конфигурация
3. **app/config.py** - параметры:
```python
# Выбор стратегии
TRADING_STRATEGY = "soft_trading"  # или "default"

# Параметры soft trading
SOFT_TRADE_EDGE_ENTER = 5.0
SOFT_TRADE_FIRST_POSITION_USD = 10.0
SOFT_TRADE_MAX_LOSS_PCT = 5.0
...
```

### Запуск
4. **web/app.py** - автозапуск:
```python
if TRADING_STRATEGY == "soft_trading":
    soft_trading_entry_system = init_soft_trading_entry_system(...)
    soft_trading_entry_system.start_scheduler()
else:
    auto_entry_system = init_auto_entry_system(...)
    auto_entry_system.start_scheduler()
```

---

## 🚀 Запуск

### 1. Настроить стратегию

В `.env`:
```bash
TRADING_STRATEGY=soft_trading
```

### 2. Настроить параметры (опционально)

В `config.py`:
```python
# Какие рынки использовать
ENTER_TO_1H_MARKETS = True
ENTER_TO_15M_MARKETS = True
H1_MARKETS_NUMBER_TO_ENTER = 1
M15_MARKETS_NUMBER_TO_ENTER = 1

# За сколько минут до старта запускать
FIRST_ENTRY_MINUTES_BEFORE_START = 1

# Параметры soft trading
SOFT_TRADE_EDGE_ENTER = 5.0
SOFT_TRADE_FIRST_POSITION_USD = 10.0
```

### 3. Запустить

```bash
python main.py --mode web
```

---

## 📊 Что увидите в логах

### При старте приложения:
```
📊 Выбранная стратегия: soft_trading
🌙 Запуск SOFT TRADING стратегии...
🌙 Запуск планировщика Soft Trading...
🌙 Запланирован запуск в :59 (для рынка в :00)
🌙 Запланирован запуск в :14 (для рынка в :15)
🌙 Запланирован запуск в :29 (для рынка в :30)
🌙 Запланирован запуск в :44 (для рынка в :45)
✅ Планировщик Soft Trading запущен. Сессии будут запускаться за 1 мин до старта рынков
✓ Планировщик запущен в фоне
✓ Все компоненты инициализированы
```

### За 1 минуту до старта рынка:
```
🚀 Запуск сессии Soft Trading Entry
📈 Начало сессии Soft Trading Entry в 2026-02-07 12:59:00

[Выбор рынков через MarketPreSelector]
✅ Выбрано 1 15m рынков для soft trading
✅ Выбрано 1 1h рынков для soft trading

🌙 Запуск Soft Trading для рынка 12345
PositionManagerSoftTrading инициализирован для рынка 12345
✅ Soft Trading менеджер запущен для рынка 12345

🚀 Начато управление SOFT TRADING для рынка 12345
   📊 Без начальной позиции, мониторим рынок

✅ Сессия Soft Trading Entry завершена за 0.5 сек
```

### Мониторинг рынка (каждые 5 сек):
```
📊 [market_12345] СТАТУС SOFT TRADING MANAGER (каждые 5 сек)
   📂 Позиций: 0
   📈 Вероятности: UP=0.550, DOWN=0.480
   💰 Цены: UP=$0.4800, DOWN=$0.5200
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

### После нескольких покупок:
```
📊 [market_12345] СТАТУС SOFT TRADING MANAGER
   💎 SOFT TRADING:
      UP: 1 поз, avg=$0.4800
      DOWN: 2 поз, avg=$0.4921
      СУММА: $0.9721 ✅ ПРИБЫЛЬ
      До цели (0.98): +0.79%
```

---

## 🔧 Сравнение стратегий

### Default (auto_entry + position_manager)
```
1. MarketPreSelector выбирает топ рынки
2. За 1 мин до старта → auto_entry
3. Auto-entry постепенно покупает одну сторону (2 итерации по 20 сек)
4. Position manager следит за позицией
5. При условиях входит в противоположную сторону (хедж)
6. При падении цены усиливает исходную позицию
```

### Soft Trading (soft_trading_entry + position_manager_soft_trading)
```
1. MarketPreSelector выбирает топ рынки
2. За 1 мин до старта → soft_trading_entry
3. Запускает только PositionManagerSoftTrading (БЕЗ покупки)
4. Менеджер мониторит edge для UP и DOWN
5. При edge > 5% покупает любую сторону
6. Усредняет позиции обеих сторон
7. Цель: avg_UP + avg_DOWN < $1.00
```

---

## ⚙️ Настройка количества рынков

В `config.py`:
```python
# Сколько рынков выбирать
H1_MARKETS_NUMBER_TO_ENTER = 1  # 1 часовой рынок
M15_MARKETS_NUMBER_TO_ENTER = 1  # 1 15-минутный рынок

# Включить/выключить типы рынков
ENTER_TO_1H_MARKETS = True
ENTER_TO_15M_MARKETS = True
```

---

## 🎓 Преимущества новой реализации

✅ **Выбор лучших рынков** - MarketPreSelector выбирает топ рынки по momentum

✅ **Запуск в нужное время** - за N минут до старта, не рано и не поздно

✅ **Контроль количества** - входим только в N лучших рынков, не во все

✅ **Консистентность** - работает так же как auto_entry, легко понять

✅ **Гибкость** - можно настроить когда запускать и сколько рынков

---

## 📚 Документация

1. [SOFT_TRADING_STRATEGY.md](SOFT_TRADING_STRATEGY.md) - полное описание алгоритма
2. [SOFT_TRADING_QUICKSTART.md](SOFT_TRADING_QUICKSTART.md) - быстрый старт
3. [STRATEGIES.md](STRATEGIES.md) - сравнение стратегий
4. **SOFT_TRADING_FINAL.md** (этот файл) - финальная реализация

---

## ✅ Готово к использованию!

```bash
# Установить стратегию
echo "TRADING_STRATEGY=soft_trading" >> .env

# Запустить
python main.py --mode web

# Ждать до :59, :14, :29, :44
# Система автоматически запустит менеджеры для лучших рынков
```

**Всё работает автоматически по расписанию! 🌙📊💰**
