import os
import pandas as pd
import pytz
from TradingAlgoFast import run_trading_algo_fast, AlgoConfig
from _sweep_trailing import _apply_trailing

_EST = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.expanduser("~/Desktop/2YearsData/full_day")
_TRACKING  = os.path.expanduser("~/Desktop/IB_Live/tracking")

d = "2026-04-23"

config = AlgoConfig(
    warmup_minutes=12, steep_angle_threshold=70.0, proximity_points=15.0,
    min_reversal_minutes=0, min_entry_angle=30.0, partial_tp_pts=50.0,
    spike_profit_pts=99999.0,
)

# --- Backtest (historical CSV) ---
fpath = os.path.join(_DATA_ROOT, f"CBOT_MINI_YM1_{d}.csv")
df = pd.read_csv(fpath, index_col=0, parse_dates=True)
df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
start_ts = pd.Timestamp(f"{d} 09:30", tz=_EST)
end_ts   = pd.Timestamp(f"{d} 17:00", tz=_EST)
day_data = df[(df.index >= start_ts) & (df.index <= end_ts)]
algo_df  = run_trading_algo_fast(day_data, d, "09:30", "17:00", config=config)
trail = dict(threshold=50, base_angle=50, mid_angle=60, high_angle=70,
             mid_profit=100, high_profit=150, lock_anchor=True, progressive=False)
bt_pl = _apply_trailing(algo_df, start_ts, end_ts, **trail) or 0.0
bt_trades = algo_df[algo_df["signal"].isin(["BUY","SELL"])]

print(f"=== BACKTEST {d} ===")
print(f"Total P/L: {bt_pl:+.0f} pts")
for ts, row in bt_trades.iterrows():
    liq = " (liq)" if row.get("is_liquidation") else ""
    print(f"  {ts.strftime('%H:%M')}  {row['signal']}  @{row['Close']:.0f}  pl={row['pl']:+.0f}{liq}")

# --- Live tracking CSV ---
print(f"\n=== LIVE TRACKING {d} ===")
csv_path = os.path.join(_TRACKING, f"YM_tracking_{d}.csv")
if os.path.exists(csv_path):
    live_df = pd.read_csv(csv_path, index_col=0, parse_dates=True)
    live_df.index = pd.to_datetime(live_df.index, utc=True).tz_convert(_EST)
    live_trades = live_df[live_df["signal"].isin(["BUY","SELL"])]
    last_pl = live_df["pl"].iloc[-1]
    print(f"Total P/L: {last_pl:+.0f} pts")
    for ts, row in live_trades.iterrows():
        liq = " (liq)" if row.get("is_liquidation") else ""
        print(f"  {ts.strftime('%H:%M')}  {row['signal']}  @{row['Close']:.0f}  pl={row['pl']:+.0f}{liq}")
else:
    print("No tracking CSV found")
