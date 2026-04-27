"""Compare two AlgoConfig setups on a single day."""
import os, pytz, pandas as pd
from TradingAlgoFast import AlgoConfig, run_trading_algo_fast

_EST      = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")

DATE = "2026-04-24"

# Config A — proven 265.9 pts/day (from steering doc, 2026-04-22)
config_a = AlgoConfig(
    warmup_minutes=12,
    steep_angle_threshold=70.0,
    proximity_points=15.0,
    min_reversal_minutes=0,
    min_entry_angle=30.0,
    partial_tp_pts=50.0,
    wm_shield_distance=12.0,
)

# Config B — current backtest (missing min_entry_angle)
config_b = AlgoConfig(
    warmup_minutes=12,
    steep_angle_threshold=70.0,
    proximity_points=15.0,
    min_reversal_minutes=0,
    min_entry_angle=0.0,
    partial_tp_pts=50.0,
    wm_shield_distance=12.0,
)

def run_and_print(label, config):
    fpath = os.path.join(_DATA_ROOT, f"CBOT_MINI_YM1_{DATE}.csv")
    df = pd.read_csv(fpath, index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)

    day_start = pd.Timestamp(f"{DATE} 09:30", tz=_EST)
    day_end   = pd.Timestamp(f"{DATE} 16:59", tz=_EST)
    day_data  = df[(df.index >= day_start) & (df.index <= day_end)]

    result = run_trading_algo_fast(day_data, DATE, "09:30", "17:00", config=config)

    print(f"  Signal unique values: {result['signal'].unique()[:10]}")
    print(f"  buy_price non-null: {result['buy_price'].notna().sum()}")
    print(f"  sell_price non-null: {result['sell_price'].notna().sum()}")
    signals = result[result["signal"].isin(["BUY", "SELL"])].copy()

    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    print(f"  {'Time':<8} {'Signal':<6} {'Price':>8}  {'partial_tp'}")
    print(f"  {'-'*45}")

    pos, ep = "flat", None
    total_pts = 0
    for ts, row in signals.iterrows():
        sig = row["signal"]
        price = float(row["buy_price"] if sig == "BUY" else row["sell_price"])
        partial = result.loc[ts, "partial_tp"] if "partial_tp" in result.columns else False
        pl_str = ""
        if pos == "long" and sig == "SELL":
            pl = price - ep
            total_pts += pl
            pl_str = f"  → close long  {pl:+.0f} pts"
        elif pos == "short" and sig == "BUY":
            pl = ep - price
            total_pts += pl
            pl_str = f"  → close short {pl:+.0f} pts"
        print(f"  {ts.strftime('%H:%M'):<8} {sig:<6} {price:>8.0f}{pl_str}")
        if sig == "BUY":  pos, ep = "long",  price
        else:             pos, ep = "short", price

    # close open position at end
    if pos != "flat" and ep is not None:
        last = float(result["Close"].iloc[-1])
        pl = (last - ep) if pos == "long" else (ep - last)
        total_pts += pl
        print(f"  {'17:00':<8} {'EOD':<6} {last:>8.0f}  → close {pos} {pl:+.0f} pts")

    print(f"\n  Total trades: {len(signals)}   Total pts: {total_pts:+.0f}")

run_and_print("Config A — Proven (min_entry_angle=30)", config_a)
run_and_print("Config B — Current backtest (min_entry_angle=0)", config_b)
