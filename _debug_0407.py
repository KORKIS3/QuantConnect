"""Debug 04/07/25 signal mismatch."""
import os, pandas as pd, pytz
from TradingAlgo import run_trading_algo, AlgoConfig
from TradingAlgoFast import run_trading_algo_fast

_EST = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")
config = AlgoConfig(warmup_minutes=12, steep_angle_threshold=70.0, proximity_points=15.0,
                    min_reversal_minutes=0, max_loss_per_trade=999)
dd = "2025-04-07"
df = pd.read_csv(os.path.join(_DATA_ROOT, f"CBOT_MINI_YM1_{dd}.csv"), index_col=0, parse_dates=True)
df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
ds = pd.Timestamp(f"{dd} 09:30", tz=_EST); de = pd.Timestamp(f"{dd} 10:30", tz=_EST)
dd_data = df[(df.index >= ds) & (df.index <= de)]

algo = run_trading_algo(dd_data, dd, "09:30", "10:30", config=config)
fast = run_trading_algo_fast(dd_data, dd, "09:30", "10:30", config=config)

print("Bar  Time   Close   Purple  PAngle  Signal(algo)  Signal(fast)")
print("-" * 75)
for i in range(len(algo)):
    t = algo.index[i].strftime("%H:%M")
    c = algo["Close"].iloc[i]
    p = algo["purple_ray"].iloc[i]
    pa = algo["purple_angle"].iloc[i] if "purple_angle" in algo.columns else 0
    asig = algo["signal"].iloc[i] if pd.notna(algo["signal"].iloc[i]) else ""
    fsig = fast["signal"].iloc[i] if pd.notna(fast["signal"].iloc[i]) else ""
    if asig or fsig or i < 20:
        flag = " <-- DIFF" if asig != fsig else ""
        print(f"{i:3d}  {t}  {c:.0f}  {p:.0f}  {pa:.1f}°  {str(asig):<12}  {str(fsig):<12}{flag}")
