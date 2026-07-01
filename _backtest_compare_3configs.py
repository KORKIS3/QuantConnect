"""Compare 3 AlgoConfig variants across all available days (full day session 9:30-17:00).

Config A: "Interactive Graph" (run_chart.py)
Config B: "Live IB" (IBDataBridge default)
Config C: "Proven Backtest" (Backtest2Year.py / steering file)
"""

import os, time
import pandas as pd, pytz, numpy as np
from TradingAlgoFast import AlgoConfig, run_trading_algo_fast

_EST = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")
_CONTRACTS = 2
_MULTIPLIER = 5

# --- The 3 configs ---

CONFIG_A = AlgoConfig(
    warmup_minutes=7,
    steep_angle_threshold=90.0,
    proximity_points=4.0,
    min_reversal_minutes=0,
    min_entry_angle=0.0,
    partial_tp_pts=50.0,
    wm_shield_distance=0.0,
    swing_anchor_threshold=25.0,
)

CONFIG_B = AlgoConfig(
    warmup_minutes=7,
    steep_angle_threshold=90.0,
    proximity_points=4.0,
    min_reversal_minutes=0,
    min_entry_angle=0.0,
    partial_tp_pts=50.0,
    spike_profit_pts=100.0,
    spike_profit_bars=9,
    wm_shield_distance=0.0,
    swing_anchor_threshold=10.0,
    cushion_points=0.0,
    limit_expiry_bars=5,
)

CONFIG_C = AlgoConfig(
    warmup_minutes=7,
    steep_angle_threshold=90.0,
    proximity_points=4.0,
    min_reversal_minutes=0,
    min_entry_angle=0.0,
    partial_tp_pts=50.0,
    wm_shield_distance=0.0,
    swing_anchor_threshold=10.0,
    cushion_points=40.0,
    limit_expiry_bars=5,
)

CONFIG_D = AlgoConfig(
    warmup_minutes=12,
    steep_angle_threshold=70.0,
    proximity_points=15.0,
    min_reversal_minutes=0,
    min_entry_angle=30.0,
    partial_tp_pts=50.0,
    wm_shield_distance=12.0,
    swing_anchor_threshold=25.0,
)

CONFIGS = {
    "A: Interactive Graph": CONFIG_A,
    "B: Live IB": CONFIG_B,
    "C: Proven Backtest": CONFIG_C,
    "D: Steering 275/day": CONFIG_D,
}


def run_one_day(fpath, target_date, config):
    """Run algo on one day, return session P/L at 17:00 or None on failure."""
    try:
        df = pd.read_csv(fpath, index_col=0, parse_dates=True)
        df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
        if len(df) < 10:
            return None
        day_start = pd.Timestamp(f"{target_date} 09:30", tz=_EST)
        day_end = pd.Timestamp(f"{target_date} 16:59", tz=_EST)
        day_data = df[(df.index >= day_start) & (df.index <= day_end)]
        if len(day_data) < 15:
            return None
        if (day_data[["Open", "High", "Low", "Close"]] <= 0).any().any():
            return None
        if day_data["High"].max() == day_data["Low"].min():
            return None
        if day_data["Volume"].sum() < 100:
            return None
        algo_df = run_trading_algo_fast(day_data, target_date, "09:30", "17:00", config=config)
        end_ts = pd.Timestamp(f"{target_date} 17:00", tz=_EST)
        sliced = algo_df[(algo_df.index >= day_start) & (algo_df.index <= end_ts)]
        if len(sliced) < 2:
            return None
        pl = float(sliced["session_pl"].iloc[-1])
        return pl
    except Exception:
        return None


def main():
    csv_files = sorted([f for f in os.listdir(_DATA_ROOT)
                        if f.startswith("CBOT_MINI_YM1_") and f.endswith(".csv")])
    total = len(csv_files)
    print(f"\nBacktest comparison: {total} days, full day 9:30-17:00, 2 contracts")
    print(f"{'='*80}\n")

    # Print config differences
    print("Config A (Interactive Graph / run_chart.py):")
    print(f"  swing_anchor=25, spike_profit=100/5bars, cushion=0")
    print("Config B (Live IB / IBDataBridge):")
    print(f"  swing_anchor=10, spike_profit=100/9bars, cushion=0")
    print("Config C (Proven Backtest / Backtest2Year.py):")
    print(f"  swing_anchor=10, spike_profit=100/5bars, cushion=40")
    print("Config D (Steering 275/day):")
    print(f"  warmup=12, steep=70, proximity=15, min_entry_angle=30, wm_shield=12, swing_anchor=25")
    print(f"\n{'='*80}\n")

    results = {name: [] for name in CONFIGS}
    t_start = time.time()

    for i, fname in enumerate(csv_files):
        target_date = fname.replace("CBOT_MINI_YM1_", "").replace(".csv", "")
        fpath = os.path.join(_DATA_ROOT, fname)

        day_results = {}
        for name, config in CONFIGS.items():
            pl = run_one_day(fpath, target_date, config)
            day_results[name] = pl

        # Only count day if ALL configs returned a result
        if all(v is not None for v in day_results.values()):
            for name, pl in day_results.items():
                results[name].append(pl)

        if (i + 1) % 50 == 0 or (i + 1) == total:
            elapsed = time.time() - t_start
            print(f"  [{i+1}/{total}] processed ({elapsed:.0f}s)")

    n_days = len(results[list(CONFIGS.keys())[0]])
    elapsed = time.time() - t_start
    print(f"\n{'='*80}")
    print(f"RESULTS: {n_days} valid days, {elapsed:.0f}s elapsed")
    print(f"{'='*80}\n")

    print(f"{'Config':<28} {'Total Pts':>10} {'Avg/Day':>8} {'Win%':>7} {'Win Days':>9} {'Lose Days':>10} {'P/L USD':>12}")
    print("-" * 95)
    for name in CONFIGS:
        pls = results[name]
        total_pts = sum(pls)
        avg = np.mean(pls) if pls else 0
        wins = sum(1 for p in pls if p > 0)
        losses = sum(1 for p in pls if p <= 0)
        win_pct = wins / len(pls) * 100 if pls else 0
        usd = total_pts * _MULTIPLIER
        print(f"{name:<28} {total_pts:>+10.0f} {avg:>+7.1f} {win_pct:>6.1f}% {wins:>9} {losses:>10} ${usd:>11,.0f}")

    print()


if __name__ == "__main__":
    main()
