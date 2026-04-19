"""Debug: check where highs touch the purple line."""
import os
import pandas as pd, pytz
from TradingAlgo import run_trading_algo, AlgoConfig

_EST = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")

df = pd.read_csv(os.path.join(_DATA_ROOT, "CBOT_MINI_YM1_2026-02-23.csv"), index_col=0, parse_dates=True)
df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
ds = pd.Timestamp("2026-02-23 09:30", tz=_EST)
de = pd.Timestamp("2026-02-23 10:30", tz=_EST)
df = df[(df.index >= ds) & (df.index <= de)]

config = AlgoConfig(warmup_minutes=12, steep_angle_threshold=70.0,
                    proximity_points=15.0, min_reversal_minutes=10)
algo = run_trading_algo(df, "2026-02-23", "09:30", "10:30", config=config)

print("Bar  Time   High    Purple   Gap     DarkPurple  Touch?")
print("-" * 70)
for i, (ts, row) in enumerate(algo.iterrows()):
    t = ts.strftime("%H:%M")
    h = row["High"]
    p = row["purple_ray"]
    dp = row.get("dark_purple_ray", float("nan"))
    gap = h - p
    dp_str = f"{dp:.0f}" if not pd.isna(dp) else "---"
    touch = "TOUCH" if gap >= -5 else ""
    print(f"{i:3d}  {t}  {h:.0f}   {p:.0f}   {gap:+.0f}     {dp_str:>8}    {touch}")
