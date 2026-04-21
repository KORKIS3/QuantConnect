"""Compare baseline config vs new config (min_entry_angle=30) side by side."""
import os, time
import pandas as pd, pytz, numpy as np
from TradingAlgoFast import AlgoConfig, run_trading_algo_fast
from Backtest2Year import _filter_and_calc_pl, DAY_END_TIMES, NIGHT_END_TIMES

_EST       = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")
_CONTRACTS = 2
_MULTIPLIER = 5

CONFIGS = {
    "BASELINE (angle=0) ": AlgoConfig(warmup_minutes=12, steep_angle_threshold=70.0,
                                       proximity_points=15.0, min_reversal_minutes=0,
                                       max_loss_per_trade=0, min_entry_angle=0.0),
    "NEW      (angle=30)": AlgoConfig(warmup_minutes=12, steep_angle_threshold=70.0,
                                       proximity_points=15.0, min_reversal_minutes=0,
                                       max_loss_per_trade=0, min_entry_angle=30.0),
    "NEW      (angle=35)": AlgoConfig(warmup_minutes=12, steep_angle_threshold=70.0,
                                       proximity_points=15.0, min_reversal_minutes=0,
                                       max_loss_per_trade=0, min_entry_angle=35.0),
}

csv_files = sorted([f for f in os.listdir(_DATA_ROOT)
                    if f.startswith("CBOT_MINI_YM1_") and f.endswith(".csv")])
total = len(csv_files)

results = {name: {et: {"trades":0,"pl":0.0,"winners":0,"losers":0,"daily_pls":[]}
                  for et in DAY_END_TIMES} for name in CONFIGS}
for name, config in CONFIGS.items():
    print(f"\nRunning {name.strip()} on {total} days ...", flush=True)
    t0 = time.time(); done = 0
    for fname in csv_files:
        target_date = fname.replace("CBOT_MINI_YM1_","").replace(".csv","")
        fpath = os.path.join(_DATA_ROOT, fname)
        try:
            df = pd.read_csv(fpath, index_col=0, parse_dates=True)
            df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
            if len(df) < 10: done += 1; continue
        except: done += 1; continue

        day_start = pd.Timestamp(f"{target_date} 09:30", tz=_EST)
        day_end   = pd.Timestamp(f"{target_date} 16:59", tz=_EST)
        day_data  = df[(df.index >= day_start) & (df.index <= day_end)]

        if len(day_data) >= 15:
            try:
                algo = run_trading_algo_fast(day_data, target_date, "09:30", "17:00", config=config)
                for et in DAY_END_TIMES:
                    end_ts = pd.Timestamp(f"{target_date} {et}", tz=_EST)
                    tpls = _filter_and_calc_pl(algo, day_start, end_ts, partial_tp_pts=50)
                    if tpls:
                        day_pl = sum(tpls)
                        results[name][et]["trades"]    += len(tpls)
                        results[name][et]["pl"]        += day_pl
                        results[name][et]["winners"]   += sum(1 for p in tpls if p > 0)
                        results[name][et]["losers"]    += sum(1 for p in tpls if p <= 0)
                        results[name][et]["daily_pls"].append(day_pl)
            except: pass
        done += 1
        print(f"  [{done}/{total}] {int(done/total*100)}%", end="\r", flush=True)
    print(f"\n  Done in {time.time()-t0:.1f}s")

# Print side by side — 3 configs
names = list(CONFIGS.keys())
n0, n1, n2 = names[0], names[1], names[2]

print(f"\n{'='*115}")
print(f"{'End':^6} | {'BASELINE (angle=0)':^33} | {'NEW (angle=30)':^33} | {'NEW (angle=35)':^33}")
print(f"{'Time':^6} | {'Trades':>7} {'Win%':>6} {'Avg/Day':>8} {'Pts':>9} | {'Trades':>7} {'Win%':>6} {'Avg/Day':>8} {'Diff':>6} | {'Trades':>7} {'Win%':>6} {'Avg/Day':>8} {'Diff':>6}")
print(f"{'='*115}")

for et in DAY_END_TIMES:
    b  = results[n0][et]
    r1 = results[n1][et]
    r2 = results[n2][et]
    b_wr  = b["winners"]/b["trades"]*100   if b["trades"]  else 0
    r1_wr = r1["winners"]/r1["trades"]*100 if r1["trades"] else 0
    r2_wr = r2["winners"]/r2["trades"]*100 if r2["trades"] else 0
    b_avg  = np.mean(b["daily_pls"])  if b["daily_pls"]  else 0
    r1_avg = np.mean(r1["daily_pls"]) if r1["daily_pls"] else 0
    r2_avg = np.mean(r2["daily_pls"]) if r2["daily_pls"] else 0
    d1 = r1_avg - b_avg
    d2 = r2_avg - b_avg
    m1 = "+" if d1 > 0.5 else ("-" if d1 < -0.5 else " ")
    m2 = "+" if d2 > 0.5 else ("-" if d2 < -0.5 else " ")
    print(f"{et:^6} | {b['trades']:>7} {b_wr:>5.1f}% {b_avg:>+8.1f} {b['pl']:>9.0f} | "
          f"{r1['trades']:>7} {r1_wr:>5.1f}% {r1_avg:>+8.1f} {d1:>+5.1f}{m1} | "
          f"{r2['trades']:>7} {r2_wr:>5.1f}% {r2_avg:>+8.1f} {d2:>+5.1f}{m2}")

print(f"{'='*115}")
