"""Backtest different profit protection rules on 2 years of full day data.

Tests:
1. Baseline (no protection, run to 17:00)
2. Hard stop at 13:00
3. Hard stop at 14:00
4. Max drawdown from peak: exit if P/L drops X pts from session high
5. Daily profit lock: once P/L >= threshold, floor at threshold - buffer
"""
import os, time
import pandas as pd, pytz, numpy as np
from TradingAlgoFast import run_trading_algo_fast, AlgoConfig
from Backtest2Year import _filter_and_calc_pl

_EST      = pytz.timezone("US/Eastern")
DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")
_CONTRACTS = 2
_MULT      = 5

cfg = AlgoConfig(warmup_minutes=12, steep_angle_threshold=70.0,
                 proximity_points=15.0, min_reversal_minutes=0,
                 max_loss_per_trade=0, min_entry_angle=30.0,
                 partial_tp_pts=50.0, wm_shield_distance=12.0)

csv_files = sorted([f for f in os.listdir(DATA_ROOT)
                    if f.startswith("CBOT_MINI_YM1_") and f.endswith(".csv")])

# Protection rules to test
RULES = {
    "Baseline (17:00)":     {"end": "17:00", "drawdown": 0,   "lock_thresh": 0,   "lock_buf": 0},
    "Stop at 13:00":        {"end": "13:00", "drawdown": 0,   "lock_thresh": 0,   "lock_buf": 0},
    "Stop at 14:00":        {"end": "14:00", "drawdown": 0,   "lock_thresh": 0,   "lock_buf": 0},
    "Drawdown 150pts":      {"end": "17:00", "drawdown": 150, "lock_thresh": 0,   "lock_buf": 0},
    "Drawdown 200pts":      {"end": "17:00", "drawdown": 200, "lock_thresh": 0,   "lock_buf": 0},
    "Lock @300, buf 100":   {"end": "17:00", "drawdown": 0,   "lock_thresh": 300, "lock_buf": 100},
    "Lock @400, buf 150":   {"end": "17:00", "drawdown": 0,   "lock_thresh": 400, "lock_buf": 150},
    "Lock @500, buf 200":   {"end": "17:00", "drawdown": 0,   "lock_thresh": 500, "lock_buf": 200},
}

totals = {k: [] for k in RULES}
done = 0; total = len(csv_files)

for fname in csv_files:
    date_str = fname.replace("CBOT_MINI_YM1_","").replace(".csv","")
    try:
        df = pd.read_csv(os.path.join(DATA_ROOT, fname), index_col=0, parse_dates=True)
        df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
        if len(df) < 10: done += 1; continue
        day_start = pd.Timestamp(f"{date_str} 09:30", tz=_EST)
        day_end   = pd.Timestamp(f"{date_str} 16:59", tz=_EST)
        day_data  = df[(df.index >= day_start) & (df.index <= day_end)]
        if len(day_data) < 15: done += 1; continue

        algo = run_trading_algo_fast(day_data, date_str, "09:30", "17:00", config=cfg)
    except:
        done += 1; continue

    for rule_name, rule in RULES.items():
        end_ts = pd.Timestamp(f"{date_str} {rule['end']}", tz=_EST)
        tpls = _filter_and_calc_pl(algo, day_start, end_ts, partial_tp_pts=50)
        if not tpls:
            totals[rule_name].append(0)
            continue

        day_pl = sum(tpls)

        # Apply drawdown protection: simulate bar-by-bar P/L and exit early
        if rule["drawdown"] > 0 or rule["lock_thresh"] > 0:
            # Replay P/L bar by bar using the algo result
            sliced = algo[(algo.index >= day_start) & (algo.index <= end_ts)]
            peak_pl = 0.0; floor_pl = None; exited_pl = None
            for ts, row in sliced.iterrows():
                cur_pl = float(row["pl"])
                if cur_pl > peak_pl:
                    peak_pl = cur_pl
                    # Update lock floor if threshold crossed
                    if rule["lock_thresh"] > 0 and peak_pl >= rule["lock_thresh"]:
                        floor_pl = peak_pl - rule["lock_buf"]

                # Check drawdown exit
                if rule["drawdown"] > 0 and peak_pl > 0 and (peak_pl - cur_pl) >= rule["drawdown"]:
                    exited_pl = cur_pl
                    break

                # Check lock floor exit
                if floor_pl is not None and cur_pl < floor_pl:
                    exited_pl = floor_pl  # exit at floor
                    break

            if exited_pl is not None:
                day_pl = exited_pl

        totals[rule_name].append(day_pl)

    done += 1
    print(f"  [{done}/{total}] {int(done/total*100)}%", end="\r", flush=True)

print(f"\n\nResults across {total} days:\n")
print(f"{'Rule':<25} {'Total Pts':>10} {'Avg/Day':>8} {'Win Days':>9} {'Lose Days':>10}")
print("-" * 70)

for rule_name, pls in totals.items():
    if not pls: continue
    total_pl = sum(pls)
    avg      = total_pl / len(pls)
    wins     = sum(1 for p in pls if p > 0)
    losses   = sum(1 for p in pls if p <= 0)
    print(f"{rule_name:<25} {total_pl:>+10.0f} {avg:>+8.1f} {wins:>9} {losses:>10}")
