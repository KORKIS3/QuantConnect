import pandas as pd, pytz, os
from TradingAlgoFast import run_trading_algo_fast, AlgoConfig

_EST = pytz.timezone("US/Eastern")
DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")

date = "2026-04-21"
df = pd.read_csv(os.path.join(DATA_ROOT, f"CBOT_MINI_YM1_{date}.csv"), index_col=0, parse_dates=True)
df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
ds = pd.Timestamp(f"{date} 09:30", tz=_EST)
de = pd.Timestamp(f"{date} 17:00", tz=_EST)
df = df[(df.index >= ds) & (df.index <= de)]

cfg = AlgoConfig(warmup_minutes=12, steep_angle_threshold=70.0, proximity_points=15.0,
                 min_reversal_minutes=10, min_entry_angle=30.0,
                 partial_tp_pts=50.0, wm_shield_distance=12.0)

result = run_trading_algo_fast(df, date, "09:30", "17:00", config=cfg)

# Show bar-by-bar from 13:00 onwards with position and P/L
print("Bar-by-bar from 13:00 (position, close, P/L):")
afternoon = result[result.index.hour >= 13]
for ts, row in afternoon.iterrows():
    sig = row["signal"] if row["signal"] in ["BUY","SELL"] else ""
    ptp = " [PARTIAL TP]" if row["partial_tp"] else ""
    liq = " [LIQ]" if row["is_liquidation"] else ""
    marker = f"  *** {sig}{liq}{ptp}" if (sig or ptp) else ""
    print(f"  {ts.strftime('%H:%M')}  pos={row['position']:5s}  close={int(row['Close'])}  pl={row['pl']:+.0f}{marker}")
