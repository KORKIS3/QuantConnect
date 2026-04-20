import pandas as pd
import pytz
from TradingAlgoFast import run_trading_algo_fast as run_trading_algo, AlgoConfig

est = pytz.timezone("US/Eastern")

# Load complete 1-min data from IB
csv_path = r"C:\Users\Administrator\Desktop\IB_Live\tracking\YM_1min_2026-04-07_1800.csv"
df = pd.read_csv(csv_path, index_col=0, parse_dates=True)
df.index = pd.to_datetime(df.index)
if df.index.tz is None:
    df.index = df.index.tz_localize(est)
else:
    df.index = df.index.tz_convert(est)

# Filter to 18:00-19:00
t_start = pd.Timestamp("2026-04-07 18:00:00", tz=est)
t_end   = pd.Timestamp("2026-04-07 19:00:00", tz=est)
df = df[(df.index >= t_start) & (df.index <= t_end)]

# Resample to 5-min bars (outside 9:30-10:30 window)
minute_df = df.resample("5min").agg(
    Open=("Open", "first"),
    High=("High", "max"),
    Low=("Low", "min"),
    Close=("Close", "last"),
    Volume=("Volume", "sum"),
).dropna(subset=["Open"])

print("5-min bars:")
print(minute_df[["Open","High","Low","Close"]].to_string())
print()

config = AlgoConfig(warmup_minutes=7, steep_angle_threshold=65.0, proximity_points=15.0)
algo_df = run_trading_algo(minute_df, "2026-04-07", "18:00", "19:00", config=config)

contracts = 100
multiplier = 5
final_pl_pts = float(algo_df["pl"].iloc[-1])
final_pl_dollars = final_pl_pts * contracts * multiplier

print("=== 04/07/26  18:00 - 19:00 (5-min bars, complete data) ===")
print()
signals = algo_df[algo_df["signal"].isin(["BUY","SELL"])]
for ts, row in signals.iterrows():
    sig = row["signal"]
    price = row["buy_price"] if sig == "BUY" else row["sell_price"]
    pl = row["pl"]
    print(f"  {ts.strftime('%H:%M')}  {sig:4s}  @ {int(price)}   P/L: {pl:+.0f} pts  /  ${pl*contracts*multiplier:+,.0f}")

print()
print(f"Final P/L:  {final_pl_pts:+.0f} points")
print(f"            ${final_pl_dollars:+,.0f}  (100 contracts x $5/pt)")
