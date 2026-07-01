"""Compare today's live session signals vs backtest signals."""
import pandas as pd
import os, pytz
from TradingAlgoFast import AlgoConfig, run_trading_algo_fast

_EST = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")

# --- LIVE SESSION ---
live_path = os.path.expanduser("~/Desktop/IB_Live/tracking/YM_tracking_DUO158495_2026-06-30_0930.csv")
live = pd.read_csv(live_path, index_col=0, parse_dates=True)

live_signals = live[live["signal"].notna() & (live["signal"] != "")]
print("=== LIVE SESSION SIGNALS ===")
print(f"Total signals: {len(live_signals)}")
print(f"Final session_pl: {live['session_pl'].iloc[-1]:.1f} pts")
print()
for idx, row in live_signals.iterrows():
    sig = row["signal"]
    bp = row.get("buy_price", "")
    sp = row.get("sell_price", "")
    price = bp if sig == "buy" else sp
    pos = row.get("position", "")
    spl = row.get("session_pl", 0)
    liq = row.get("is_liquidation", False)
    ptp = row.get("partial_tp_signal", False)
    liq_str = " [LIQ]" if liq else ""
    ptp_str = " [PTP]" if ptp else ""
    print(f"  {idx}  {sig:<6} @ {price:<10} pos={pos:<6} session_pl={spl:.1f}{liq_str}{ptp_str}")

# --- BACKTEST ---
print("\n\n=== BACKTEST SIGNALS ===")
fpath = os.path.join(_DATA_ROOT, "CBOT_MINI_YM1_2026-06-30.csv")
df = pd.read_csv(fpath, index_col=0, parse_dates=True)
df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)

config = AlgoConfig(
    warmup_minutes=7,
    steep_angle_threshold=90.0,
    proximity_points=4.0,
    min_reversal_minutes=0,
    min_entry_angle=0.0,
    partial_tp_pts=50.0,
    wm_shield_distance=0.0,
    swing_anchor_threshold=10.0,
    cushion_points=40.0,
    limit_expiry_bars=5,
)

day_start = pd.Timestamp("2026-06-30 09:30", tz=_EST)
day_end = pd.Timestamp("2026-06-30 16:59", tz=_EST)
day_data = df[(df.index >= day_start) & (df.index <= day_end)]

bt_algo = run_trading_algo_fast(day_data, "2026-06-30", "09:30", "17:00", config=config)
bt_signals = bt_algo[bt_algo["signal"].notna() & (bt_algo["signal"] != "")]

print(f"Total signals: {len(bt_signals)}")
print(f"Final session_pl: {bt_algo['session_pl'].iloc[-1]:.1f} pts")
print()
for idx, row in bt_signals.iterrows():
    sig = row["signal"]
    bp = row.get("buy_price", "")
    sp = row.get("sell_price", "")
    price = bp if sig == "buy" else sp
    pos = row.get("position", "")
    spl = row.get("session_pl", 0)
    liq = row.get("is_liquidation", False)
    ptp = row.get("partial_tp_signal", False)
    liq_str = " [LIQ]" if liq else ""
    ptp_str = " [PTP]" if ptp else ""
    print(f"  {idx}  {sig:<6} @ {price:<10} pos={pos:<6} session_pl={spl:.1f}{liq_str}{ptp_str}")

# --- IB FILLS P/L ---
print("\n\n=== IB FILLS (from tracking CSV ib_ columns) ===")

# Extract rows where ib_signal is not empty
ib_signals = live[live["ib_signal"].notna() & (live["ib_signal"] != "") & (live["ib_signal"] != "flat")]
print(f"IB signal rows: {len(ib_signals)}")
print(f"IB final realized P/L (from CSV): {live['ib_realized_pl'].iloc[-1]:.1f}")
print(f"IB final unrealized P/L (from CSV): {live['ib_unrealized_pl'].iloc[-1]:.1f}")
print(f"IB final total P/L (from CSV): {live['ib_pl'].iloc[-1]:.1f}")
print()

# Also parse the validation report for IB fills
val_report = os.path.expanduser("~/Desktop/IB_Live/validation/2026-06-30/validation_report_2026-06-30.txt")
if os.path.exists(val_report):
    print("=== IB FILLS (from validation report) ===")
    with open(val_report) as f:
        content = f.read()
    # Extract fills section
    in_fills = False
    fills = []
    for line in content.split("\n"):
        if line.strip().startswith("IB Fills:"):
            in_fills = True
            continue
        if in_fills:
            if line.strip() == "" or (not line.startswith("  ")):
                in_fills = False
                continue
            fills.append(line.strip())
    
    # Calculate P/L from IB fills using a simple queue (FIFO)
    # Each open lot is tracked individually
    open_lots = []  # list of (side, price) for open lots
    total_pl = 0.0
    position = 0  # +ve = long, -ve = short
    print(f"Total IB fills: {len(fills)}")
    print()
    for fill in fills:
        parts = fill.split()
        side = parts[0]  # BOT or SLD
        qty = int(parts[1])
        price = float(parts[3])
        
        for _ in range(qty):
            if open_lots and open_lots[0][0] != side:
                # Closing a lot
                entry_side, entry_price = open_lots.pop(0)
                if entry_side == "BOT":
                    # Was long, now selling to close
                    total_pl += (price - entry_price)
                else:
                    # Was short, now buying to close
                    total_pl += (entry_price - price)
            else:
                # Opening a new lot
                open_lots.append((side, price))
        
        position = len([l for l in open_lots if l[0] == "BOT"]) - len([l for l in open_lots if l[0] == "SLD"])
        print(f"  {fill:<25} -> pos={position:+d}, running_pl={total_pl:.1f} pts")
    
    print(f"\n  Final position: {position}")
    print(f"  Total realized P/L from fills: {total_pl:.1f} pts")
    print(f"  Total realized P/L (USD): ${total_pl * 5:.0f}")

# --- COMPARISON SUMMARY ---
print("\n\n=== COMPARISON SUMMARY ===")
print(f"{'Source':<25} {'Signals':<10} {'Final P/L (pts)':<18}")
print("-" * 55)
print(f"{'Live CSV (algo signals)':<25} {len(live_signals):<10} {live['session_pl'].iloc[-1]:.1f}")
print(f"{'Backtest (same config)':<25} {len(bt_signals):<10} {bt_algo['session_pl'].iloc[-1]:.1f}")
print(f"{'IB Fills (FIFO calc)':<25} {22:<10} {total_pl:.1f}")
print(f"\nLive vs Backtest diff: {bt_algo['session_pl'].iloc[-1] - live['session_pl'].iloc[-1]:.1f} pts")
print(f"Live vs IB fills diff: {live['session_pl'].iloc[-1] - total_pl:.1f} pts")

# =============================================================================
# FULL GRID: every minute with activity across all sources
# =============================================================================
print("\n\n" + "=" * 130)
print("FULL GRID: Every event across all sources (2026-06-30)")
print("=" * 130)
print()

# Build event maps by minute
algo_csv_events = {}
for idx, row in live.iterrows():
    sig = row.get("signal", "")
    if pd.notna(sig) and sig != "":
        ts = pd.Timestamp(idx).floor("min")
        price = row.get("sell_price", None) if str(sig).upper() == "SELL" else row["Close"]
        if pd.isna(price):
            price = row["Close"]
        algo_csv_events[ts] = {"sig": str(sig).upper(), "price": float(price), "pl": float(row.get("session_pl", 0))}

bt_events = {}
bt_sigs_all = bt_algo[(bt_algo["signal"].notna()) & (bt_algo["signal"] != "")]
for idx, row in bt_sigs_all.iterrows():
    ts = idx.floor("min")
    sig = str(row["signal"]).upper()
    price = row.get("sell_price", None) if sig == "SELL" else row["Close"]
    if pd.isna(price):
        price = row["Close"]
    bt_events[ts] = {"sig": sig, "price": float(price), "pl": float(row.get("session_pl", 0))}

ib_live_events = {}
ib_rows = live[(live["ib_signal"].notna()) & (live["ib_signal"] != "") & (live["ib_signal"] != "flat")]
for idx, row in ib_rows.iterrows():
    ts = pd.Timestamp(idx).floor("min")
    sig = row["ib_signal"]
    if sig == "BUY":
        price = row.get("ib_buy_price", row["Close"])
    else:
        price = row.get("ib_sell_price", row["Close"])
    if pd.isna(price):
        price = row["Close"]
    ib_live_events[ts] = {"sig": sig, "price": float(price), "pl": float(row.get("ib_session_pl", 0))}

# IB Fills from validation report matched to ib_live timestamps
ib_fill_events = {}
ib_fill_iter = iter(fills)
for ts in sorted(ib_live_events.keys()):
    try:
        fill_line = next(ib_fill_iter)
        parts = fill_line.split()
        side = "BUY" if parts[0] == "BOT" else "SELL"
        qty = int(parts[1])
        fprice = float(parts[3])
        ib_fill_events[ts] = {"sig": side, "qty": qty, "price": fprice}
    except StopIteration:
        break

# Chart snapshots
_CHART_ROOT = os.path.expanduser("~/Desktop/IB_Live/charts")
snapshot_times = set()
for h in [10, 11, 12, 13, 14, 15, 16]:
    snap = f"YM_2026-06-30_{h:02d}00_snapshot.jpg"
    if os.path.exists(os.path.join(_CHART_ROOT, snap)):
        snapshot_times.add(pd.Timestamp(f"2026-06-30 {h:02d}:00", tz=_EST))

# All event times
all_times = set()
all_times.update(algo_csv_events.keys())
all_times.update(bt_events.keys())
all_times.update(ib_live_events.keys())
all_times.update(ib_fill_events.keys())

col_w = 22
hdr = (f"{'Time':<9} | "
       f"{'ALGO CSV':<{col_w}} | "
       f"{'BACKTEST':<{col_w}} | "
       f"{'IB LIVE (csv cols)':<{col_w}} | "
       f"{'IB FILLS (val rpt)':<{col_w}} | "
       f"{'Chart'}")
print(hdr)
print("-" * 130)

for ts in sorted(all_times):
    time_str = ts.strftime("%H:%M")
    algo_str = ""
    bt_str = ""
    ib_live_str = ""
    ib_fill_str = ""

    if ts in algo_csv_events:
        e = algo_csv_events[ts]
        algo_str = f"{e['sig']} @ {e['price']:.0f} ({e['pl']:+.0f})"
    if ts in bt_events:
        e = bt_events[ts]
        bt_str = f"{e['sig']} @ {e['price']:.0f} ({e['pl']:+.0f})"
    if ts in ib_live_events:
        e = ib_live_events[ts]
        ib_live_str = f"{e['sig']} @ {e['price']:.0f} ({e['pl']:+.0f})"
    if ts in ib_fill_events:
        e = ib_fill_events[ts]
        ib_fill_str = f"{e['sig']} {e['qty']} @ {e['price']:.0f}"

    snap_str = "YES" if ts in snapshot_times else ""
    print(f"{time_str:<9} | {algo_str:<{col_w}} | {bt_str:<{col_w}} | {ib_live_str:<{col_w}} | {ib_fill_str:<{col_w}} | {snap_str}")

# =============================================================================
# HOURLY P/L SNAPSHOT
# =============================================================================
print("\n\n" + "=" * 100)
print("HOURLY P/L SNAPSHOT")
print("=" * 100)
print()
print(f"{'Hour':<8} | {'Algo CSV P/L':<16} | {'Backtest P/L':<16} | {'IB Live P/L':<16} | {'Chart?':<8} | {'Algo Pos':<10} | {'IB Pos':<10}")
print("-" * 100)

hours = ["10:00", "11:00", "12:00", "13:00", "14:00", "15:00", "16:00", "16:58"]
for hour in hours:
    cutoff = pd.Timestamp(f"2026-06-30 {hour}", tz=_EST)
    algo_slice = live[live.index <= str(cutoff)]
    a_pl = float(algo_slice["session_pl"].iloc[-1]) if not algo_slice.empty else 0
    a_pos = algo_slice["position"].iloc[-1] if not algo_slice.empty else "flat"
    bt_slice = bt_algo[bt_algo.index <= cutoff]
    b_pl = float(bt_slice["session_pl"].iloc[-1]) if not bt_slice.empty else 0
    ib_pl_val = float(algo_slice["ib_session_pl"].iloc[-1]) if (not algo_slice.empty and "ib_session_pl" in algo_slice.columns) else 0
    ib_pos = algo_slice["ib_position"].iloc[-1] if (not algo_slice.empty and "ib_position" in algo_slice.columns) else "flat"
    h_int = int(hour.split(":")[0])
    snap_exists = os.path.exists(os.path.join(_CHART_ROOT, f"YM_2026-06-30_{h_int:02d}00_snapshot.jpg"))
    snap_str = "YES" if snap_exists else ""
    print(f"{hour:<8} | {a_pl:>+12.0f} pts | {b_pl:>+12.0f} pts | {ib_pl_val:>+12.0f} pts | {snap_str:<8} | {a_pos:<10} | {ib_pos:<10}")

# =============================================================================
# FINAL TOTALS
# =============================================================================
print("\n" + "=" * 100)
print("FINAL TOTALS")
print("=" * 100)
a_final = float(live["session_pl"].iloc[-1])
b_final = float(bt_algo["session_pl"].iloc[-1])
ib_csv_final = float(live["ib_session_pl"].iloc[-1]) if "ib_session_pl" in live.columns else 0
print(f"  Algo CSV:      {a_final:+.0f} pts (${a_final*5:,.0f})")
print(f"  Backtest:      {b_final:+.0f} pts (${b_final*5:,.0f})")
print(f"  IB Live CSV:   {ib_csv_final:+.0f} pts (${ib_csv_final*5:,.0f})")
print(f"  IB Fills FIFO: {total_pl:+.0f} pts (${total_pl*5:,.0f})")
print(f"\n  Algo vs BT:    {a_final - b_final:+.0f} pts")
print(f"  Algo vs IB:    {a_final - total_pl:+.0f} pts")
print(f"  BT vs IB:      {b_final - total_pl:+.0f} pts")
