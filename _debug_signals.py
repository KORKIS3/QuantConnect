"""Debug: trace all signals on 02/23 to find what triggered the BUY/LIQ."""
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

print("Bar  Time   Close   Purple  Blue    Orange  Yellow  Signal  BuyPx   SellPx")
print("-" * 95)
for i, (ts, row) in enumerate(algo.iterrows()):
    t = ts.strftime("%H:%M")
    c = row["Close"]
    p = row["purple_ray"]
    b = row["blue_ray"]
    o = row["orange_ray"]
    y = row["yellow_ray"]
    sig = row.get("signal", "")
    bp = row.get("buy_price", "")
    sp = row.get("sell_price", "")
    sig_str = str(sig) if pd.notna(sig) and str(sig) != "" else ""
    bp_str = f"{float(bp):.0f}" if pd.notna(bp) else ""
    sp_str = f"{float(sp):.0f}" if pd.notna(sp) else ""
    if sig_str or i < 25 or i > 45:
        print(f"{i:3d}  {t}  {c:.0f}   {p:.0f}   {b:.0f}   {o:.0f}   {y:.0f}   {sig_str:<6} {bp_str:<8} {sp_str}")
