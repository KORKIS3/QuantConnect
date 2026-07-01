"""Debug: show first 20 bars of algo output for 06/23 to see why 09:33 SELL is missing."""
import pandas as pd, pytz, os
from TradingAlgoFast import AlgoConfig, run_trading_algo_fast

config = AlgoConfig(
    warmup_minutes=7, steep_angle_threshold=90.0, proximity_points=4.0,
    min_reversal_minutes=0, min_entry_angle=0.0, partial_tp_pts=50.0,
    spike_profit_pts=100.0, spike_profit_bars=9, wm_shield_distance=0.0,
    swing_anchor_threshold=10.0, num_contracts=2, cushion_points=0.0, limit_expiry_bars=5,
)
EST = pytz.timezone("US/Eastern")
fpath = os.path.expanduser("~/Desktop/2YearsData/full_day/CBOT_MINI_YM1_2026-06-23.csv")
df = pd.read_csv(fpath, index_col=0, parse_dates=True)
df.index = pd.to_datetime(df.index, utc=True).tz_convert(EST)
day_start = pd.Timestamp("2026-06-23 09:30", tz=EST)
day_end = pd.Timestamp("2026-06-23 16:59", tz=EST)
day_data = df[(df.index >= day_start) & (day_end >= df.index)]

algo_df = run_trading_algo_fast(day_data, "2026-06-23", "09:30", "17:00", config=config)

# Show first 20 bars
print("First 20 bars of algo output:")
print(f"{'Time':<6} {'Close':>7} {'Signal':<6} {'Position':<6} {'P/L':>6} {'BuyP':>7} {'SellP':>7}")
print("-" * 55)
for idx, row in algo_df.head(20).iterrows():
    t = idx.strftime("%H:%M")
    sig = row["signal"] if row["signal"] else ""
    pos = row["position"]
    pl = row["session_pl"]
    bp = f"{row['buy_price']:.0f}" if pd.notna(row.get("buy_price")) and row.get("buy_price", 0) > 0 else ""
    sp = f"{row['sell_price']:.0f}" if pd.notna(row.get("sell_price")) and row.get("sell_price", 0) > 0 else ""
    print(f"{t:<6} {row['Close']:>7.0f} {sig:<6} {pos:<6} {pl:>6.0f} {bp:>7} {sp:>7}")

# Also show all signal trades
print("\nAll signal trades:")
trades = algo_df[algo_df["signal"].isin(["BUY", "SELL"])]
for idx, row in trades.iterrows():
    t = idx.strftime("%H:%M")
    sig = row["signal"]
    price = row["buy_price"] if sig == "BUY" else row["sell_price"]
    print(f"  {t} {sig} @ {price:.0f}")
print(f"\nTotal trades: {len(trades)}")
print(f"Final P/L: {algo_df['session_pl'].iloc[-1]:.0f}")

# Now run with warmup=3 to see if the 09:33 SELL appears
print("\n\n=== WITH warmup_minutes=3 ===")
config2 = AlgoConfig(
    warmup_minutes=3, steep_angle_threshold=90.0, proximity_points=4.0,
    min_reversal_minutes=0, min_entry_angle=0.0, partial_tp_pts=50.0,
    spike_profit_pts=100.0, spike_profit_bars=9, wm_shield_distance=0.0,
    swing_anchor_threshold=10.0, num_contracts=2, cushion_points=0.0, limit_expiry_bars=5,
)
algo_df2 = run_trading_algo_fast(day_data, "2026-06-23", "09:30", "17:00", config=config2)
trades2 = algo_df2[algo_df2["signal"].isin(["BUY", "SELL"])]
print("First 5 trades:")
for idx, row in trades2.head(5).iterrows():
    t = idx.strftime("%H:%M")
    sig = row["signal"]
    price = row["buy_price"] if sig == "BUY" else row["sell_price"]
    print(f"  {t} {sig} @ {price:.0f}")
print(f"Total trades: {len(trades2)}, Final P/L: {algo_df2['session_pl'].iloc[-1]:.0f}")
