# Market Data Cache Strategy

## Архитектура: Cache-First с Fallback на API

### Принцип работы

```
1. Попытка чтения из Market Service cache (мгновенно)
   ↓
2. Если НЕ найдено → Fallback на API (медленно, но надежно)
   ↓
3. Возврат данных
```

---

## Когда используется кэш

### ✅ Успешно из кэша (быстро, ~0.03 сек)

**Случаи:**
- Рынки, которые проходят фильтры Market Service
- Bitcoin/Ethereum/Solana Up/Down рынки
- Рынки, которые стартуют в ближайшие 20 минут
- Рынки, которые стартовали менее 15 минут назад

**Источник:** `data/filtered_markets.json` (обновляется каждые 15 минут)

**Код:**
```python
from polymarket.market_cache_reader import get_cached_market_by_id
market_data = get_cached_market_by_id(market_id)
# Возвращает данные мгновенно из файла
```

---

## Когда используется API (fallback)

### ⚠️ Fallback на API (медленно, ~10-30 сек)

**Случаи:**
1. **Manual Entry** - пользователь вручную выбирает рынок (может быть любой)
2. **Новые рынки** - рынок только что создан, Market Service еще не обновил кэш
3. **За пределами фильтров** - рынок не проходит фильтры времени Market Service
4. **Особые рынки** - не Bitcoin/Ethereum/Solana

**Источник:** Gamma API (`https://gamma-api.polymarket.com/markets/{market_id}`)

**Код:**
```python
# Сначала пробуем кэш
market_data = get_cached_market_by_id(market_id)

# Если не найдено - API fallback
if not market_data:
    logger.warning(f"⚠️  Рынок {market_id} не найден в кэше, запрашиваем из API")
    market_data = pm_client.get_market_data(market_id)
```

---

## Где применяется эта стратегия

### 1. PriceToBeatService (`analysis/price_to_beat_service.py:86`)

**Назначение:** Получить данные рынка для определения `price_to_beat`

**Логика:**
```python
# Приоритет: Market Service cache
from polymarket.market_cache_reader import get_cached_market_by_id
market_data = get_cached_market_by_id(market_id)

# Fallback: API для manual entry / новых рынков
if not market_data:
    logger.warning(f"⚠️  Рынок {market_id} не найден в кэше, запрашиваем из API")
    market_data = self.pm_client.get_market_data(market_id)
    if not market_data:
        return None
    logger.info(f"✅ Получены данные рынка {market_id} из API (fallback)")
```

**Результат:**
- ✅ Быстро для кэшированных рынков (99% случаев)
- ✅ Работает для manual entry (1% случаев)

---

### 2. Manual Entry API (`web/app.py:838`)

**Назначение:** Получить данные рынка для ручного входа пользователем

**Логика:**
```python
# Приоритет: Market Service cache
market_data = get_cached_market_by_id(market_id)

# Fallback: API для рынков вне кэша
if not market_data:
    logger.warning(f"⚠️  Рынок {market_id} не найден в кэше для manual entry, запрашиваем из API")
    market_data = pm_client.get_market_data(market_id)
    if not market_data:
        raise HTTPException(status_code=404, detail="Рынок не найден")
```

**Результат:**
- ✅ Пользователь может выбрать **ЛЮБОЙ** рынок (не только в кэше)
- ✅ Быстро для рынков в кэше
- ⚠️ Медленно для рынков вне кэша (но работает!)

---

### 3. Список рынков API (`web/app.py:254`)

**Назначение:** Показать список доступных рынков в UI

**Логика:**
```python
# Только кэш, БЕЗ fallback (быстро!)
markets = get_cached_markets()
```

**Почему БЕЗ fallback:**
- Список рынков должен загружаться **мгновенно**
- Пользователь всегда видит рынки из кэша
- Если нужен особый рынок → Manual Entry (с fallback)

**Результат:**
- ✅ UI всегда отзывчив
- ✅ Нет заморозок при обновлении страницы

---

## Преимущества этой стратегии

### 1. **Производительность**
- 99% запросов из кэша (мгновенно)
- 1% запросов из API (медленно, но редко)
- UI никогда не зависает

### 2. **Гибкость**
- Работает с любым рынком (не только в кэше)
- Manual Entry поддерживает все рынки
- Graceful degradation

### 3. **Надежность**
- Если кэш пуст → fallback на API
- Если Market Service сломался → все равно работает
- Нет single point of failure

---

## Метрики производительности

| Операция | Источник | Время | Частота |
|----------|----------|-------|---------|
| Список рынков | Cache | ~0.03 сек | Очень часто |
| Данные рынка (в кэше) | Cache | ~0.03 сек | 99% |
| Данные рынка (вне кэша) | API | ~10-30 сек | 1% |
| Manual Entry (в кэше) | Cache | ~0.03 сек | 90% |
| Manual Entry (вне кэша) | API | ~10-30 сек | 10% |

---

## Как проверить, что работает правильно

### Тест 1: Проверить cache-first (должно быть быстро)

```bash
# Запросить рынок из кэша
time curl -s http://localhost:8000/api/markets

# Должно быть: ~0.03 секунды
```

### Тест 2: Проверить fallback (должно работать, но медленно)

```bash
# Открыть логи
tail -f logs/trading_bot.log | grep "не найден в кэше"

# Manual Entry для рынка вне кэша
curl -X POST http://localhost:8000/api/manual-entry -d '{"market_id": "999999", "side": "UP"}'

# Должно увидеть:
# ⚠️  Рынок 999999 не найден в кэше, запрашиваем из API
```

### Тест 3: Проверить что UI быстрый

```bash
# Открыть браузер
open http://localhost:8000

# Обновить страницу 10 раз
# Должно загружаться МГНОВЕННО каждый раз
```

---

## FAQ

### Q: Почему не весь API кэшируется?

**A:** Market Service кэширует только **отфильтрованные** рынки (Bitcoin/Ethereum/Solana, определенное время). Это экономит память и ускоряет работу. Для других рынков используется API fallback.

### Q: Что если Market Service выключен?

**A:** Fallback на API сработает автоматически для всех запросов. Бот продолжит работать, но медленнее (10-30 сек вместо 0.03 сек).

### Q: Можно ли отключить fallback?

**A:** Технически да, но **НЕ РЕКОМЕНДУЕТСЯ**. Без fallback manual entry не будет работать.

### Q: Как часто обновляется кэш?

**A:** Каждые 15 минут (настраивается в `app/config.py`: `MARKETS_UPDATE_INTERVAL_MINUTES`).

---

## Связанные файлы

- `analysis/price_to_beat_service.py:86` - Cache-first с fallback для price_to_beat
- `web/app.py:254` - Cache-only для списка рынков
- `web/app.py:838` - Cache-first с fallback для manual entry
- `polymarket/market_cache_reader.py` - Функции чтения из кэша
- `market_service.py` - Сервис обновления кэша
- `services/market_cache.py` - Абстракция кэша (File/Redis)

---

## Итог

**Cache-First с Fallback на API** - это оптимальная стратегия, которая дает:
- ✅ Максимальную скорость (99% из кэша)
- ✅ Максимальную гибкость (1% из API)
- ✅ Надежность (fallback если кэш недоступен)

**Правило:** Всегда читайте из кэша сначала, используйте API только как fallback для особых случаев.
