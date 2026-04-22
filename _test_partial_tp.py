import os, pandas as pd, pytz
from TradingAlgoFast import run_trading_algo_fast, AlgoConfig
_EST = pytz.timezone("US/Eastern")
DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "930_1000")
date = "2026-02-23"
df = pd.read_csv(os.path.join(DATA_ROOT, f"CBOT_MINI_YM1_{date}.csv"), index_col=0, parse_dates=True)
df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
cfg = AlgoConfig(warmup_minutes=12, steep_angle_threshold=70.0, proximity_points=15.0,
                 min_reversal_minutes=10, min_entry_angle=30.0, partial_tp_pts=50.0)
r = run_trading_algo_fast(df, date, "09:30", "10:30", config=cfg)
partial = r[r["partial_tp"] == True]
print(f"Partial TP fires: {len(partial)} times")
for ts, row in partial.iterrows():
    print(f"  {ts.strftime('%H:%M')}  close={int(row['Close'])}  pl={row['pl']:+.0f}")
print(f"Final P/L: {r['pl'].iloc[-1]:+.0f} pts")
