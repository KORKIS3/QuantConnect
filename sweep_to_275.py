"""Sweep key parameters to find the path to 275 pts/day.

Tests combinations of:
- Stop loss: 50, 60, 70
- Session end: 11:00, 12:00, 13:00, 14:00, 17:00
- Steep angle: 50, 60, 70, 80
- Warmup: 8, 10, 12
- Proximity: 10, 15, 20, 25
"""
import os, time
import pandas as pd
import numpy as np
import pytz
from TradingAlgoFast import AlgoConfig, run_trading_algo_fast

_EST = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")


def run_with_sl(config, stop_loss, end_time_str):
    """Run backtest with post-hoc filter + hard stop loss, return avg pts/day."""
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

            end_ts = pd.Timestamp(f"{target_date} {end_time_str}", tz=_EST)
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

            # Replay with SL
            closes = sliced["Close"].values.astype(float)
            highs = sliced["High"].values.astype(float)
            lows = sliced["Low"].values.astype(float)
            times = sliced.index
            sig_idx = 0
            total_pl = 0.0
            pos = "flat"
            ep = None
            partial_taken = False

            for i in range(len(sliced)):
                # Stop loss check
                if pos != "flat" and ep is not None and stop_loss > 0:
                    if pos == "long":
                        adverse = ep - lows[i]
                    else:
                        adverse = highs[i] - ep
                    if adverse >= stop_loss:
                        # Stopped out
                        if partial_taken:
                            total_pl += -stop_loss
                        else:
                            total_pl += -stop_loss * 2
                        pos = "flat"
                        ep = None
                        partial_taken = False
                        continue

                # Partial TP
                if pos != "flat" and ep is not None and not partial_taken:
                    unrealized = (closes[i] - ep) if pos == "long" else (ep - closes[i])
                    if unrealized >= 50.0:
                        total_pl += unrealized
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


# Sweep
print("=" * 80, flush=True)
print("PARAMETER SWEEP — Finding the path to 275 pts/day", flush=True)
print("=" * 80, flush=True)

results = []

# Key combinations to test
steep_angles = [50, 60, 70, 80]
warmups = [8, 10, 12]
proximities = [10, 15, 20, 25]
stop_losses = [50, 60, 70]
end_times = ["12:00", "14:00", "17:00"]

# First pass: find best steep/warmup/proximity with fixed SL=60, end=17:00
print("\n--- PASS 1: Steep angle x Warmup x Proximity (SL=60, end=17:00) ---", flush=True)
print(f"{'Steep':<8}{'Warmup':<9}{'Prox':<7}{'Avg/Day':<10}{'Days':<7}{'Win%':<7}", flush=True)
print("-" * 50, flush=True)

best = (0, None)
for steep in steep_angles:
    for warmup in warmups:
        for prox in proximities:
            cfg = AlgoConfig(
                warmup_minutes=warmup,
                steep_angle_threshold=float(steep),
                proximity_points=float(prox),
                min_reversal_minutes=0,
                min_entry_angle=0.0,
                partial_tp_pts=50.0,
                wm_shield_distance=12.0,
                swing_anchor_threshold=10.0,
                cushion_points=0.0,
                limit_expiry_bars=5,
            )
            avg, days, win_pct = run_with_sl(cfg, 60, "17:00")
            print(f"{steep:<8}{warmup:<9}{prox:<7}{avg:<+10.1f}{days:<7}{win_pct:<6.1f}%", flush=True)
            results.append((steep, warmup, prox, 60, "17:00", avg, days, win_pct))
            if avg > best[0]:
                best = (avg, (steep, warmup, prox))

print(f"\nBest combo: steep={best[1][0]}, warmup={best[1][1]}, prox={best[1][2]} -> {best[0]:+.1f} pts/day", flush=True)

# Second pass: test best combo with different SL and end times
print(f"\n--- PASS 2: Stop loss x End time (using best combo) ---", flush=True)
best_steep, best_warmup, best_prox = best[1]
print(f"{'SL':<6}{'End':<8}{'Avg/Day':<10}{'Days':<7}{'Win%':<7}", flush=True)
print("-" * 40, flush=True)

for sl in stop_losses:
    for et in end_times:
        cfg = AlgoConfig(
            warmup_minutes=best_warmup,
            steep_angle_threshold=float(best_steep),
            proximity_points=float(best_prox),
            min_reversal_minutes=0,
            min_entry_angle=0.0,
            partial_tp_pts=50.0,
            wm_shield_distance=12.0,
            swing_anchor_threshold=10.0,
            cushion_points=0.0,
            limit_expiry_bars=5,
        )
        avg, days, win_pct = run_with_sl(cfg, sl, et)
        print(f"{sl:<6}{et:<8}{avg:<+10.1f}{days:<7}{win_pct:<6.1f}%", flush=True)
