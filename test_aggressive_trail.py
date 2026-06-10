"""Test aggressive trailing stop: activate immediately, 40pt trail distance.
Compare against Engine 89 baseline."""
import os
import pandas as pd
import numpy as np
import pytz
from TradingAlgoFast import AlgoConfig, run_trading_algo_fast

_EST = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")

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


def backtest_with_management(stop_loss, trail_distance, trail_activate):
    """Run full backtest with post-hoc filter + SL + trailing stop."""
    csv_files = sorted([f for f in os.listdir(_DATA_ROOT)
                        if f.startswith("CBOT_MINI_YM1_") and f.endswith(".csv")])

    daily_pls = []
    for fname in csv_files:
        target_date = fname.replace("CBOT_MINI_YM1_", "").replace(".csv", "")
        fpath = os.path.join(_DATA_ROOT, fname)

        try:
            df = pd.read_csv(fpath, index_col=0, parse_dates=True)
            df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
            if len(df) < 15:
                continue
            if (df[["Open", "High", "Low", "Close"]] <= 0).any().any():
                continue
            if df["High"].max() == df["Low"].min():
                continue
            if df["Volume"].sum() < 100:
                continue

            day_start = pd.Timestamp(f"{target_date} 09:30", tz=_EST)
            day_end = pd.Timestamp(f"{target_date} 16:59", tz=_EST)
            day_data = df[(df.index >= day_start) & (df.index <= day_end)]
            if len(day_data) < 15:
                continue

            algo_df = run_trading_algo_fast(day_data, target_date, "09:30", "17:00", config=config)
            end_ts = pd.Timestamp(f"{target_date} 17:00", tz=_EST)
            sliced = algo_df[(algo_df.index >= day_start) & (algo_df.index <= end_ts)]
            if len(sliced) < 2:
                continue

            rows = sliced[sliced["signal"].isin(["BUY", "SELL"])]
            if rows.empty:
                continue

            # Post-hoc 10-min filter
            filtered = []
            for ts, row in rows.iterrows():
                sig = row["signal"]
                price = float(row["buy_price"] if sig == "BUY" else row["sell_price"])
                if not filtered:
                    filtered.append((ts, sig, price))
                    continue
                last_ts, last_sig, _ = filtered[-1]
                if last_sig != sig:
                    if (ts - last_ts).total_seconds() / 60 >= 10:
                        filtered.append((ts, sig, price))
                else:
                    filtered.append((ts, sig, price))

            if not filtered:
                continue

            # Replay with SL + trailing
            closes = sliced["Close"].values.astype(float)
            highs = sliced["High"].values.astype(float)
            lows = sliced["Low"].values.astype(float)
            times = sliced.index
            sig_idx = 0
            total_pl = 0.0
            pos = "flat"
            ep = None
            partial_taken = False
            max_favorable = 0.0  # track best unrealized for trailing

            for i in range(len(sliced)):
                if pos != "flat" and ep is not None:
                    # Calculate current unrealized (using close for trailing, high/low for SL)
                    if pos == "long":
                        unrealized_close = closes[i] - ep
                        adverse = ep - lows[i]
                    else:
                        unrealized_close = ep - closes[i]
                        adverse = highs[i] - ep

                    # Hard stop loss
                    if stop_loss > 0 and adverse >= stop_loss:
                        if partial_taken:
                            total_pl += -stop_loss
                        else:
                            total_pl += -stop_loss * 2
                        pos = "flat"
                        ep = None
                        partial_taken = False
                        max_favorable = 0.0
                        continue

                    # Track max favorable excursion
                    if unrealized_close > max_favorable:
                        max_favorable = unrealized_close

                    # Trailing stop: once unrealized hits trail_activate, trail at trail_distance from peak
                    if trail_activate > 0 and max_favorable >= trail_activate:
                        drawback = max_favorable - unrealized_close
                        if drawback >= trail_distance:
                            # Trailed out — exit at (max_favorable - trail_distance)
                            exit_pl = max_favorable - trail_distance
                            if partial_taken:
                                total_pl += exit_pl
                            else:
                                total_pl += exit_pl * 2
                            pos = "flat"
                            ep = None
                            partial_taken = False
                            max_favorable = 0.0
                            continue

                    # Partial TP
                    if not partial_taken and unrealized_close >= 50.0:
                        total_pl += unrealized_close
                        partial_taken = True

                # Signal check
                if sig_idx < len(filtered) and times[i] == filtered[sig_idx][0]:
                    ts, sig, price = filtered[sig_idx]
                    sig_idx += 1

                    if pos == "long" and sig == "SELL":
                        pl = price - ep
                        if partial_taken:
                            total_pl += pl
                        else:
                            total_pl += pl * 2
                    elif pos == "short" and sig == "BUY":
                        pl = ep - price
                        if partial_taken:
                            total_pl += pl
                        else:
                            total_pl += pl * 2

                    if sig == "BUY":
                        pos, ep = "long", price
                    else:
                        pos, ep = "short", price
                    partial_taken = False
                    max_favorable = 0.0

            # Close at session end
            if pos != "flat" and ep is not None:
                final_close = closes[-1]
                pl = (final_close - ep) if pos == "long" else (ep - final_close)
                if partial_taken:
                    total_pl += pl
                else:
                    total_pl += pl * 2

            if total_pl != 0.0:
                daily_pls.append(total_pl)

        except Exception:
            continue

    if not daily_pls:
        return 0.0, 0, 0.0
    arr = np.array(daily_pls)
    win_pct = (arr > 0).sum() / len(arr) * 100
    return arr.mean(), len(arr), win_pct


print("=" * 70, flush=True)
print("TRADE MANAGEMENT SWEEP — SL + Trailing Stop combinations", flush=True)
print("=" * 70, flush=True)
print(f"{'SL':<6}{'Trail Act':<11}{'Trail Dist':<12}{'Avg/Day':<10}{'Days':<7}{'Win%':<7}", flush=True)
print("-" * 55, flush=True)

# Test combinations
tests = [
    # (stop_loss, trail_activate, trail_distance)
    (60, 0, 0),          # Engine 89 baseline (SL only, no custom trail)
    (60, 20, 30),        # Tight trail: activate at +20, trail 30 back
    (60, 30, 40),        # Moderate: activate at +30, trail 40
    (60, 50, 40),        # Current-ish: activate at +50, trail 40
    (60, 50, 30),        # Tighter trail from +50
    (70, 30, 40),        # Looser SL, moderate trail
    (50, 20, 30),        # Tighter everything
    (80, 50, 50),        # Loose everything
    (60, 0, 0),          # No trail (just SL) — confirm baseline
    (0, 30, 40),         # No SL, just trail
    (60, 40, 30),        # Activate at 40, trail 30
    (60, 60, 40),        # Activate at 60, trail 40
]

for sl, ta, td in tests:
    avg, days, win_pct = backtest_with_management(sl, td, ta)
    trail_str = f"{ta}/{td}" if ta > 0 else "none"
    print(f"{sl:<6}{trail_str:<11}{'':<12}{avg:<+10.1f}{days:<7}{win_pct:<6.1f}%", flush=True)
