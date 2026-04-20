"""Test daily loss cap WITH April 2025 included.
Also show April 2025 day-by-day to find the -2000 day."""
import os
import pandas as pd, pytz, numpy as np
from TradingAlgoFast import AlgoConfig
from TradingAlgoFast import run_trading_algo_fast

_EST = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")

config = AlgoConfig(warmup_minutes=12, steep_angle_threshold=70.0,
                    proximity_points=15.0, min_reversal_minutes=0, max_loss_per_trade=0,
                    confirmation_bars=0)

csv_files = sorted([f for f in os.listdir(_DATA_ROOT) if f.endswith(".csv")])
print(f"Daily loss cap test on {len(csv_files)} days (April 2025 INCLUDED)...\n", flush=True)

_SPIKE_PTS = 100
_SPIKE_BARS = 5


def run_day(algo_df, daily_cap):
    rows = algo_df[algo_df["signal"].isin(["BUY", "SELL"])]
    if rows.empty:
        return None, False

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
        return None, False

    closes = algo_df["Close"].values.astype(float)
    times = algo_df.index
    sig_idx = 0
    tpls = []
    pos, ep, entry_bar = "flat", None, 0
    session_pl = 0.0
    capped = False

    for i in range(len(algo_df)):
        if daily_cap > 0 and pos != "flat" and ep is not None:
            if pos == "long":
                unrealized = closes[i] - ep
            else:
                unrealized = ep - closes[i]
            total_pl = session_pl + unrealized
            if total_pl <= -daily_cap:
                tpls.append(unrealized)
                session_pl += unrealized
                pos, ep, entry_bar = "flat", None, 0
                capped = True
                break

        if sig_idx < len(filtered) and times[i] == filtered[sig_idx][0]:
            ts, sig, price = filtered[sig_idx]
            sig_idx += 1
            if pos == "long" and sig == "SELL":
                pl = price - ep
                tpls.append(pl)
                session_pl += pl
            elif pos == "short" and sig == "BUY":
                pl = ep - price
                tpls.append(pl)
                session_pl += pl
            if daily_cap > 0 and session_pl <= -daily_cap:
                pos, ep, entry_bar = "flat", None, 0
                capped = True
                break
            if sig == "BUY":
                pos, ep, entry_bar = "long", price, i
            else:
                pos, ep, entry_bar = "short", price, i
            continue

        if pos != "flat" and ep is not None and i > entry_bar:
            bars_held = i - entry_bar
            if bars_held <= _SPIKE_BARS:
                move = (closes[i] - ep) if pos == "long" else (ep - closes[i])
                if move >= _SPIKE_PTS:
                    tpls.append(move)
                    session_pl += move
                    pos, ep, entry_bar = "flat", None, 0

    if pos != "flat" and ep is not None:
        last_close = closes[-1]
        pl = (last_close - ep) if pos == "long" else (ep - last_close)
        tpls.append(pl)

    return (tpls if tpls else None), capped


# First: show April 2025 day by day
print("=== APRIL 2025 DAY BY DAY ===", flush=True)
april_total = 0.0
for fname in csv_files:
    dd = fname.replace("CBOT_MINI_YM1_", "").replace(".csv", "")
    if not dd.startswith("2025-04"):
        continue
    try:
        df = pd.read_csv(os.path.join(_DATA_ROOT, fname), index_col=0, parse_dates=True)
        df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
    except:
        continue
    if len(df) < 10:
        continue
    day_start = pd.Timestamp(f"{dd} 09:30", tz=_EST)
    day_end = pd.Timestamp(f"{dd} 16:59", tz=_EST)
    day_data = df[(df.index >= day_start) & (df.index <= day_end)]
    if len(day_data) < 15:
        print(f"  {dd}  SKIP (only {len(day_data)} bars)", flush=True)
        continue
    try:
        algo = run_trading_algo_fast(day_data, dd, "09:30", "17:00", config=config)
    except Exception as e:
        print(f"  {dd}  ERROR: {e}", flush=True)
        continue
    tpls, _ = run_day(algo, 0)
    if tpls:
        day_pl = sum(tpls)
        april_total += day_pl
        print(f"  {dd}  {day_pl:>+8.0f} pts  ({len(tpls)} trades)  running: {april_total:>+8.0f}", flush=True)
    else:
        print(f"  {dd}  no trades", flush=True)

print(f"\n  April 2025 total: {april_total:>+8.0f} pts\n", flush=True)

# Now sweep caps WITH April included
caps = [0, 550]
for cap in caps:
    total_pl = 0.0
    total_trades = 0
    winners = 0
    losers = 0
    daily_pls = []
    capped_days = 0
    worst_day = 0.0
    worst_date = ""
    days_counted = 0

    for fname in csv_files:
        dd = fname.replace("CBOT_MINI_YM1_", "").replace(".csv", "")
        # NO APRIL EXCLUSION
        try:
            df = pd.read_csv(os.path.join(_DATA_ROOT, fname), index_col=0, parse_dates=True)
            df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
        except:
            continue
        if len(df) < 10:
            continue
        day_start = pd.Timestamp(f"{dd} 09:30", tz=_EST)
        day_end = pd.Timestamp(f"{dd} 16:59", tz=_EST)
        day_data = df[(df.index >= day_start) & (df.index <= day_end)]
        if len(day_data) < 15:
            continue
        try:
            algo = run_trading_algo_fast(day_data, dd, "09:30", "17:00", config=config)
        except:
            continue

        tpls, was_capped = run_day(algo, cap)
        if tpls:
            day_pl = sum(tpls)
            total_pl += day_pl
            total_trades += len(tpls)
            winners += sum(1 for p in tpls if p > 0)
            losers += sum(1 for p in tpls if p <= 0)
            daily_pls.append((dd, day_pl))
            if was_capped:
                capped_days += 1
            if day_pl < worst_day:
                worst_day = day_pl
                worst_date = dd
            days_counted += 1

    wr = winners / (winners + losers) * 100 if (winners + losers) else 0
    usd = total_pl * 2 * 5
    avg = np.mean([p for _, p in daily_pls]) if daily_pls else 0
    cap_str = f"CAP -{cap}" if cap > 0 else "NO CAP"
    print(f"{cap_str:<10} Days:{days_counted}  Trades:{total_trades:>5}  Win%:{wr:>5.1f}%  Pts:{total_pl:>+8.0f}  ${usd:>+10,.0f}  Avg:{avg:>+6.1f}/day  Worst:{worst_day:>+6.0f} ({worst_date})  Capped:{capped_days}", flush=True)

    # Show worst 15 days
    if cap == 0:
        sorted_days = sorted(daily_pls, key=lambda x: x[1])
        print(f"\n  Worst 15 days (no cap, April included):", flush=True)
        for d, p in sorted_days[:15]:
            print(f"    {d}  {p:>+8.0f} pts", flush=True)
