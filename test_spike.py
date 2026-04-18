"""A/B test: spike profit take — exit on rapid moves in your favor.

Two interpretations tested:
A) "bar move" — any single bar during the trade moves X+ pts in your favor (close-to-close)
B) "unrealized" — unrealized profit from entry reaches X+ pts within N bars of entry
"""
import os
import pandas as pd, pytz, numpy as np
from TradingAlgo import AlgoConfig
from TradingAlgoFast import run_trading_algo_fast

_EST = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")

config = AlgoConfig(warmup_minutes=12, steep_angle_threshold=70.0,
                    proximity_points=15.0, min_reversal_minutes=0, max_loss_per_trade=0,
                    confirmation_bars=0)

csv_files = sorted([f for f in os.listdir(_DATA_ROOT) if f.endswith(".csv")])
print(f"Spike profit take test on {len(csv_files)} days...\n", flush=True)


def run_backtest(algo_df, spike_pts, spike_bars, mode="unrealized"):
    """Run post-hoc 10-min filter + spike profit take.
    mode="unrealized": exit if unrealized profit >= spike_pts within spike_bars of entry
    mode="bar_move":   exit if any single bar moves >= spike_pts in your favor (spike_bars ignored)
    spike_bars=0: baseline, no spike exit
    """
    rows = algo_df[algo_df["signal"].isin(["BUY", "SELL"])]
    if rows.empty:
        return None

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
        return None

    if spike_bars == 0 and mode == "unrealized":
        # Baseline — no spike exit
        last_close = float(algo_df["Close"].iloc[-1])
        tpls = []
        pos, ep = "flat", None
        for ts, sig, price in filtered:
            if sig == "BUY":
                if pos == "short" and ep:
                    tpls.append(ep - price)
                pos, ep = "long", price
            elif sig == "SELL":
                if pos == "long" and ep:
                    tpls.append(price - ep)
                pos, ep = "short", price
        if pos != "flat" and ep:
            tpls.append((last_close - ep) if pos == "long" else (ep - last_close))
        return tpls if tpls else None

    # Replay bar-by-bar with spike exit
    closes = algo_df["Close"].values.astype(float)
    times = algo_df.index
    sig_idx = 0
    result_trades = []
    spike_fires = 0
    pos, ep, entry_bar = "flat", None, 0
    prev_close = None

    for i in range(len(algo_df)):
        # Check if this bar has a signal
        if sig_idx < len(filtered) and times[i] == filtered[sig_idx][0]:
            ts, sig, price = filtered[sig_idx]
            sig_idx += 1
            if pos == "long" and sig == "SELL":
                result_trades.append(price - ep)
            elif pos == "short" and sig == "BUY":
                result_trades.append(ep - price)
            if sig == "BUY":
                pos, ep, entry_bar = "long", price, i
            else:
                pos, ep, entry_bar = "short", price, i
            prev_close = closes[i]
            continue

        # Check spike exit
        if pos != "flat" and ep is not None and i > entry_bar:
            fire = False

            if mode == "bar_move" and prev_close is not None:
                # Single bar move: close[i] vs close[i-1]
                bar_move = closes[i] - prev_close
                if pos == "long" and bar_move >= spike_pts:
                    fire = True
                elif pos == "short" and (-bar_move) >= spike_pts:
                    fire = True

            elif mode == "unrealized":
                bars_held = i - entry_bar
                if bars_held <= spike_bars:
                    if pos == "long":
                        move = closes[i] - ep
                    else:
                        move = ep - closes[i]
                    if move >= spike_pts:
                        fire = True

            if fire:
                if pos == "long":
                    result_trades.append(closes[i] - ep)
                else:
                    result_trades.append(ep - closes[i])
                spike_fires += 1
                pos, ep, entry_bar = "flat", None, 0

        prev_close = closes[i]

    # Close any open position at session end
    if pos != "flat" and ep is not None:
        last_close = closes[-1]
        if pos == "long":
            result_trades.append(last_close - ep)
        else:
            result_trades.append(ep - last_close)

    return (result_trades, spike_fires) if result_trades else None


# Test matrix
tests = [
    (0, 0, "unrealized", "BASELINE (no spike)"),
    # Bar move tests — any single bar in your favor
    (200, 0, "bar_move", "Bar move >= 200pts"),
    (150, 0, "bar_move", "Bar move >= 150pts"),
    (100, 0, "bar_move", "Bar move >= 100pts"),
    (75,  0, "bar_move", "Bar move >= 75pts"),
    (50,  0, "bar_move", "Bar move >= 50pts"),
    # Unrealized from entry within N bars
    (200, 3, "unrealized", "Unreal >= 200 in 3 bars"),
    (150, 3, "unrealized", "Unreal >= 150 in 3 bars"),
    (100, 3, "unrealized", "Unreal >= 100 in 3 bars"),
    (200, 5, "unrealized", "Unreal >= 200 in 5 bars"),
    (150, 5, "unrealized", "Unreal >= 150 in 5 bars"),
    (100, 5, "unrealized", "Unreal >= 100 in 5 bars"),
]

for spike_pts, spike_bars, mode, label in tests:
    total_pl = 0.0
    total_trades = 0
    winners = 0
    losers = 0
    daily_pls = []
    done = 0
    total_spikes = 0

    for fname in csv_files:
        dd = fname.replace("CBOT_MINI_YM1_", "").replace(".csv", "")
        if dd.startswith("2025-04"):
            done += 1
            continue
        try:
            df = pd.read_csv(os.path.join(_DATA_ROOT, fname), index_col=0, parse_dates=True)
            df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
        except:
            done += 1
            continue
        if len(df) < 10:
            done += 1
            continue

        day_start = pd.Timestamp(f"{dd} 09:30", tz=_EST)
        day_end = pd.Timestamp(f"{dd} 16:59", tz=_EST)
        day_data = df[(df.index >= day_start) & (df.index <= day_end)]
        if len(day_data) < 15:
            done += 1
            continue

        try:
            algo = run_trading_algo_fast(day_data, dd, "09:30", "17:00", config=config)
        except:
            done += 1
            continue

        result = run_backtest(algo, spike_pts, spike_bars, mode)
        if result is not None:
            if spike_bars == 0 and mode == "unrealized":
                tpls = result
                spk = 0
            elif isinstance(result, tuple):
                tpls, spk = result
                total_spikes += spk
            else:
                tpls = result
                spk = 0
            if tpls:
                day_pl = sum(tpls)
                total_pl += day_pl
                total_trades += len(tpls)
                winners += sum(1 for p in tpls if p > 0)
                losers += sum(1 for p in tpls if p <= 0)
                daily_pls.append(day_pl)
        done += 1

    wr = winners / (winners + losers) * 100 if (winners + losers) else 0
    usd = total_pl * 2 * 5
    avg = np.mean(daily_pls) if daily_pls else 0
    spike_str = f"  spikes:{total_spikes}" if mode != "unrealized" or spike_bars > 0 else ""
    print(f"{label:<30} Trades:{total_trades:>5}  Win%:{wr:>5.1f}%  Pts:{total_pl:>+8.0f}  ${usd:>+10,.0f}  Avg:{avg:>+6.1f}/day{spike_str}", flush=True)
