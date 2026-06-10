"""Improve from Engine 89 baseline using engine's session_pl (honest, includes trailing stop v4).

The engine's session_pl already uses: (exit - entry) * contracts_remaining for all trades.
We sweep parameters that change the ENGINE's signal generation to improve the base P/L.
The 60pt SL improvement (+27 pts) is additive on top of whatever we find here.
"""
import os
import pandas as pd
import numpy as np
import pytz
from TradingAlgoFast import AlgoConfig, run_trading_algo_fast

_EST = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")

csv_files = sorted([f for f in os.listdir(_DATA_ROOT)
                    if f.startswith("CBOT_MINI_YM1_") and f.endswith(".csv")])


def run_engine_backtest(config, end_time="17:00"):
    """Run backtest using engine's session_pl directly. Returns avg_pts_day, num_days, win_pct."""
    daily_pls = []

    for fname in csv_files:
        target_date = fname.replace("CBOT_MINI_YM1_", "").replace(".csv", "")
        fpath = os.path.join(_DATA_ROOT, fname)

        try:
            df = pd.read_csv(fpath, index_col=0, parse_dates=True)
            df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
            if len(df) < 15:
                continue
            if (df[["Open", "High", "Low", "Close"]] <= 0).any().any():
                continue
            if df["High"].max() == df["Low"].min():
                continue
            if df["Volume"].sum() < 100:
                continue

            day_start = pd.Timestamp(f"{target_date} 09:30", tz=_EST)
            day_end = pd.Timestamp(f"{target_date} 16:59", tz=_EST)
            day_data = df[(df.index >= day_start) & (df.index <= day_end)]
            if len(day_data) < 15:
                continue

            algo_df = run_trading_algo_fast(day_data, target_date, "09:30", end_time, config=config)

            end_ts = pd.Timestamp(f"{target_date} {end_time}", tz=_EST)
            sliced = algo_df[(algo_df.index >= day_start) & (algo_df.index <= end_ts)]
            if len(sliced) < 2:
                continue

            pl = float(sliced["session_pl"].iloc[-1])
            if pl != 0.0:
                daily_pls.append(pl)

        except Exception:
            continue

    if not daily_pls:
        return 0.0, 0, 0.0
    arr = np.array(daily_pls)
    return arr.mean(), len(arr), (arr > 0).sum() / len(arr) * 100


print("=" * 70, flush=True)
print("ENGINE PARAMETER SWEEP (honest session_pl, includes trailing stop v4)", flush=True)
print("Note: +27 pts/day from 60pt SL is additive on top of these numbers", flush=True)
print("=" * 70, flush=True)

# BASELINE
base_config = AlgoConfig(
    warmup_minutes=12,
    steep_angle_threshold=70.0,
    proximity_points=15.0,
    min_reversal_minutes=0,
    min_entry_angle=0.0,
    partial_tp_pts=50.0,
    wm_shield_distance=12.0,
    swing_anchor_threshold=10.0,
    cushion_points=0.0,
    limit_expiry_bars=5,
)
print("\n[BASELINE]:", flush=True)
avg, days, win = run_engine_backtest(base_config)
print(f"  {avg:+.1f} pts/day, {days} days, {win:.1f}% win (+27 with SL = {avg+27:+.1f})", flush=True)

# TEST 1: Steep angle
print("\n[TEST 1] Steep angle threshold:", flush=True)
for steep in [50, 55, 60, 65, 70, 75, 80, 85]:
    cfg = AlgoConfig(warmup_minutes=12, steep_angle_threshold=float(steep),
                     proximity_points=15.0, min_reversal_minutes=0, min_entry_angle=0.0,
                     partial_tp_pts=50.0, wm_shield_distance=12.0, swing_anchor_threshold=10.0,
                     cushion_points=0.0, limit_expiry_bars=5)
    avg, days, win = run_engine_backtest(cfg)
    print(f"  steep={steep}: {avg:+.1f} pts/day, {win:.1f}% win (+SL={avg+27:+.1f})", flush=True)

# TEST 2: Proximity
print("\n[TEST 2] Proximity points:", flush=True)
for prox in [5, 8, 10, 12, 15, 18, 20, 25]:
    cfg = AlgoConfig(warmup_minutes=12, steep_angle_threshold=70.0,
                     proximity_points=float(prox), min_reversal_minutes=0, min_entry_angle=0.0,
                     partial_tp_pts=50.0, wm_shield_distance=12.0, swing_anchor_threshold=10.0,
                     cushion_points=0.0, limit_expiry_bars=5)
    avg, days, win = run_engine_backtest(cfg)
    print(f"  proximity={prox}: {avg:+.1f} pts/day, {win:.1f}% win (+SL={avg+27:+.1f})", flush=True)

# TEST 3: Warmup
print("\n[TEST 3] Warmup minutes:", flush=True)
for wu in [7, 8, 10, 12, 14, 16, 18]:
    cfg = AlgoConfig(warmup_minutes=wu, steep_angle_threshold=70.0,
                     proximity_points=15.0, min_reversal_minutes=0, min_entry_angle=0.0,
                     partial_tp_pts=50.0, wm_shield_distance=12.0, swing_anchor_threshold=10.0,
                     cushion_points=0.0, limit_expiry_bars=5)
    avg, days, win = run_engine_backtest(cfg)
    print(f"  warmup={wu}: {avg:+.1f} pts/day, {win:.1f}% win (+SL={avg+27:+.1f})", flush=True)

# TEST 4: WM shield
print("\n[TEST 4] WM shield distance:", flush=True)
for wm in [0, 5, 8, 10, 12, 15, 18, 20, 25]:
    cfg = AlgoConfig(warmup_minutes=12, steep_angle_threshold=70.0,
                     proximity_points=15.0, min_reversal_minutes=0, min_entry_angle=0.0,
                     partial_tp_pts=50.0, wm_shield_distance=float(wm), swing_anchor_threshold=10.0,
                     cushion_points=0.0, limit_expiry_bars=5)
    avg, days, win = run_engine_backtest(cfg)
    print(f"  wm_shield={wm}: {avg:+.1f} pts/day, {win:.1f}% win (+SL={avg+27:+.1f})", flush=True)

# TEST 5: Swing anchor threshold
print("\n[TEST 5] Swing anchor threshold:", flush=True)
for sa in [5, 8, 10, 15, 20, 25, 30]:
    cfg = AlgoConfig(warmup_minutes=12, steep_angle_threshold=70.0,
                     proximity_points=15.0, min_reversal_minutes=0, min_entry_angle=0.0,
                     partial_tp_pts=50.0, wm_shield_distance=12.0, swing_anchor_threshold=float(sa),
                     cushion_points=0.0, limit_expiry_bars=5)
    avg, days, win = run_engine_backtest(cfg)
    print(f"  swing_anchor={sa}: {avg:+.1f} pts/day, {win:.1f}% win (+SL={avg+27:+.1f})", flush=True)

# TEST 6: Partial TP level
print("\n[TEST 6] Partial TP pts:", flush=True)
for tp in [30, 40, 50, 60, 70, 80, 100]:
    cfg = AlgoConfig(warmup_minutes=12, steep_angle_threshold=70.0,
                     proximity_points=15.0, min_reversal_minutes=0, min_entry_angle=0.0,
                     partial_tp_pts=float(tp), wm_shield_distance=12.0, swing_anchor_threshold=10.0,
                     cushion_points=0.0, limit_expiry_bars=5)
    avg, days, win = run_engine_backtest(cfg)
    print(f"  partial_tp={tp}: {avg:+.1f} pts/day, {win:.1f}% win (+SL={avg+27:+.1f})", flush=True)

# TEST 7: Session end time
print("\n[TEST 7] Session end time:", flush=True)
for et in ["11:00", "12:00", "13:00", "14:00", "15:00", "16:00", "17:00"]:
    avg, days, win = run_engine_backtest(base_config, end_time=et)
    print(f"  end={et}: {avg:+.1f} pts/day, {win:.1f}% win (+SL={avg+27:+.1f})", flush=True)

print("\n[DONE] Best combos can be stacked for final test.", flush=True)
