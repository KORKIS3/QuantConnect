import os, pandas as pd, pytz, matplotlib
matplotlib.use("TkAgg")
from TradingAlgoFast import run_trading_algo_fast, AlgoConfig
from plotFigure import ChartPlotter

_EST = pytz.timezone("US/Eastern")

date    = "2026-05-05"
start_t = "09:30"
end_t   = "17:00"

tracking_path = os.path.join(os.path.expanduser("~"), "Desktop", "IB_Live", "tracking", "YM_tracking_2026-05-05.csv")
df = pd.read_csv(tracking_path, index_col=0, parse_dates=True)
df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
ds = pd.Timestamp(f"{date} {start_t}", tz=_EST)
de = pd.Timestamp(f"{date} {end_t}",   tz=_EST)
df = df[(df.index >= ds) & (df.index <= de)]

config = AlgoConfig(
    warmup_minutes=12, steep_angle_threshold=70.0,
    proximity_points=15.0, min_reversal_minutes=0,
    min_entry_angle=30.0, partial_tp_pts=50.0,
    spike_profit_pts=100.0, spike_profit_bars=5,
    wm_shield_distance=12.0,
)

algo_df = run_trading_algo_fast(df, date, start_t, end_t, config=config)

signals = algo_df[algo_df["signal"].isin(["BUY", "SELL"])]
print(f"\nDate: {date}  Bars: {len(algo_df)}  Signals: {len(signals)}")
for ts, row in signals.iterrows():
    sig   = row["signal"]
    price = row["buy_price"] if sig == "BUY" else row["sell_price"]
    liq   = " [LIQ]"        if row["is_liquidation"] else ""
    tp    = " [PARTIAL_TP]" if row["partial_tp"]      else ""
    print(f"  {ts.strftime('%H:%M')}  {sig:4s} @ {int(price)}{liq}{tp}")
print(f"\nFinal P/L: {algo_df['session_pl'].iloc[-1]:+.0f} pts  /  ${algo_df['session_pl'].iloc[-1]*5:+,.0f}\n")

plotter = ChartPlotter(algo_df, date, start_t, end_t, output_dir="", batch_mode=False)
plotter.show()
