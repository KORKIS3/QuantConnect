# Signal to Order Flow — How Chart Signals Become IB Orders

## The Flow

```
TradingAlgoFast.py          InteractiveBrokers.py           IB Gateway
(generates signals)    →    (places orders)            →    (executes fills)
                                                             
Chart shows:                Fred does:                      IB Monitor shows:
─────────────────────────────────────────────────────────────────────────────
```

## Step-by-Step Breakdown

### 1. TradingAlgoFast.py — Signal Generation

**Location:** `TradingAlgoFast.py` line ~800-900 in `_run_signals_nb()`

```python
# When price closes above purple ray:
if close > purple_ray and prev_close <= prev_purple_ray:
    signal = SIGNAL_BUY
    is_liquidation = (position == POSITION_SHORT)  # if short, this is a liquidation
    
# When price closes below blue ray:
if close < blue_ray and prev_close >= prev_blue_ray:
    signal = SIGNAL_SELL
    is_liquidation = (position == POSITION_LONG)   # if long, this is a liquidation

# Partial TP (when profit >= 50 pts):
if position == POSITION_LONG and unrealized_pl >= partial_tp_pts:
    partial_tp = True  # close 1 of 2 contracts
elif position == POSITION_SHORT and unrealized_pl >= partial_tp_pts:
    partial_tp = True  # close 1 of 2 contracts
```

**Output:** DataFrame with columns:
- `signal`: "BUY", "SELL", or ""
- `is_liquidation`: True/False
- `partial_tp`: True/False
- `position`: "long", "short", "flat"

---

### 2. InteractiveBrokers.py — Order Placement

**Location:** `InteractiveBrokers.py` line ~869-930 in `_run_algo()`

#### A. Regular BUY Signal (not liquidation)

```python
if signal == "BUY":
    if is_liq:
        # This is a liquidation (closing short position)
        self._place_order("BUY", liquidate=True)
    else:
        # This is a new long entry or reversal
        self._place_order("BUY")
```

#### B. Regular SELL Signal (not liquidation)

```python
elif signal == "SELL":
    if is_liq:
        # This is a liquidation (closing long position)
        self._place_order("SELL", liquidate=True)
    else:
        # This is a new short entry or reversal
        self._place_order("SELL")
```

#### C. Partial TP

```python
if partial_tp:
    if pos == "long":
        self._place_order("SELL", partial_tp=True)  # close 1 of 2
    elif pos == "short":
        self._place_order("BUY", partial_tp=True)   # close 1 of 2
```

---

### 3. InteractiveBrokers.py — Order Quantity Calculation

**Location:** `InteractiveBrokers.py` line ~1000-1030 in `_place_order()`

```python
def _place_order(self, action: str, liquidate: bool = False, partial_tp: bool = False):
    nc = self.config.num_contracts  # = 2
    
    if partial_tp:
        # Close half the position
        qty = max(1, abs(self._ib_position) // 2)  # if pos=2, qty=1
        
    elif liquidate:
        # Close entire position
        qty = abs(self._ib_position) if self._ib_position != 0 else nc
        
    else:
        # Entry or reversal
        if action == "BUY":
            qty = nc + max(0, -self._ib_position)   # cover shorts + go long
        else:
            qty = nc + max(0, self._ib_position)    # cover longs + go short
    
    order = MarketOrder(action, totalQuantity=qty)
    trade = self._ib.placeOrder(exec_contract, order)
```

---

## Examples — Chart Signal → IB Order

### Example 1: First Trade (Flat → Short)

**Chart shows:**
- 09:45 SELL @ 49759 → position=short

**What Fred does:**
```python
signal = "SELL"
is_liquidation = False  # was flat
_ib_position = 0        # flat

# _place_order("SELL", liquidate=False)
qty = 2 + max(0, 0) = 2
order = MarketOrder("SELL", 2)
```

**IB Monitor shows:**
- 09:45 SELL 2 @ 49759

✓ **MATCH**

---

### Example 2: Partial TP (Short → Less Short)

**Chart shows:**
- 10:40 SELL @ 49852 (liquidation) → position=flat
- Note: This is labeled "liquidation" but it's actually partial TP

**What Fred does:**
```python
partial_tp = True       # profit >= 50 pts
position = "short"
_ib_position = -2

# _place_order("BUY", partial_tp=True)
qty = max(1, abs(-2) // 2) = 1
order = MarketOrder("BUY", 1)
```

**IB Monitor shows:**
- 10:40 BUY 1 @ 49852

❌ **MISMATCH** — Chart says "SELL" but Fred places "BUY"

**WHY:** Partial TP closes half the position. If you're short, you BUY to close. The chart shows the SIGNAL that triggered it (SELL crossed a line), but the ORDER is the opposite direction.

---

### Example 3: Reversal (Short → Long)

**Chart shows:**
- 11:47 BUY @ 49745 → position=long

**What Fred does:**
```python
signal = "BUY"
is_liquidation = False  # this is a reversal, not a liquidation
_ib_position = -2       # currently short

# _place_order("BUY", liquidate=False)
qty = 2 + max(0, -(-2)) = 2 + 2 = 4
order = MarketOrder("BUY", 4)
```

**IB Monitor shows:**
- 11:47 BUY 4 @ 49745

✓ **MATCH** — BUY 4 = close 2 short + open 2 long

---

### Example 4: Session End Flatten (Long → Flat)

**Chart shows:**
- 16:54 SELL @ 49744 (liquidation) → position=flat

**What Fred does:**
```python
# _on_session_end() calls:
if self._ib_position > 0:
    self._place_order("SELL", liquidate=True)

_ib_position = 2  # long

# _place_order("SELL", liquidate=True)
qty = abs(2) = 2
order = MarketOrder("SELL", 2)
```

**IB Monitor shows:**
- 16:54 SELL 2 @ 49744

✓ **MATCH**

---

## The Key Insight

**The chart shows SIGNALS (what line was crossed).**
**The IB monitor shows ORDERS (what Fred actually placed).**

### When They Match:
- Entry trades (flat → long/short)
- Reversals (long → short or short → long)
- Session end flatten

### When They DON'T Match:
- **Partial TP:** Chart shows the signal direction (SELL if short), but Fred places the OPPOSITE order (BUY to close half)

---

## Why May 8th Was Different

On May 8th, the mismatch wasn't about signal vs order direction. It was about **quantity**:

**What should have happened:**
- Chart: SELL @ 49716 → position=short (2 contracts)
- Fred: SELL 2

**What actually happened:**
- Chart: SELL @ 49716 → position=short (2 contracts)
- Fred: SELL 4 (because `_ib_position` was wrong)

The **direction** was correct, but the **quantity** was wrong because Fred's position tracker was out of sync.

---

## How to Verify They Match

### 1. Check the position after each trade

**Chart CSV:**
```
time,signal,position,pl
09:45,SELL,short,0.0
10:40,SELL,flat,75.0    ← partial TP
11:47,BUY,long,186.0
```

**IB Monitor:**
```
09:45 SELL 2 @ 49759  → pos = -2 (short)
10:40 BUY 1 @ 49852   → pos = -1 (still short, but half closed)
11:47 BUY 4 @ 49745   → pos = +2 (long)
```

Wait, that's wrong! After partial TP, position should be -1, not flat.

**This reveals a bug in the chart:** Partial TP shows position=flat, but it should show position=short (1 contract).

### 2. Check the P/L matches

If Fred's orders match the chart signals, the P/L should be identical (within a few points for slippage).

**Chart:** +231 pts
**IB Monitor:** Should be +231 pts (if position tracking is correct)

---

## Action Items for Monday

1. **Watch the first trade carefully** — verify IB monitor shows the same direction and quantity as the chart

2. **After partial TP** — verify position is half, not flat

3. **After reversal** — verify quantity is 4 (close 2 + open 2)

4. **At session end** — verify Fred flattens to 0 contracts

If any of these don't match, the position tracker is out of sync and needs immediate attention.
