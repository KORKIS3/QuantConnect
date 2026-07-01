"""Analyze IB P/L discrepancy between chart snapshot and CSV at 11:00 July 1."""
import pandas as pd
import os, pytz, re

_EST = pytz.timezone("US/Eastern")

# 1. Parse all IB execution fills from today's logs
log_dir = os.path.join(os.path.expanduser("~"), "Desktop", "IB_Live", "logs")
log_files = sorted([f for f in os.listdir(log_dir) if "20260701" in f and "DUO158495" in f])
print(f"Log files: {log_files}")
print()

exec_pattern = re.compile(
    r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*execDetails Execution\("
    r".*side='(BOT|SLD)'.*price=([\d.]+).*orderId=(\d+).*cumQty=([\d.]+)"
)

all_fills = []
for lf in log_files:
    path = os.path.join(log_dir, lf)
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            m = exec_pattern.search(line)
            if m:
                time_str, side, price, order_id, cum_qty = m.groups()
                all_fills.append({
                    "time": time_str,
                    "side": side,
                    "price": float(price),
                    "order_id": order_id,
                    "cum_qty": float(cum_qty),
                    "log_file": lf,
                })

print(f"Total execution records: {len(all_fills)}")

# Deduplicate by order_id (keep max cumQty)
fills_by_order = {}
for f in all_fills:
    oid = f["order_id"]
    if oid not in fills_by_order or f["cum_qty"] > fills_by_order[oid]["cum_qty"]:
        fills_by_order[oid] = f

sorted_fills = sorted(fills_by_order.values(), key=lambda x: x["time"])
print(f"Unique fills (by order_id): {len(sorted_fills)}")
print()
print("ALL FILLS FROM IB LOGS:")
for f in sorted_fills:
    side_str = "BOT" if f["side"] == "BOT" else "SLD"
    print(f"  {f['time']}  {side_str} {int(f['cum_qty'])} @ {f['price']:.0f}  (order={f['order_id']}, from={f['log_file']})")

# 2. Now replay these fills using the SAME logic as _build_ib_view_df
print("\n\n=== REPLAY P/L (same logic as _build_ib_view_df) ===")
print("Uses: qty=1 for is_partial_tp, qty=2 otherwise")
print()

# But first - what does _seed_events_from_logs produce?
# It deduplicates by order_id, keeps max cumQty, then iterates in time order.
# Each fill becomes an _order_event. The seeded_count is set to len(_order_events) after seeding.
# Then _build_ib_view_df uses session_events = _order_events[seeded_count:]
# So it should EXCLUDE seeded fills.

# Let's check: the 09:28 session fills vs 09:31 session fills
session1_fills = [f for f in sorted_fills if f["log_file"].endswith("0928.log")]
session2_fills = [f for f in sorted_fills if f["log_file"].endswith("0931.log")]
print(f"Session 1 (09:28) fills: {len(session1_fills)}")
print(f"Session 2 (09:31) fills: {len(session2_fills)}")
print()

# Check for overlapping order IDs
s1_orders = set(f["order_id"] for f in session1_fills)
s2_orders = set(f["order_id"] for f in session2_fills)
overlap = s1_orders & s2_orders
print(f"Overlapping order IDs: {len(overlap)} -> {overlap}")
print()

# 3. Replay ALL fills with _build_ib_view_df logic
print("=== REPLAY ALL FILLS (as _build_ib_view_df would) ===")
ib_position = 0
entry_price = 0.0
realized_pl = 0.0

for f in sorted_fills:
    side = f["side"]
    price = f["price"]
    qty = int(f["cum_qty"])
    # _build_ib_view_df uses qty=1 for partial, qty=2 for full
    # But the LOG fills have the actual cumQty
    # The issue: _build_ib_view_df doesn't use log fills - it uses _order_events
    # which have is_partial_tp set by the placement logic
    # For this analysis, let's just replay with actual qty from logs
    
    if side == "BOT":
        if ib_position < 0:
            close_qty = min(qty, abs(ib_position))
            realized_pl += (entry_price - price) * close_qty
            ib_position += qty
            if ib_position > 0:
                entry_price = price
        elif ib_position == 0:
            ib_position = qty
            entry_price = price
        else:
            ib_position += qty
    else:  # SLD
        if ib_position > 0:
            close_qty = min(qty, ib_position)
            realized_pl += (price - entry_price) * close_qty
            ib_position -= qty
            if ib_position < 0:
                entry_price = price
        elif ib_position == 0:
            ib_position = -qty
            entry_price = price
        else:
            ib_position -= qty
    
    print(f"  {f['time']}  {side} {qty} @ {price:.0f}  -> pos={ib_position:+d}  realized={realized_pl:.0f}  entry={entry_price:.0f}")

print(f"\nFinal: pos={ib_position}, realized_pl={realized_pl:.0f}")

# 4. Now check what _build_ib_view_df actually uses
# It uses _order_events which are set by _on_portfolio_update
# Let's look at the CSV to understand what happened
print("\n\n=== CSV ib_session_pl TRACKING ===")
csv_path = os.path.join(os.path.expanduser("~"), "Desktop", "IB_Live", "tracking",
                        "YM_tracking_DUO158495_2026-07-01_0930.csv")
live = pd.read_csv(csv_path, index_col=0, parse_dates=True)

# Show ib_session_pl at each signal
ib_sigs = live[(live["ib_signal"].notna()) & (live["ib_signal"] != "") & (live["ib_signal"] != "flat")]
print(f"IB signal rows in CSV: {len(ib_sigs)}")
for idx, row in ib_sigs.iterrows():
    sig = row["ib_signal"]
    bp = row.get("ib_buy_price", "")
    sp = row.get("ib_sell_price", "")
    price = bp if sig == "BUY" else sp
    if pd.isna(price):
        price = row["Close"]
    print(f"  {idx}  {sig:<5} @ {float(price):.0f}  ib_session_pl={row['ib_session_pl']:.0f}  ib_realized={row['ib_realized_pl']:.0f}  ib_pl={row['ib_pl']:.0f}")

# 5. Check what the chart's _build_ib_view_df would compute
# It uses is_partial_tp from _order_events. Let's simulate with qty=2 for all (no partial info in CSV)
print("\n\n=== SIMULATED _build_ib_view_df (qty=2 for all, no partial_tp) ===")
ib_position2 = 0
entry_price2 = 0.0
realized_pl2 = 0.0

for idx, row in ib_sigs.iterrows():
    sig = row["ib_signal"]
    bp = row.get("ib_buy_price", "")
    sp = row.get("ib_sell_price", "")
    price = bp if sig == "BUY" else sp
    if pd.isna(price):
        price = row["Close"]
    price = float(price)
    qty = 2  # _build_ib_view_df default for non-partial
    
    if sig == "BUY":
        if ib_position2 < 0:
            close_qty = min(qty, abs(ib_position2))
            realized_pl2 += (entry_price2 - price) * close_qty
            ib_position2 += qty
            if ib_position2 > 0:
                entry_price2 = price
        elif ib_position2 == 0:
            ib_position2 = qty
            entry_price2 = price
        else:
            ib_position2 += qty
    else:  # SELL
        if ib_position2 > 0:
            close_qty = min(qty, ib_position2)
            realized_pl2 += (price - entry_price2) * close_qty
            ib_position2 -= qty
            if ib_position2 < 0:
                entry_price2 = price
        elif ib_position2 == 0:
            ib_position2 = -qty
            entry_price2 = price
        else:
            ib_position2 -= qty
    
    # Unrealized at this bar
    close_bar = float(row["Close"])
    unrealized = 0.0
    if ib_position2 > 0:
        unrealized = (close_bar - entry_price2) * ib_position2
    elif ib_position2 < 0:
        unrealized = (entry_price2 - close_bar) * abs(ib_position2)
    total = realized_pl2 + unrealized
    
    print(f"  {idx}  {sig:<5} @ {price:.0f}  pos={ib_position2:+d}  realized={realized_pl2:.0f}  unreal={unrealized:.0f}  total={total:.0f}")

print(f"\nFinal simulated: pos={ib_position2}, total_pl={realized_pl2:.0f}")
