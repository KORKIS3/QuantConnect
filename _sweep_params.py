"""Parameter sweep — find best combo vs 183.3 pts/day baseline."""
import os, time, pytz, numpy as np, pandas as pd
from itertools import product
from TradingAlgoFast import AlgoConfig, run_trading_algo_fast

_EST       = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")
_CSV_FILES = sorted([f for f in os.listdir(_DATA_ROOT)
                     if f.startswith("CBOT_MINI_YM1_") and f.endswith(".csv")])

def run_config(config):
    total_pl = 0.0; win_days = 0; total_days = 0
    for fname in _CSV_FILES:
        date = fname.replace("CBOT_MINI_YM1_","").replace(".csv","")
        df = pd.read_csv(os.path.join(_DATA_ROOT, fname), index_col=0, parse_dates=True)
        df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
        day = df[(df.index >= pd.Timestamp(f"{date} 09:30", tz=_EST)) &
                 (df.index <= pd.Timestamp(f"{date} 16:59", tz=_EST))]
        if len(day) < 15: continue
        try:
            result = run_trading_algo_fast(day, date, "09:30", "17:00", config=config)
            end_ts = pd.Timestamp(f"{date} 17:00", tz=_EST)
            sliced = result[result.index <= end_ts]
            pl = float(sliced["session_pl"].iloc[-1])
            total_pl += pl
            total_days += 1
            if pl > 0: win_days += 1
        except: pass
    avg = total_pl / total_days if total_days else 0
    win_pct = win_days / total_days * 100 if total_days else 0
    return avg, win_pct, total_days

# Baseline
print("Running baseline...")
t0 = time.time()
baseline_config = AlgoConfig(
    warmup_minutes=12, steep_angle_threshold=70.0, proximity_points=15.0,
    min_reversal_minutes=0, min_entry_angle=30.0,
    partial_tp_pts=50.0, wm_shield_distance=12.0,
)
base_avg, base_win, base_days = run_config(baseline_config)
print(f"Baseline: {base_avg:+.1f} pts/day  {base_win:.1f}% win  ({time.time()-t0:.0f}s)\n")

# Parameter grid
sweep = {
    "steep_angle_threshold": [60.0, 65.0, 70.0, 75.0],
    "proximity_points":      [8.0, 12.0, 15.0, 20.0],
    "min_entry_angle":       [0.0, 20.0, 30.0, 40.0],
    "warmup_minutes":        [8, 10, 12, 15],
    "partial_tp_pts":        [30.0, 50.0, 75.0, 100.0],
    "wm_shield_distance":    [0.0, 8.0, 12.0, 16.0],
}

results = []
keys = list(sweep.keys())
values = list(sweep.values())

# Single-param sweep first (hold others at baseline)
baseline_vals = {
    "steep_angle_threshold": 70.0,
    "proximity_points": 15.0,
    "min_entry_angle": 30.0,
    "warmup_minutes": 12,
    "partial_tp_pts": 50.0,
    "wm_shield_distance": 12.0,
}

print(f"{'Param':<25} {'Value':>8}  {'Avg/Day':>8}  {'Win%':>6}  {'vs Base':>8}")
print("-" * 65)

best_singles = dict(baseline_vals)

for param, vals in sweep.items():
    best_val = baseline_vals[param]; best_avg = base_avg
    for v in vals:
        cfg_kwargs = dict(baseline_vals)
        cfg_kwargs[param] = v
        cfg = AlgoConfig(
            warmup_minutes=cfg_kwargs["warmup_minutes"],
            steep_angle_threshold=cfg_kwargs["steep_angle_threshold"],
            proximity_points=cfg_kwargs["proximity_points"],
            min_reversal_minutes=0,
            min_entry_angle=cfg_kwargs["min_entry_angle"],
            partial_tp_pts=cfg_kwargs["partial_tp_pts"],
            wm_shield_distance=cfg_kwargs["wm_shield_distance"],
        )
        avg, win, _ = run_config(cfg)
        marker = " ◄ BEST" if avg > best_avg else ""
        print(f"{param:<25} {str(v):>8}  {avg:>+8.1f}  {win:>5.1f}%  {avg-base_avg:>+8.1f}{marker}")
        if avg > best_avg:
            best_avg = avg; best_val = v
    best_singles[param] = best_val
    print()

# Run best combo
print("\n--- Best combo ---")
best_cfg = AlgoConfig(
    warmup_minutes=best_singles["warmup_minutes"],
    steep_angle_threshold=best_singles["steep_angle_threshold"],
    proximity_points=best_singles["proximity_points"],
    min_reversal_minutes=0,
    min_entry_angle=best_singles["min_entry_angle"],
    partial_tp_pts=best_singles["partial_tp_pts"],
    wm_shield_distance=best_singles["wm_shield_distance"],
)
print(f"Config: {best_singles}")
avg, win, days = run_config(best_cfg)
print(f"Result: {avg:+.1f} pts/day  {win:.1f}% win  {days} days  (vs baseline {base_avg:+.1f}, delta {avg-base_avg:+.1f})")
