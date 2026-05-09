"""Run May 8th 2026 and save the tracking CSV."""
import os
import pandas as pd
import pytz
from TradingAlgoFast import AlgoConfig, run_trading_algo_fast

_EST = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")

target_date = "2026-05-08"
fname = f"CBOT_MINI_YM1_{target_date}.csv"
fpath = os.path.join(_DATA_ROOT, fname)

# Identical config to live IBDataBridge
config = AlgoConfig(
    warmup_minutes=12,
    steep_angle_threshold=70.0,
    proximity_points=15.0,
    min_reversal_minutes=0,
    min_entry_angle=30.0,
    partial_tp_pts=50.0,
    spike_profit_pts=100.0,
    spike_profit_bars=5,
    wm_shield_distance=12.0,
    steep_line_reentry=True,
)

print(f"Loading {fname}...")
df = pd.read_csv(fpath, index_col=0, parse_dates=True)
df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)

day_start = pd.Timestamp(f"{target_date} 09:30", tz=_EST)
day_end = pd.Timestamp(f"{target_date} 16:59", tz=_EST)
day_data = df[(df.index >= day_start) & (df.index <= day_end)]

print(f"Running algo on {len(day_data)} bars (9:30-17:00)...")
algo_df = run_trading_algo_fast(day_data, target_date, "09:30", "17:00", config=config)

# Save to tracking folder
output_path = os.path.join(os.path.expanduser("~"), "Desktop", "IB_Live", "tracking", f"YM_tracking_{target_date}_BACKTEST.csv")
algo_df.to_csv(output_path)
print(f"\nSaved to: {output_path}")

# Show final P/L
final_pl = algo_df["session_pl"].iloc[-1]
print(f"Final P/L: {final_pl:.2f} pts (${final_pl * 5:.2f})")

# Show all trades
trades = algo_df[algo_df["signal"] != ""].copy()
if len(trades) > 0:
    print(f"\nTrades ({len(trades)}):")
    for idx, row in trades.iterrows():
        sig = row["signal"]
        price = row["buy_price"] if sig == "BUY" else row["sell_price"]
        liq = " (liquidation)" if row["is_liquidation"] else ""
        pos = row["position"]
        spl = row["session_pl"]
        print(f"  {idx.strftime('%H:%M')} {sig:4s} @ {price:.0f}{liq} → pos={pos}, session_pl={spl:.2f}")
else:
    print("\nNo trades generated")
