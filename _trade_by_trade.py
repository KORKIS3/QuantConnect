"""Trade-by-trade apples-to-apples comparison: Live Algo vs Backtest vs IB Actual."""
import pandas as pd
import os, pytz
from TradingAlgoFast import AlgoConfig, run_trading_algo_fast

_EST = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")

# Load live tracking CSV
live_path = os.path.expanduser("~/Desktop/IB_Live/tracking/YM_tracking_DUO158495_2026-06-30_0930.csv")
live = pd.read_csv(live_path, index_col=0, parse_dates=True)

# Run backtest
fpath = os.path.join(_DATA_ROOT, "CBOT_MINI_YM1_2026-06-30.csv")
df = pd.read_csv(fpath, index_col=0, parse_dates=True)
df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
config = AlgoConfig(
    warmup_minutes=7, steep_angle_threshold=90.0, proximity_points=4.0,
    min_reversal_minutes=0, min_entry_angle=0.0, partial_tp_pts=50.0,
    wm_shield_distance=0.0, swing_anchor_threshold=10.0, cushion_points=40.0, limit_expiry_bars=5,
)
day_start = pd.Timestamp("2026-06-30 09:30", tz=_EST)
day_end = pd.Timestamp("2026-06-30 16:59", tz=_EST)
day_data = df[(df.index >= day_start) & (df.index <= day_end)]
bt = run_trading_algo_fast(day_data, "2026-06-30", "09:30", "17:00", config=config)


def get_trades(algo_df):
    """Extract trade list with fill prices from algo DataFrame."""
    sigs = algo_df[(algo_df["signal"].notna()) & (algo_df["signal"] != "")]
    trades = []
    for idx, row in sigs.iterrows():
        sig = str(row["signal"]).upper()
        # For sells, use sell_price; for buys, use Close (market order fills at close)
        if sig == "SELL":
            price = row.get("sell_price", row["Close"])
            if pd.isna(price):
                price = row["Close"]
        else:
            price = row["Close"]
        trades.append({
            "time": idx,
            "signal": sig,
            "price": float(price),
            "session_pl": float(row.get("session_pl", 0)),
        })
    return trades


live_trades = get_trades(live)
bt_trades = get_trades(bt)

# Get IB fills with timestamps from tracking CSV
ib_sig_rows = live[
    (live["ib_signal"].notna()) & (live["ib_signal"] != "") & (live["ib_signal"] != "flat")
]
ib_trades_timed = []
for idx, row in ib_sig_rows.iterrows():
    sig = row["ib_signal"]
    if sig == "BUY":
        price = row.get("ib_buy_price", row.get("fill_price", row["Close"]))
    else:
        price = row.get("ib_sell_price", row.get("fill_price", row["Close"]))
    if pd.isna(price):
        price = row["Close"]
    ib_trades_timed.append({"time": pd.Timestamp(idx), "signal": sig, "price": float(price)})

# Print header
print("=" * 110)
print("TRADE-BY-TRADE COMPARISON: Live Algo vs Backtest vs IB Actual (2026-06-30)")
print("=" * 110)
print()
header = f"{'#':<4} {'Time':<18} {'Dir':<6} | {'Live Algo':<12} {'Backtest':<12} {'IB Fill':<12} | {'Live-BT':<9} {'Live-IB':<9} {'BT-IB':<9}"
print(header)
print("-" * 110)

# Match each algo trade to the closest IB fill (same direction, within 3 min)
used_ib = set()
total_live_bt_slip = 0.0
total_live_ib_slip = 0.0
ib_matched = 0

for i, (lt, btt) in enumerate(zip(live_trades, bt_trades), 1):
    lt_time = pd.Timestamp(lt["time"])
    bt_time = btt["time"]
    direction = lt["signal"]

    # Find matching IB fill
    ib_price = None
    ib_match_idx = None
    best_diff = 999
    for j, ib in enumerate(ib_trades_timed):
        if j in used_ib:
            continue
        diff_sec = abs((ib["time"] - lt_time).total_seconds())
        if diff_sec <= 180 and ib["signal"] == direction and diff_sec < best_diff:
            best_diff = diff_sec
            ib_price = ib["price"]
            ib_match_idx = j

    if ib_match_idx is not None:
        used_ib.add(ib_match_idx)
        ib_matched += 1

    # Calculate slippage
    live_bt_diff = lt["price"] - btt["price"]
    live_ib_diff = (lt["price"] - ib_price) if ib_price else None
    bt_ib_diff = (btt["price"] - ib_price) if ib_price else None

    total_live_bt_slip += live_bt_diff
    if live_ib_diff is not None:
        total_live_ib_slip += live_ib_diff

    # Format time
    time_str = str(lt_time)[11:16]
    bt_time_str = str(bt_time)[11:16]
    time_display = time_str if time_str == bt_time_str else f"{time_str}*"

    ib_str = f"{ib_price:.0f}" if ib_price else "NO MATCH"
    diff_lb = f"{live_bt_diff:+.0f}" if live_bt_diff != 0 else "0"
    diff_li = f"{live_ib_diff:+.0f}" if live_ib_diff is not None else "---"
    diff_bi = f"{bt_ib_diff:+.0f}" if bt_ib_diff is not None else "---"

    print(f"{i:<4} {time_display:<18} {direction:<6} | {lt['price']:<12.0f} {btt['price']:<12.0f} {ib_str:<12} | {diff_lb:<9} {diff_li:<9} {diff_bi:<9}")

# Footer
print("-" * 110)
print(f"{'':4} {'TOTALS':<18} {'':6} | {'':12} {'':12} {'':12} | {total_live_bt_slip:<+9.0f} {total_live_ib_slip:<+9.0f}")
print()

# Note the one timing difference
print("* = Backtest fired at different minute (14:40 vs live 14:47)")
print()

# P/L summary
print("=" * 60)
print("P/L SUMMARY")
print("=" * 60)
live_final = live_trades[-1]["session_pl"]
bt_final = bt_trades[-1]["session_pl"]
ib_final = 266.0  # from FIFO fill calculation
print(f"  Live Algo (theoretical):  {live_final:+.0f} pts  (${live_final * 5:,.0f})")
print(f"  Backtest:                 {bt_final:+.0f} pts  (${bt_final * 5:,.0f})")
print(f"  IB Actual (from fills):   {ib_final:+.0f} pts  (${ib_final * 5:,.0f})")
print()
print(f"  Live vs Backtest gap:     {live_final - bt_final:+.0f} pts")
print(f"  Live vs IB gap:           {live_final - ib_final:+.0f} pts (execution slippage)")
print(f"  Backtest vs IB gap:       {bt_final - ib_final:+.0f} pts")
print()
print(f"  IB fills matched to algo: {ib_matched}/{len(live_trades)}")
print(f"  Extra IB fills (partial TP / flatten): {len(ib_trades_timed) - ib_matched}")
