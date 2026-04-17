"""Trace the fast algo bar by bar around 06:00-06:02 on 2025-03-27."""
import pandas as pd, pytz, os, numpy as np
from TradingAlgoFast import run_trading_algo_fast
from TradingAlgo import AlgoConfig

est = pytz.timezone("US/Eastern")
data_root = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "930_1130")
fname = "CBOT_MINI_YM1_2025-03-27.csv"
df = pd.read_csv(os.path.join(data_root, fname), index_col=0, parse_dates=True)
df.index = pd.to_datetime(df.index, utc=True).tz_convert(est)

config = AlgoConfig(warmup_minutes=12, steep_angle_threshold=70.0,
                    proximity_points=15.0, min_reversal_minutes=0, max_loss_per_trade=0)
fast = run_trading_algo_fast(df, "2025-03-27", "09:30", "10:30", config=config)

# Print bars 05:58 to 06:05
for i in range(len(fast)):
    ts = fast.index[i]
    hhmm = ts.strftime("%H:%M")
    if "05:58" <= hhmm <= "06:05":
        row = fast.iloc[i]
        sig = row.get("signal", "")
        pos = row.get("position", "")
        close = float(row["Close"])
        purple = float(row["purple_ray"])
        blue = float(row["blue_ray"])
        liq = bool(row.get("is_liquidation", False))
        print(f"{hhmm}: close={close:.0f} purple={purple:.1f} blue={blue:.1f} "
              f"sig={sig:>4} liq={liq} pos={pos}")
