import os, pandas as pd, pytz
from TradingAlgoFast import run_trading_algo_fast, AlgoConfig

_EST = pytz.timezone("US/Eastern")
DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")

date    = "2026-04-29"
start_t = "09:30"
end_t   = "17:00"

df = pd.read_csv(os.path.join(DATA_ROOT, f"CBOT_MINI_YM1_{date}.csv"), index_col=0, parse_dates=True)
df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)

ds = pd.Timestamp(f"{date} {start_t}", tz=_EST)
de = pd.Timestamp(f"{date} {end_t}",   tz=_EST)
df = df[(df.index >= ds) & (df.index <= de)]

config = AlgoConfig(warmup_minutes=12, steep_angle_threshold=70.0,
                    proximity_points=15.0, min_reversal_minutes=0,
                    min_entry_angle=30.0)
algo_df = run_trading_algo_fast(df, date, start_t, end_t, config=config)

signals = algo_df[algo_df["signal"].isin(["BUY", "SELL"])]
print(f"\nDate: {date}  {start_t}-{end_t}")
print(f"Bars: {len(algo_df)}  Signals: {len(signals)}")
for ts, row in signals.iterrows():
    sig   = row["signal"]
    price = row["buy_price"] if sig == "BUY" else row["sell_price"]
    liq   = " [LIQ]" if row["is_liquidation"] else ""
    tp    = " [TP]"  if row["partial_tp"] else ""
    print(f"  {ts.strftime('%H:%M')}  {sig:4s} @ {int(price)}{liq}{tp}")
print(f"\nFinal session_pl: {algo_df['session_pl'].iloc[-1]:+.0f} pts  /  ${algo_df['session_pl'].iloc[-1]*5:+,.0f}")

# Also print bar-level detail around 9:50-10:10 to diagnose the liquidation
print("\n--- Bar detail 9:50-10:10 ---")
mask = (algo_df.index >= pd.Timestamp(f"{date} 09:50", tz=_EST)) & \
       (algo_df.index <= pd.Timestamp(f"{date} 10:10", tz=_EST))
cols = ["open","high","low","close","signal","buy_price","sell_price","is_liquidation","partial_tp","session_pl"]
print(algo_df.loc[mask, [c for c in cols if c in algo_df.columns]].to_string())
