import os, pandas as pd, pytz
from TradingAlgoFast import run_trading_algo_fast, AlgoConfig

_EST = pytz.timezone("US/Eastern")
DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "930_1000")
date = "2026-02-23"

df = pd.read_csv(os.path.join(DATA_ROOT, f"CBOT_MINI_YM1_{date}.csv"), index_col=0, parse_dates=True)
df.index = pd.to_datetime(df.index, utc=False)
if df.index.tz is None:
    df.index = df.index.tz_localize(_EST)
else:
    df.index = df.index.tz_convert(_EST)

cfg = AlgoConfig(warmup_minutes=12, steep_angle_threshold=70.0, proximity_points=15.0, min_reversal_minutes=10)
result = run_trading_algo_fast(df, date, "09:30", "10:30", config=cfg)

signals = result[result["signal"].isin(["BUY", "SELL"])]
print(f"Date:    {date}")
print(f"Bars:    {len(result)}")
print(f"Signals: {len(signals)}")
print()
for ts, row in signals.iterrows():
    sig   = row["signal"]
    price = row["buy_price"] if sig == "BUY" else row["sell_price"]
    liq   = " [LIQ]" if row["is_liquidation"] else ""
    print(f"  {ts.strftime('%H:%M')}  {sig:4s} @ {int(price)}   P/L: {row['pl']:+.0f} pts{liq}")

final = result["pl"].iloc[-1]
print(f"\nFinal P/L: {final:+.0f} pts  /  ${final*5*2:+,.0f}  (2 contracts)")
