import os, pandas as pd, pytz
from TradingAlgo import AlgoConfig
from TradingAlgoFast import run_trading_algo_fast

_EST = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")
config = AlgoConfig(warmup_minutes=12, steep_angle_threshold=70.0,
                    proximity_points=15.0, min_reversal_minutes=0,
                    max_loss_per_trade=0, line_tolerance=500.0)
df = pd.read_csv(os.path.join(_DATA_ROOT, "CBOT_MINI_YM1_2026-02-05.csv"), index_col=0, parse_dates=True)
df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
ds = pd.Timestamp("2026-02-05 09:30", tz=_EST); de = pd.Timestamp("2026-02-05 17:00", tz=_EST)
algo = run_trading_algo_fast(df[(df.index >= ds) & (df.index <= de)], "2026-02-05", "09:30", "17:00", config=config)

print("Time   Close   Purple  Blue    Orange  Yellow  Signal")
print("-" * 70)
for ts, row in algo.iterrows():
    t = ts.strftime("%H:%M")
    if t < "09:40" or t > "09:55": continue
    c = row["Close"]; p = row["purple_ray"]; b = row["blue_ray"]
    o = row["orange_ray"]; y = row["yellow_ray"]
    sig = str(row["signal"]) if row["signal"] != "" else ""
    flag = " <--" if sig else ""
    print(f"{t}   {c:.0f}   {p:.0f}   {b:.0f}   {o:.0f}   {y:.0f}   {sig}{flag}")
