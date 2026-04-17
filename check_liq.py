import pandas as pd, pytz, os
from TradingAlgo import run_trading_algo, AlgoConfig
est = pytz.timezone("US/Eastern")
data_root = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "930_1130")
files = sorted([f for f in os.listdir(data_root) if f.endswith(".csv")])
fname = files[-10]
target_date = fname.replace("CBOT_MINI_YM1_","").replace(".csv","")
df = pd.read_csv(os.path.join(data_root, fname), index_col=0, parse_dates=True)
df.index = pd.to_datetime(df.index, utc=True).tz_convert(est)
config = AlgoConfig(warmup_minutes=12, steep_angle_threshold=70.0,
                    proximity_points=15.0, min_reversal_minutes=0, max_loss_per_trade=0)
orig = run_trading_algo(df, target_date, "09:30", "10:30", config=config)
for ts, row in orig.iterrows():
    if row.get("signal") in ("BUY","SELL"):
        is_liq = bool(row.get("is_liquidation", False))
        print(f"{ts.strftime('%H:%M')} {row['signal']} liq={is_liq}")
