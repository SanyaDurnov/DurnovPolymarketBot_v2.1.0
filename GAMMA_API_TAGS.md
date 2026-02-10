# Polymarket Gamma API Tags Reference

## Available Crypto-Related Tags

From `https://gamma-api.polymarket.com/tags`:

| Tag ID | Tag Name | Description |
|--------|----------|-------------|
| **744** | **cryptocurrency** | Main crypto tag (USE THIS) ✅ |
| 102115 | Bitcoin Dominance | Bitcoin dominance markets |
| 686 | cryptozoo | CryptoZoo related |
| 1256 | crypto: the game | Crypto game related |

## Configuration

### In [app/config.py](app/config.py)

```python
# Fixed: Use "cryptocurrency" not "crypto"
GAMMA_API_TAG = "cryptocurrency"  # tag_id: 744

# NEW: Configurable update interval
MARKETS_UPDATE_INTERVAL_MINUTES = 15  # Update cache every N minutes
```

### In [app/app_config.py](app/app_config.py)

Now reads from main config.py automatically:
```python
gamma_api_tag = getattr(main_config, 'GAMMA_API_TAG', "cryptocurrency")
markets_update_interval_minutes = getattr(main_config, 'MARKETS_UPDATE_INTERVAL_MINUTES', 15)
```

## Testing the Fix

### 1. Check Tag Resolution

```bash
# In logs, you should see:
# "Найден тег 'cryptocurrency' с ID: 744"
```

### 2. Verify Filtering Works

Before fix:
```
Начинаем загрузку всех рынков с Gamma API...
Загружено 10000+ рынков  # ❌ Downloads everything!
```

After fix:
```
Начинаем загрузку всех рынков с Gamma API...
Запрос к Gamma API: params={'tag_id': 744, 'active': True, ...}
Загружено ~100-200 рынков  # ✅ Only crypto markets!
```

## Alternative: Use Tag ID Directly

If tag name lookup fails, you can use tag_id directly:

### In [app/config.py](app/config.py)
```python
# Option 1: Use tag name (automatic ID lookup)
GAMMA_API_TAG = "cryptocurrency"

# Option 2: Use tag_id directly (faster, no lookup)
# Set in app_config.py:
# gamma_api_tag_id = 744
```

## Update Interval Options

You can now change update interval in [app/config.py](app/config.py):

```python
MARKETS_UPDATE_INTERVAL_MINUTES = 15  # Every 15 minutes (default)
MARKETS_UPDATE_INTERVAL_MINUTES = 5   # Every 5 minutes (more frequent)
MARKETS_UPDATE_INTERVAL_MINUTES = 30  # Every 30 minutes (less API load)
MARKETS_UPDATE_INTERVAL_MINUTES = 60  # Every hour (minimal load)
```

**Recommendation:**
- **Development/Active Trading**: 5-10 minutes
- **Normal Operation**: 15 minutes (default)
- **Low Activity**: 30-60 minutes

## All Available Tags (First 20)

```
ID: 671   | jto
ID: 101592| Tom Aspinal
ID: 101115| Preston
ID: 746   | detroit pistons
ID: 744   | cryptocurrency ← YOU WANT THIS ONE
ID: 1493  | spider-man
ID: 1564  | facebook
ID: 335   | peace deals
...
```

Total tags available: ~300

## API Endpoints

### Get All Tags
```bash
curl "https://gamma-api.polymarket.com/tags?limit=1000"
```

### Search Tags
```bash
curl "https://gamma-api.polymarket.com/tags?search=crypto&limit=100"
```

### Get Markets by Tag
```bash
curl "https://gamma-api.polymarket.com/markets?tag_id=744&active=true&limit=100"
```

## Summary of Changes

✅ **Fixed tag name:** "crypto" → "cryptocurrency"
✅ **Added config:** MARKETS_UPDATE_INTERVAL_MINUTES
✅ **Centralized:** app_config.py now reads from config.py
✅ **Documented:** All crypto-related tags

Now your bot will only download crypto markets instead of all 10,000+ markets!
