# Code Walkthrough — Signal Generation to Order Placement

## Part 1: TradingAlgoFast.py — Signal Generation

### Location: Line 1032-1036 (BUY signal triggered)

```python
if buy_triggered:
    sig_type[i] = 1  # 1 = BUY
    sig_price[i] = close
    if pos == 2: session_pl += entry_price - close  # if short, realize P/L
    if is_last: pos = 0; entry_price = 0.0; entry_time_num = 0.0  # liquidation
    else: pos = 1; entry_price = close; entry_time_num = times_num[i]  # new long
```

**What this means:**
- `sig_type[i] = 1` → This bar gets a BUY signal
- `is_last` → True if this is a liquidation (closing short), False if new long entry
- `pos = 0` → Position becomes flat (liquidation)
- `pos = 1` → Position becomes long (new entry)

### Location: Line 1088-1092 (SELL signal triggered)

```python
if sell_triggered:
    sig_type[i] = 2  # 2 = SELL
    sig_price[i] = close
    if pos == 1: session_pl += close - entry_price  # if long, realize P/L
    if is_last: pos = 0; entry_price = 0.0; entry_time_num = 0.0  # liquidation
    else: pos = 2; entry_price = close; entry_time_num = times_num[i]  # new short
```

**What this means:**
- `sig_type[i] = 2` → This bar gets a SELL signal
- `is_last` → True if this is a liquidation (closing long), False if new short entry
- `pos = 0` → Position becomes flat (liquidation)
- `pos = 2` → Position becomes short (new entry)

### Location: Line 1238-1245 (Convert to dict)

```python
buy_signals: Dict = {}
sell_signals: Dict = {}
liquidation_timestamps: set = set()
for i in range(n):
    if sig_type[i] == 1:
        buy_signals[times_idx[i]] = sig_price[i]
        if sig_liq[i]: liquidation_timestamps.add(times_idx[i])
    elif sig_type[i] == 2:
        sell_signals[times_idx[i]] = sig_price[i]
        if sig_liq[i]: liquidation_timestamps.add(times_idx[i])
```

**What this means:**
- `buy_signals` = {timestamp: price} for all BUY signals
- `sell_signals` = {timestamp: price} for all SELL signals
- `liquidation_timestamps` = set of timestamps where `is_liquidation=True`

### Location: Line 76-98 (_build_signals_frame)

```python
def _build_signals_frame(data, buy_signals, sell_signals, trading_halted, halt_time, liq_ts):
    df = data.copy()
    df["signal"] = ""
    df["buy_price"] = pd.NA
    df["sell_price"] = pd.NA
    df["is_liquidation"] = False
    
    for ts, price in buy_signals.items():
        if ts in df.index:
            df.at[ts, "signal"] = "BUY"
            df.at[ts, "buy_price"] = float(price)
            if ts in liq_ts:
                df.at[ts, "is_liquidation"] = True
    
    for ts, price in sell_signals.items():
        if ts in df.index:
            df.at[ts, "signal"] = "SELL"
            df.at[ts, "sell_price"] = float(price)
            if ts in liq_ts:
                df.at[ts, "is_liquidation"] = True
```

**Output DataFrame columns:**
- `signal`: "BUY", "SELL", or ""
- `buy_price`: price if BUY, else NaN
- `sell_price`: price if SELL, else NaN
- `is_liquidation`: True if closing a position, False if opening/reversing

---

## Part 2: InteractiveBrokers.py — Order Placement

### Location: Line 869-930 (_run_algo)

```python
def _run_algo(self):
    # ... run the algo ...
    result = run_trading_algo(minute_df, target_date, start_time, end_time, config)
    self._last_result = result
    
    # --- PRE-TRADE POSITION RECONCILIATION ---
    try:
        positions = self._ib.positions()
        for p in positions:
            if p.contract.symbol in ("YM", "MYM"):
                real_pos = int(p.position)
                if real_pos != self._ib_position:
                    log.warning("[PositionSync] PRE-TRADE RECONCILE: _ib_position %d -> %d (CORRECTED)",
                                self._ib_position, real_pos)
                    self._ib_position = real_pos
                break
    except Exception as exc:
        log.error("[PositionSync] Pre-trade reconcile failed: %s", exc)
    
    # --- Scan ALL new signals since last call ---
    new_rows = result[result["signal"].isin(["BUY", "SELL"])]
    if self._last_signal_ts is not None:
        new_rows = new_rows[new_rows.index > self._last_signal_ts]
    
    for ts, last in new_rows.iterrows():
        signal = str(last.get("signal", ""))
        is_liq = bool(last.get("is_liquidation", False))
        pl     = float(last.get("pl", 0.0))
        price  = float(minute_df["Close"].iloc[-1])
        pos    = str(last.get("position", "flat"))
        
        if signal == "BUY":
            if is_liq:
                log.info("[TradingAlgo] LIQUIDATION  price=%.2f  pl=%.1f", price, pl)
                self._place_order("BUY", liquidate=True)
            else:
                if self._pending_order:
                    log.info("[TradingAlgo] BUY skipped — pending order not yet filled")
                    self._last_signal_ts = ts
                    continue
                if self._ib_position > 0:
                    log.info("[TradingAlgo] BUY skipped — already long (ib_pos=%d)", self._ib_position)
                    self._last_signal_ts = ts
                    continue
                log.info("[TradingAlgo] BUY          price=%.2f  pl=%.1f", price, pl)
                self._place_order("BUY")
        
        elif signal == "SELL":
            if is_liq:
                log.info("[TradingAlgo] LIQUIDATION  price=%.2f  pl=%.1f", price, pl)
                self._place_order("SELL", liquidate=True)
            else:
                if self._pending_order:
                    log.info("[TradingAlgo] SELL skipped — pending order not yet filled")
                    self._last_signal_ts = ts
                    continue
                if self._ib_position < 0:
                    log.info("[TradingAlgo] SELL skipped — already short (ib_pos=%d)", self._ib_position)
                    self._last_signal_ts = ts
                    continue
                log.info("[TradingAlgo] SELL         price=%.2f  pl=%.1f", price, pl)
                self._place_order("SELL")
        
        self._last_signal_ts = ts
```

**Key points:**
1. **Pre-trade reconciliation** — Fred checks IB's actual position before every signal
2. **Skip if pending** — If an order is placed but not yet filled, skip new signals
3. **Skip if already in position** — If BUY signal but already long, skip
4. **Liquidation vs Entry** — `is_liquidation=True` means close position, `False` means open/reverse

### Location: Line 1000-1030 (_place_order)

```python
def _place_order(self, action: str, liquidate: bool = False, partial_tp: bool = False):
    tag = "LIQUIDATE" if liquidate else ("PARTIAL_TP" if partial_tp else action)
    if self.dry_run:
        log.info("[ORDER dry_run] %-10s  contract=%s", tag, self._contract.localSymbol)
        return
    
    # Refresh position from IB before calculating qty
    try:
        positions = self._ib.positions()
        for p in positions:
            if p.contract.symbol in ("YM", "MYM"):
                real_pos = int(p.position)
                if real_pos != self._ib_position:
                    log.info("[PositionSync] Pre-order reconcile: _ib_position %d -> %d",
                             self._ib_position, real_pos)
                    self._ib_position = real_pos
                break
    except Exception as exc:
        log.warning("[PositionSync] Could not refresh position before order: %s", exc)
    
    # Calculate quantity
    nc = self.config.num_contracts  # = 2
    if partial_tp:
        qty = max(1, abs(self._ib_position) // 2)
    elif liquidate:
        qty = abs(self._ib_position) if self._ib_position != 0 else nc
    else:
        if action == "BUY":
            qty = nc + max(0, -self._ib_position)   # cover shorts + go long
        else:
            qty = nc + max(0, self._ib_position)    # cover longs + go short
    
    qty = max(1, qty)
    order = MarketOrder(action, totalQuantity=qty)
    order.tif = "DAY"
    exec_contract = self._order_contract or self._contract
    trade = self._ib.placeOrder(exec_contract, order)
    self._pending_order = True
    log.info("[ORDER placed]  %-10s  qty=%d  contract=%s  orderId=%s",
             tag, qty, exec_contract.localSymbol, trade.order.orderId)
```

**Quantity calculation examples:**

| Current Pos | Signal | Liquidate? | Calculation | Qty | Result |
|-------------|--------|------------|-------------|-----|--------|
| 0 (flat) | BUY | No | 2 + max(0, 0) | 2 | Go long 2 |
| 0 (flat) | SELL | No | 2 + max(0, 0) | 2 | Go short 2 |
| +2 (long) | SELL | No | 2 + max(0, 2) | 4 | Reverse: close 2 + open 2 short |
| -2 (short) | BUY | No | 2 + max(0, 2) | 4 | Reverse: close 2 + open 2 long |
| +2 (long) | SELL | Yes | abs(2) | 2 | Close long |
| -2 (short) | BUY | Yes | abs(-2) | 2 | Close short |
| +2 (long) | SELL | Partial TP | abs(2) // 2 | 1 | Close half |
| -2 (short) | BUY | Partial TP | abs(-2) // 2 | 1 | Close half |

---

## Part 3: Partial TP — The Special Case

### Location: Line 932-945 (_run_algo, partial TP section)

```python
# --- Scan ALL new partial TPs since last call ---
new_tp_rows = result[result["partial_tp"] == True]
if self._last_partial_tp_ts is not None:
    new_tp_rows = new_tp_rows[new_tp_rows.index > self._last_partial_tp_ts]

for ts, last in new_tp_rows.iterrows():
    pl  = float(last.get("pl", 0.0))
    pos = str(last.get("position", "flat"))
    price = float(minute_df["Close"].iloc[-1])
    log.info("[TradingAlgo] PARTIAL TP   price=%.2f  pl=%.1f  (1 contract)", price, pl)
    if pos == "long":
        self._place_order("SELL", partial_tp=True)
    elif pos == "short":
        self._place_order("BUY", partial_tp=True)
    self._last_partial_tp_ts = ts
```

**Key insight:**
- If position is "long", partial TP places a SELL order (close half)
- If position is "short", partial TP places a BUY order (close half)
- **The chart doesn't show a signal for partial TP** — it's triggered by profit threshold

---

## Summary: Chart vs IB Monitor

### They SHOULD match:
1. **Entry trades** (flat → long/short)
2. **Reversals** (long → short or short → long)
3. **Liquidations** (close entire position)

### They WON'T match:
1. **Partial TP** — Chart shows no signal, IB monitor shows opposite direction order

### They MUST match on:
1. **Final position** after each trade
2. **Cumulative P/L** at end of session
3. **Number of trades** (excluding partial TPs)

---

## How to Debug Mismatches

### 1. Check the log file

```bash
grep "TradingAlgo" ~/Desktop/IB_Live/logs/fred_ib_*.log
```

Look for:
- `[TradingAlgo] BUY` or `[TradingAlgo] SELL`
- `[TradingAlgo] LIQUIDATION`
- `[TradingAlgo] PARTIAL TP`
- `[ORDER placed]`

### 2. Check position sync messages

```bash
grep "PositionSync" ~/Desktop/IB_Live/logs/fred_ib_*.log
```

Look for:
- `[PositionSync] PRE-TRADE RECONCILE` — means position was corrected
- `[PositionSync] IB fill confirmed` — means fill was received

### 3. Compare chart CSV to IB monitor

```python
# Chart CSV
chart = pd.read_csv("~/Desktop/IB_Live/tracking/YM_tracking_2026-05-12.csv")
trades = chart[chart["signal"] != ""]
print(trades[["time", "signal", "position", "pl"]])

# IB Monitor
python _ib_log_monitor.py --date 2026-05-12
```

If position or P/L diverges, the position tracker is out of sync.
