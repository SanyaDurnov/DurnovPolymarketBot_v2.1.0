# Position Entry Decision Logic

## Overview

The Position Manager makes trading decisions every **5 seconds** based on mathematical probabilities, market prices, and position state.

---

## 📊 Decision Types

### 1. **Opposite Entry** (Hedging)

**Trigger:** When you have 1 position, bot considers entering opposite side

**Conditions (ALL must be met):**
```
✅ Number of positions == 1
✅ Opposite probability >= 0.35 (MATH_PROB_FOR_OPPOSITE)
✅ Opposite price < 0.35 (PRICE_ENTRY_FOR_OPPOSITE)
```

**Example from logs (16:20:00 - ENTRY EXECUTED):**
```
🎯 [1345040] УСЛОВИЯ ДЛЯ ВХОДА В DOWN ВЫПОЛНЕНЫ!
   📊 Вероятность: 0.815 > 0.35 ✓
   💰 Цена: 0.3200 < 0.35 ✓
   💵 Сумма входа: $56.47
   🎲 Гарантированная прибыль: обеспечена хеджированием

Result: Position created (OPPOSITE_ENTRY)
```

**Example from logs (16:19:56 - ENTRY REJECTED):**
```
📊 [1351449] СТАТУС POSITION MANAGER
   🎯 Opposite entry (UP): ГОТОВ
      • вероятность 0.383 >= 0.35 ✓
      • цена 0.9100 >= 0.35 ❌

Why NOT buying: Price 0.91 is TOO HIGH (must be < 0.35)
```

---

### 2. **Additional Entry** (Price Averaging)

**Trigger:** When you have 2 positions, bot considers adding to initial position

**Conditions (ALL must be met):**
```
✅ Number of positions == 2
✅ Price dropped >= 15% (PERCENT_FOR_PRICE_REDUCE)
✅ Calculated amount > 0
```

**Example from logs (16:20:05):**
```
📊 [1345040] СТАТУС POSITION MANAGER
   📈 Additional entry (UP): ГОТОВ
      • снижение цены: ⬆️ 36.0% ≥ 15.0% ✓

Current positions:
   1. UP $100.00 @ $0.4707 (FIRST_ENTRY)
   2. DOWN $56.47 @ $0.3200 (OPPOSITE_ENTRY)

Current price: UP=$0.6400 (increased 36% from $0.4707)
Why NOT buying: Price INCREASED (not decreased!)
```

**Note:** The log shows "⬆️ 36.0%" which means price went UP, not down. Additional entry only triggers when price DROPS.

---

## 📈 All Parameter Values

### Probability Calculations (from REACH CALC logs)

**Example:**
```
REACH CALC:
  current_price=70852.31       # Current BTC price
  target=71170.47              # Price to beat (target for UP to win)
  reach_prob_raw=0.1846        # Raw probability of reaching target
  price_move_pct=0.0045        # Required price move (0.45%)
  z_score=0.8981               # Statistical z-score for probability
  reach_prob_up=0.1846         # Probability UP wins (18.46%)
  reach_prob_down=0.8154       # Probability DOWN wins (81.54%)
  math_prob_opposite=0.1846    # Used for opposite entry decision

VOL (Volatility):
  hybrid=0.50%                 # Hybrid volatility (ATR + current)
  atr=0.10%                    # Average True Range volatility
  current=0.51%                # Current price volatility
```

### Market Prices (from position manager status)

```
💰 Цены: UP=$0.6400, DOWN=$0.3800

Meaning:
- Buying UP shares costs $0.64 each
- Buying DOWN shares costs $0.38 each
- UP + DOWN ≈ $1.00 (market equilibrium)
```

---

## 🎯 Configuration Constants

From `app/config.py`:

| Parameter | Value | Meaning |
|-----------|-------|---------|
| `MATH_PROB_FOR_OPPOSITE` | 0.35 | Min probability to enter opposite side |
| `PRICE_ENTRY_FOR_OPPOSITE` | 0.35 | Max price to enter opposite side ($0.35) |
| `PERCENT_FOR_PRICE_REDUCE` | 15% | Min price drop for additional entry |
| `W1_PROFIT_PCT` | 5% | Target profit from hedging |

---

## 🔄 Status Updates (Every 5 Seconds)

**Full example:**
```
📊 [1345040] СТАТУС POSITION MANAGER (каждые 5 сек)
   📂 Позиций: 2
      1. UP $100.00 по $0.4707 (FIRST_ENTRY)
      2. DOWN $56.47 по $0.3200 (OPPOSITE_ENTRY)
   📈 Вероятности: UP=0.185, DOWN=0.815
   💰 Цены: UP=$0.6400, DOWN=$0.3800
   📈 Additional entry (UP): ГОТОВ
      • снижение цены: ⬆️ 36.0% ≥ 15.0%
   ⏰ Активен: True
```

**Reading this:**
- 2 positions (hedged)
- UP probability is 18.5%, DOWN is 81.5%
- Current prices: UP=$0.64, DOWN=$0.38
- Additional entry is READY (but price went UP, not down)
- Manager is active and checking conditions

---

## ⏰ Why Bot Checks But Doesn't Buy

**Every 5 seconds, bot checks all conditions:**

1. **Opposite Entry check:**
   - IF only 1 position exists
   - AND opposite probability >= 0.35
   - AND opposite price < 0.35
   - THEN enter opposite position
   - ELSE skip (log shows "ГОТОВ" but conditions not fully met)

2. **Additional Entry check:**
   - IF exactly 2 positions exist
   - AND price dropped >= 15% from initial entry
   - THEN add to initial position
   - ELSE skip

**Common reasons for NOT buying:**
- ❌ Opposite price too high (e.g., 0.91 > 0.35)
- ❌ Price increased instead of decreased
- ❌ Wrong number of positions (e.g., 0 or 3)
- ❌ Probability too low (e.g., 0.20 < 0.35)

---

## 📋 How to Interpret Logs

### ✅ Entry WILL happen:
```
🎯 [MARKET_ID] УСЛОВИЯ ДЛЯ ВХОДА В [SIDE] ВЫПОЛНЕНЫ!
   📊 Вероятность: X.XXX > 0.35 ✓
   💰 Цена: X.XXXX < 0.35 ✓
   💵 Сумма входа: $XX.XX
```

### ❌ Entry WILL NOT happen (waiting):
```
📊 [MARKET_ID] СТАТУС POSITION MANAGER
   🎯 Opposite entry ([SIDE]): ГОТОВ
      • вероятность 0.XXX >= 0.35 ✓
      • цена 0.XXXX >= 0.35 ❌  <-- Price too high!
```

The bot shows "ГОТОВ" (ready) when probability is met, but **won't execute** until **both** probability AND price conditions are satisfied.

---

## 🧪 Testing Entry Logic

To see ALL decision details including WHY bot skips entries:

```bash
# Set LOG_LEVEL to DEBUG in app/config.py
LOG_LEVEL = "DEBUG"

# Restart bot
./start_services.sh restart

# Watch detailed logs
tail -f logs/trading_bot.log | grep -E "Пропуск|opposite entry|additional entry|УСЛОВИЯ"
```

This will show logs like:
```
[DEBUG] [1345040] Пропуск opposite entry DOWN: цена 0.4500 >= 0.35
[DEBUG] [1351449] Пропуск opposite entry UP: цена 0.9100 >= 0.35
[INFO]  🎯 [1345040] УСЛОВИЯ ДЛЯ ВХОДА В DOWN ВЫПОЛНЕНЫ!
```

---

## Summary

**The bot continuously monitors and decides:**
- ✅ **Every 5 seconds**: Check probabilities, prices, positions
- ✅ **Shows "ГОТОВ"**: When probability condition is met
- ✅ **Actually BUYS**: Only when ALL conditions are met (probability + price + position count)
- ❌ **Waits patiently**: Until price drops to acceptable level (< $0.35 for opposite entry)

**Most common reason for NOT buying: Price is too high!**

Example: Opposite entry to UP at $0.91 won't execute because $0.91 >> $0.35 (too expensive, low profit potential)
