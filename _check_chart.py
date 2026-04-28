import os, pandas as pd, pytz, matplotlib
matplotlib.use("TkAgg")
from TradingAlgoFast import run_trading_algo_fast, AlgoConfig
from plotFigure import plot_intraday_data

_EST = pytz.timezone("US/Eastern")
DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")

date    = "2026-04-07"
start_t = "09:30"
end_t   = "11:30"

df = pd.read_csv(os.path.join(DATA_ROOT, f"CBOT_MINI_YM1_{date}.csv"), index_col=0, parse_dates=True)
df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)

ds = pd.Timestamp(f"{date} {start_t}", tz=_EST)
de = pd.Timestamp(f"{date} {end_t}",   tz=_EST)
df = df[(df.index >= ds) & (df.index <= de)]

config = AlgoConfig(
    warmup_minutes=5, steep_angle_threshold=67.5, proximity_points=7.0,
    min_reversal_minutes=0, min_entry_angle=0.0,
    partial_tp_pts=50.0, wm_shield_distance=0.0,
    swing_anchor_threshold=5.0, spike_profit_pts=50.0, spike_profit_bars=10,
)
algo_df = run_trading_algo_fast(df, date, start_t, end_t, config=config)

signals = algo_df[algo_df["signal"].isin(["BUY", "SELL"])]
print(f"\nDate: {date}  {start_t}-{end_t}")
print(f"Bars: {len(algo_df)}  Signals: {len(signals)}")
for ts, row in signals.iterrows():
    sig   = row["signal"]
    price = row["buy_price"] if sig == "BUY" else row["sell_price"]
    liq   = " [LIQ]" if row["is_liquidation"] else ""
    print(f"  {ts.strftime('%H:%M')}  {sig:4s} @ {int(price)}   session_pl: {algo_df.loc[ts,'session_pl']:+.0f} pts{liq}")
print(f"\nFinal session_pl: {algo_df['session_pl'].iloc[-1]:+.0f} pts  /  ${algo_df['session_pl'].iloc[-1]*5:+,.0f}")

plot_intraday_data(algo_df, date, start_t, end_t)
