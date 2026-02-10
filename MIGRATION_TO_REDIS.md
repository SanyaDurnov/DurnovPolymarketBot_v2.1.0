# Migration Guide: File-Based Cache → Redis

**Current Status:** File-based caching (simple, no dependencies)
**Future Migration:** Redis-based caching (scalable, multi-bot ready)

---

## Why Migrate to Redis?

Migrate when you need:
- ✅ **Multiple bots** sharing the same market data
- ✅ **No race conditions** (atomic operations)
- ✅ **Distributed deployment** (bots on different machines)
- ✅ **Position coordination** (prevent duplicate trades)
- ✅ **Better performance** (in-memory cache)

**Don't migrate if:**
- You're running a single bot
- File-based cache works fine for your needs
- You want to keep things simple

---

## Migration Steps

### Phase 1: Prepare (5-10 minutes)

#### 1. Install Redis

**macOS:**
```bash
brew install redis
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt update
sudo apt install redis-server
```

**Verify installation:**
```bash
redis-server --version
# Should output: Redis server v=7.x.x
```

#### 2. Start Redis Server

**macOS:**
```bash
# Start Redis (runs in foreground)
redis-server

# OR start as background service
brew services start redis
```

**Linux:**
```bash
# Start Redis service
sudo systemctl start redis-server

# Enable auto-start on boot
sudo systemctl enable redis-server
```

**Verify Redis is running:**
```bash
redis-cli ping
# Should output: PONG
```

#### 3. Install Python Redis Client

```bash
pip install redis
```

---

### Phase 2: Migrate (1 minute!)

#### Change ONE Line of Code

**File:** `services/market_cache.py`

**Line ~150** (in `get_market_cache()` function):

```python
def get_market_cache() -> MarketCache:
    # BEFORE (file-based):
    return FileMarketCache("data/filtered_markets.json")

    # AFTER (Redis):
    return RedisMarketCache("redis://localhost:6379")
```

**That's it!** No other code changes needed.

---

### Phase 3: Test (5 minutes)

#### 1. Stop All Services

```bash
# Stop market service (Ctrl+C in terminal)
# Stop trading bot (Ctrl+C in terminal)
```

#### 2. Clear Old Cache (Optional)

```bash
# Backup existing file cache
cp data/filtered_markets.json data/filtered_markets.json.backup

# Optional: clear Redis (if you had old test data)
redis-cli FLUSHDB
```

#### 3. Restart Services

```bash
# Terminal 1: Start market service
python market_service.py

# Terminal 2: Start trading bot
python main.py
```

#### 4. Verify Redis Cache

**Check cached markets:**
```bash
# Get number of markets
redis-cli GET polymarket:filtered_markets | jq '. | length'

# Get last update time
redis-cli HGET polymarket:markets_meta last_update
```

**Expected output:**
```
100  # (or however many markets you have)
2026-02-08T12:34:56.789012  # Recent timestamp
```

---

### Phase 4: Monitor (Ongoing)

#### Check Redis Status

```bash
# Redis info
redis-cli INFO

# Monitor commands in real-time
redis-cli MONITOR

# Check memory usage
redis-cli INFO memory
```

#### Market Service Logs

Watch for these messages:
```
✅ Connected to Redis at redis://localhost:6379
✅ Cached 150 markets to Redis
```

---

## Rollback Plan

If Redis causes issues, rollback is easy:

### 1. Stop Services

```bash
# Ctrl+C in both terminals
```

### 2. Revert Code Change

**File:** `services/market_cache.py`

```python
def get_market_cache() -> MarketCache:
    # Rollback to file-based
    return FileMarketCache("data/filtered_markets.json")
```

### 3. Restart Services

```bash
python market_service.py
python main.py
```

**Done!** You're back to file-based caching.

---

## Advanced: Redis Configuration

### Custom Redis URL

If Redis is on a different machine or port:

```python
# Remote Redis
return RedisMarketCache("redis://your-server.com:6379")

# Password-protected Redis
return RedisMarketCache("redis://:password@localhost:6379")

# Different database number
return RedisMarketCache("redis://localhost:6379/1")
```

### Redis Persistence

**Make sure data survives restarts:**

Edit `/usr/local/etc/redis.conf` (macOS) or `/etc/redis/redis.conf` (Linux):

```conf
# Enable RDB snapshots (every 60 seconds if at least 1 change)
save 60 1

# Enable AOF (append-only file) for durability
appendonly yes
appendfsync everysec
```

Restart Redis:
```bash
brew services restart redis  # macOS
sudo systemctl restart redis-server  # Linux
```

---

## Multi-Bot Setup (After Redis Migration)

Once on Redis, you can run multiple bots easily:

### Terminal Layout

```
Terminal 1: Market Service (fetches markets)
Terminal 2: Redis Server (cache)
Terminal 3: Bot 1 (trading)
Terminal 4: Bot 2 (trading)
Terminal 5: Bot 3 (trading)
...
```

### Start Multiple Bots

```bash
# Each bot reads from same Redis cache
python main.py --bot-id bot_1
python main.py --bot-id bot_2
python main.py --bot-id bot_3
```

**All bots share the same market data from Redis cache!**

---

## Position Coordination (Future Feature)

After migrating to Redis, you can add position locking to prevent duplicate trades:

```python
# In services/market_cache.py (RedisMarketCache class)

def lock_market(self, market_id: str, bot_id: str, timeout: int = 300) -> bool:
    """
    Try to acquire lock on market for this bot.

    Args:
        market_id: Market to lock
        bot_id: ID of bot requesting lock
        timeout: Lock expires after N seconds

    Returns:
        True if lock acquired, False if already locked
    """
    lock_key = f"lock:market:{market_id}"
    return self.redis.set(lock_key, bot_id, nx=True, ex=timeout)

def unlock_market(self, market_id: str, bot_id: str) -> None:
    """Release lock on market."""
    lock_key = f"lock:market:{market_id}"
    # Only unlock if this bot owns the lock
    script = """
    if redis.call("get", KEYS[1]) == ARGV[1] then
        return redis.call("del", KEYS[1])
    else
        return 0
    end
    """
    self.redis.eval(script, 1, lock_key, bot_id)
```

**Usage in bot:**
```python
cache = get_market_cache()

if cache.lock_market(market_id, "bot_1"):
    # This bot got the lock - safe to trade
    take_position(market_id)
    cache.unlock_market(market_id, "bot_1")
else:
    # Another bot is already trading this market
    logger.info(f"Market {market_id} locked by another bot")
```

---

## Troubleshooting

### Redis not connecting

**Error:** `ConnectionError: Error 111 connecting to localhost:6379`

**Solution:**
```bash
# Check if Redis is running
redis-cli ping

# If not running, start it
redis-server  # macOS/Linux
```

### Import error

**Error:** `ImportError: No module named 'redis'`

**Solution:**
```bash
pip install redis
```

### Memory issues

**Error:** Redis using too much memory

**Solution:**
```bash
# Check memory usage
redis-cli INFO memory

# Set max memory limit (e.g., 100MB)
redis-cli CONFIG SET maxmemory 100mb
redis-cli CONFIG SET maxmemory-policy allkeys-lru
```

---

## Comparison: File vs Redis

| Feature | File-Based | Redis |
|---------|-----------|-------|
| **Setup time** | 0 minutes | 10 minutes |
| **Dependencies** | None | Redis server + client |
| **Multiple bots** | ⚠️ Race conditions | ✅ Safe |
| **Performance** | Fast | Very fast |
| **Debugging** | Easy (open JSON file) | Need Redis CLI |
| **Persistence** | Automatic | Need to configure |
| **Scalability** | Single machine | Multi-machine |
| **Complexity** | Simple | Moderate |

---

## When to Migrate?

**Migrate now if:**
- You plan to run 2+ bots soon
- You're deploying to production
- You want best practices from day 1

**Migrate later if:**
- You're still testing/developing
- Running a single bot works fine
- You prefer simplicity

**The beauty of our abstraction layer:** You can decide anytime. Migration is literally one line of code!

---

## Summary

**Migration is a 3-step process:**

1. **Install Redis** (5 min)
   ```bash
   brew install redis  # macOS
   redis-server
   ```

2. **Install Python client** (1 min)
   ```bash
   pip install redis
   ```

3. **Change one line** (10 seconds)
   ```python
   # services/market_cache.py
   return RedisMarketCache("redis://localhost:6379")
   ```

**That's it!** Your entire system now uses Redis with zero other code changes.

---

## Need Help?

**Check Redis connection:**
```bash
redis-cli ping  # Should return: PONG
```

**View cached data:**
```bash
redis-cli GET polymarket:filtered_markets
```

**Monitor live:**
```bash
redis-cli MONITOR
```

**Redis logs:**
```bash
# macOS
tail -f /usr/local/var/log/redis.log

# Linux
sudo journalctl -u redis-server -f
```

Good luck! 🚀
