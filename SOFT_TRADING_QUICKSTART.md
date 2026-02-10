# 🚀 Soft Trading - Быстрый старт

## ✅ Что реализовано

### 1. Параметры конфигурации

В [config.py:178-186](app/config.py#L178-L186):
```python
SOFT_TRADE_EDGE_ENTER = 5.0  # Минимальный edge для входа (%)
SOFT_TRADE_FIRST_POSITION_USD = 10.0  # Размер первой позиции ($)
SOFT_TRADE_MAX_LOSS_PCT = 5.0  # Максимальный убыток при докупке (%)
SOFT_TRADE_MIN_IMPROVEMENT_PCT = 2.0  # Минимальное улучшение цены (%)
SOFT_TRADE_CHECK_INTERVAL = 1.0  # Интервал проверки (сек)
SOFT_TRADE_TARGET_SUM = 0.98  # Целевая сумма для логирования
SOFT_TRADE_COOLDOWN_AFTER_BUY = 5.0  # Задержка после покупки (сек)
```

### 2. Реализованная логика

**Файл:** [trading/position_manager_soft_trading.py](trading/position_manager_soft_trading.py)

**Основные методы:**
- `_check_entry_opportunities()` - проверка возможностей входа для UP и DOWN
- `_try_buy_side()` - попытка купить конкретную сторону
- `_calculate_safe_amount()` - расчет безопасной суммы с учетом риска
- `_update_probabilities()` - расчет вероятностей и edge (уже было)
- `_log_status()` - логирование статуса с показом средних цен

**Новые переменные класса:**
- `positions_up` - отдельный список UP позиций
- `positions_down` - отдельный список DOWN позиций
- `last_buy_time` - время последней покупки (для cooldown)

### 3. Алгоритм работы

```
Каждую секунду:
│
├─ Проверить cooldown (5 сек с последней покупки)
├─ Получить вероятности UP и DOWN
├─ Рассчитать edge:
│  ├─ edge_UP = (prob_UP - 0.5) * 100 если > 0.5
│  └─ edge_DOWN = (prob_DOWN - 0.5) * 100 если > 0.5
│
├─ Проверить UP:
│  ├─ edge_UP >= 5%?
│  ├─ Цена улучшает среднюю на >= 2%?
│  ├─ Рассчитать безопасную сумму
│  └─ Купить UP
│
└─ Проверить DOWN:
   ├─ edge_DOWN >= 5%?
   ├─ Цена улучшает среднюю на >= 2%?
   ├─ Рассчитать безопасную сумму
   └─ Купить DOWN
```

---

## 🎯 Как запустить

### Шаг 1: Установить стратегию

**Вариант А:** В файле `app/config.py`:
```python
TRADING_STRATEGY = "soft_trading"
```

**Вариант Б:** В файле `.env`:
```bash
TRADING_STRATEGY=soft_trading
```

### Шаг 2: Проверить настройки

```bash
# Проверка импорта и параметров
python test_soft_trading.py
```

Должны увидеть:
```
✅ Импорт успешен
📊 Параметры Soft Trading корректны
🧮 Тесты расчетов пройдены
```

### Шаг 3: Запустить бота

```bash
# Web UI режим
python main.py --mode web

# Или тестовый режим
python main.py --mode test
```

---

## 📊 Что увидите в логах

### При запуске:
```
🚀 Начато управление позициями SOFT TRADING для рынка [ID]
   📊 Без начальной позиции, мониторим рынок
```

### При покупке:
```
🎯 [market_id] ПОКУПКА UP!
   📊 Edge: 6.50% > 5.00%
   💰 Цена: $0.4800
   💵 Сумма: $10.00

💰 Вход в позицию UP на сумму $10.00 по цене $0.4800
✅ Успешный вход в позицию pos_xxx (SOFT_TRADE_ENTRY)
   📊 Позиций UP: 1, DOWN: 0
```

### Периодический статус (каждые 5 сек):
```
📊 [market_id] СТАТУС SOFT TRADING MANAGER (каждые 5 сек)
   📂 Позиций: 3
      1. UP $10.00 по $0.4800 (SOFT_TRADE_ENTRY)
      2. DOWN $10.00 по $0.5200 (SOFT_TRADE_ENTRY)
      3. DOWN $8.00 по $0.4600 (SOFT_TRADE_ENTRY)

   📈 Вероятности: UP=0.550, DOWN=0.520
   💰 Цены: UP=$0.4700, DOWN=$0.4800

   💎 SOFT TRADING:
      UP: 1 поз, avg=$0.4800
      DOWN: 2 поз, avg=$0.4921
      СУММА: $0.9721 ✅ ПРИБЫЛЬ
      До цели (0.98): +0.79%

   ⏰ Активен: True
   🔄 Следующий статус через 5 секунд
```

---

## 🎓 Как читать статус

### Средние цены
```
UP: 2 поз, avg=$0.4714
     ↑        ↑
  кол-во   средняя цена
```

### Целевая сумма
```
СУММА: $0.9721 ✅ ПРИБЫЛЬ
        ↑
avg_UP + avg_DOWN

Если < $1.00 → в прибыли независимо от исхода!
```

### До цели
```
До цели (0.98): +0.79%
                 ↑
Положительное → уже прошли цель
Отрицательное → еще в процессе
```

---

## 🔧 Настройка под себя

### Более агрессивная торговля:
```python
SOFT_TRADE_EDGE_ENTER = 3.0  # Ниже порог
SOFT_TRADE_FIRST_POSITION_USD = 20.0  # Больше позиции
SOFT_TRADE_MIN_IMPROVEMENT_PCT = 1.0  # Меньше требований
```

### Более консервативная торговля:
```python
SOFT_TRADE_EDGE_ENTER = 8.0  # Выше порог
SOFT_TRADE_FIRST_POSITION_USD = 5.0  # Меньше позиции
SOFT_TRADE_MIN_IMPROVEMENT_PCT = 3.0  # Больше требований
SOFT_TRADE_MAX_LOSS_PCT = 3.0  # Меньше риска
```

---

## 📚 Дополнительная документация

- [SOFT_TRADING_STRATEGY.md](SOFT_TRADING_STRATEGY.md) - подробное описание алгоритма с примерами
- [STRATEGIES.md](STRATEGIES.md) - сравнение всех стратегий
- [README.md](README.md) - общая документация проекта

---

## ⚠️ Важно

1. **Тестируйте в SIM_MODE** перед реальной торговлей:
   ```python
   SIM_MODE = True  # в config.py
   ```

2. **Начните с малых сумм**:
   ```python
   SOFT_TRADE_FIRST_POSITION_USD = 5.0  # Начните с $5
   ```

3. **Мониторьте логи** для понимания поведения стратегии

4. **Комиссии важны** - каждая покупка ~2%, учитывайте это

5. **Не гарантируется прибыль** - это трейдинг, всегда есть риски!

---

## 🐛 Если что-то не работает

1. Проверьте импорт:
   ```bash
   python test_strategies.py
   ```

2. Проверьте логи на ошибки:
   ```bash
   python main.py --mode test | grep ERROR
   ```

3. Убедитесь что установлена правильная стратегия:
   ```bash
   python -c "from app import config; print(config.TRADING_STRATEGY)"
   ```

4. Проверьте что вероятности рассчитываются:
   - В логах должны быть `Вероятности: UP=..., DOWN=...`
   - Если нет - проверьте PriceMonitor и probability analyzer

---

**Удачи в soft trading! 🌙💰**

Вопросы? Смотри [SOFT_TRADING_STRATEGY.md](SOFT_TRADING_STRATEGY.md)
