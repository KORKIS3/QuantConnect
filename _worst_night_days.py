"""Find the 5 worst losing days in the 03:00-09:00 overnight session."""
import os
import pandas as pd, pytz, numpy as np
from TradingAlgoFast import run_trading_algo_fast, AlgoConfig

_EST       = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")

config = AlgoConfig(
    warmup_minutes=12, steep_angle_threshold=70.0, proximity_points=15.0,
    min_reversal_minutes=0, min_entry_angle=30.0, partial_tp_pts=50.0,
    spike_profit_pts=100.0, spike_profit_bars=5, wm_shield_distance=12.0,
)

csv_files = sorted([f for f in os.listdir(_DATA_ROOT)
                    if f.startswith("CBOT_MINI_YM1_") and f.endswith(".csv")])

results = []
for i, fname in enumerate(csv_files[:-1]):
    date_str      = fname.replace("CBOT_MINI_YM1_", "").replace(".csv", "")
    next_fname    = csv_files[i + 1]
    next_date_str = next_fname.replace("CBOT_MINI_YM1_", "").replace(".csv", "")
    try:
        df_cur  = pd.read_csv(os.path.join(_DATA_ROOT, fname),      index_col=0, parse_dates=True)
        df_next = pd.read_csv(os.path.join(_DATA_ROOT, next_fname), index_col=0, parse_dates=True)
        df_cur.index  = pd.to_datetime(df_cur.index,  utc=True).tz_convert(_EST)
        df_next.index = pd.to_datetime(df_next.index, utc=True).tz_convert(_EST)
        win_start = pd.Timestamp(f"{next_date_str} 03:00", tz=_EST)
        win_end   = pd.Timestamp(f"{next_date_str} 09:00", tz=_EST)
        df_w = pd.concat([df_cur, df_next]).sort_index()
        df_w = df_w[(df_w.index >= win_start) & (df_w.index <= win_end)]
        df_w = df_w[~df_w.index.duplicated(keep="first")]
        if len(df_w) < 20: continue
        algo_df = run_trading_algo_fast(df_w, next_date_str, "03:00", "09:00", config=config)
        pl = float(algo_df["session_pl"].iloc[-1])
        results.append((next_date_str, pl))
    except Exception:
        continue

results.sort(key=lambda x: x[1])
print("5 worst overnight (03:00-09:00) losing days:")
for date, pl in results[:5]:
    print(f"  {date}  {pl:+.0f} pts  (${pl*5:+,.0f})")
