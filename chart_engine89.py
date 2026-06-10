"""Interactive chart with Engine 89 config for a specific day.
Usage: python chart_engine89.py 2026-05-12
"""
import sys, os
import pandas as pd, pytz
import matplotlib
matplotlib.use("TkAgg")

from TradingAlgoFast import run_trading_algo_fast, AlgoConfig
from plotFigure import plot_intraday_data

_EST = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")

date = sys.argv[1] if len(sys.argv) > 1 else "2026-05-12"
start_t = "09:30"
end_t = "17:00"

fname = os.path.join(_DATA_ROOT, f"CBOT_MINI_YM1_{date}.csv")
if not os.path.exists(fname):
    print(f"File not found: {fname}")
    sys.exit(1)

df = pd.read_csv(fname, index_col=0, parse_dates=True)
df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)

ds = pd.Timestamp(f"{date} {start_t}", tz=_EST)
de = pd.Timestamp(f"{date} {end_t}", tz=_EST)
df = df[(df.index >= ds) & (df.index <= de)]

print(f"Running Engine 89 chart for {date} ({len(df)} bars)...")

# Engine 89 config
config = AlgoConfig(
    warmup_minutes=12,
    steep_angle_threshold=70.0,
    proximity_points=15.0,
    min_reversal_minutes=0,
    min_entry_angle=0.0,
    partial_tp_pts=50.0,
    wm_shield_distance=12.0,
    swing_anchor_threshold=10.0,
    cushion_points=0.0,
    limit_expiry_bars=5,
)

algo_df = run_trading_algo_fast(df, date, start_t, end_t, config=config)
print(f"Session P/L: {algo_df['session_pl'].iloc[-1]:+.0f} pts")

# Show trades
trades = algo_df[algo_df['signal'].isin(['BUY', 'SELL'])]
for ts, row in trades.iterrows():
    sig = row['signal']
    price = row['buy_price'] if sig == 'BUY' else row['sell_price']
    liq = " (liq)" if row.get('is_liquidation', False) else ""
    print(f"  {ts.strftime('%H:%M')} {sig} @ {price:.0f}{liq}")

plot_intraday_data(algo_df, date, start_t, end_t)
