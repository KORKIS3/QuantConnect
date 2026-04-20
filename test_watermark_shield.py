"""Water mark hold shield: suppress ray-cross exits when a nearby water mark supports the trade.
Long + SELL signal → hold if low cluster within X pts below price (support holds)
Short + BUY signal → hold if high cluster within X pts above price (resistance holds)
Exit only when price closes through the water mark too."""
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
print(f"Water mark shield test on {len(csv_files)} days...\n", flush=True)

_SPIKE_PTS = 100
_SPIKE_BARS = 5

# Water mark params
WM_TOLERANCE = 12
WM_MIN_TOUCHES = 4
WM_MIN_SPAN = 15  # minutes
WM_LOOKBACK = 30  # bars


def find_clusters(lows_or_highs, times, tolerance, min_touches, min_span):
    if len(lows_or_highs) < min_touches:
        return []
    indexed = sorted(zip(lows_or_highs, times), key=lambda x: x[0])
    clusters = []
    used = set()
    for i in range(len(indexed)):
        if i in used:
            continue
        base = indexed[i][0]
        group = [(indexed[i][0], indexed[i][1])]
        used.add(i)
        for j in range(i + 1, len(indexed)):
            if j in used:
                continue
            if abs(indexed[j][0] - base) <= tolerance:
                group.append((indexed[j][0], indexed[j][1]))
                used.add(j)
            elif indexed[j][0] - base > tolerance:
                break
        if len(group) >= min_touches:
            touch_times = sorted([g[1] for g in group])
            span = (touch_times[-1] - touch_times[0]).total_seconds() / 60
            if span >= min_span:
                level = np.mean([g[0] for g in group])
                clusters.append((level, len(group)))
    return clusters


def run_backtest(algo_df, shield_distance):
    """Post-hoc 10-min filter + spike exit + optional water mark shield.
    shield_distance: suppress exit if water mark within this many pts (0=disabled/baseline)
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

    closes = algo_df["Close"].values.astype(float)
    highs = algo_df["High"].values.astype(float)
    lows = algo_df["Low"].values.astype(float)
    times = algo_df.index
    sig_idx = 0
    tpls = []
    pos, ep, entry_bar = "flat", None, 0
    shields_used = 0

    for i in range(len(algo_df)):
        # Check if this bar has a filtered signal
        if sig_idx < len(filtered) and times[i] == filtered[sig_idx][0]:
            ts, sig, price = filtered[sig_idx]
            sig_idx += 1

            should_act = True

            # Water mark shield check
            if shield_distance > 0 and pos != "flat" and i >= WM_LOOKBACK:
                window_start = max(0, i - WM_LOOKBACK)

                if pos == "long" and sig == "SELL":
                    # Check for low cluster (support) near current price
                    wm_lows = lows[window_start:i]
                    wm_times = times[window_start:i]
                    low_clusters = find_clusters(wm_lows, wm_times, WM_TOLERANCE, WM_MIN_TOUCHES, WM_MIN_SPAN)
                    for level, touches in low_clusters:
                        # Support is below current price and within shield distance
                        if level < closes[i] and (closes[i] - level) <= shield_distance:
                            # Price hasn't closed below the support → shield holds
                            if closes[i] > level:
                                should_act = False
                                shields_used += 1
                                break

                elif pos == "short" and sig == "BUY":
                    # Check for high cluster (resistance) near current price
                    wm_highs = highs[window_start:i]
                    wm_times = times[window_start:i]
                    high_clusters = find_clusters(wm_highs, wm_times, WM_TOLERANCE, WM_MIN_TOUCHES, WM_MIN_SPAN)
                    for level, touches in high_clusters:
                        # Resistance is above current price and within shield distance
                        if level > closes[i] and (level - closes[i]) <= shield_distance:
                            if closes[i] < level:
                                should_act = False
                                shields_used += 1
                                break

            if should_act:
                if pos == "long" and sig == "SELL":
                    tpls.append(price - ep)
                elif pos == "short" and sig == "BUY":
                    tpls.append(ep - price)

                if sig == "BUY":
                    pos, ep, entry_bar = "long", price, i
                else:
                    pos, ep, entry_bar = "short", price, i
            continue

        # Spike exit (unchanged)
        if pos != "flat" and ep is not None and i > entry_bar:
            bars_held = i - entry_bar
            if bars_held <= _SPIKE_BARS:
                move = (closes[i] - ep) if pos == "long" else (ep - closes[i])
                if move >= _SPIKE_PTS:
                    tpls.append(move)
                    pos, ep, entry_bar = "flat", None, 0

    # Close open position at session end
    if pos != "flat" and ep is not None:
        lc = closes[-1]
        tpls.append((lc - ep) if pos == "long" else (ep - lc))

    return (tpls, shields_used) if tpls else None


# Test shield distances
distances = [0, 20, 30, 40, 50, 75, 100]

for dist in distances:
    total_pl = 0.0
    total_trades = 0
    winners = 0
    losers = 0
    daily_pls = []
    total_shields = 0

    for fname in csv_files:
        dd = fname.replace("CBOT_MINI_YM1_", "").replace(".csv", "")
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

        result = run_backtest(algo, dist)
        if result is not None:
            tpls, shd = result
            if tpls:
                day_pl = sum(tpls)
                total_pl += day_pl
                total_trades += len(tpls)
                winners += sum(1 for p in tpls if p > 0)
                losers += sum(1 for p in tpls if p <= 0)
                daily_pls.append(day_pl)
                total_shields += shd

    wr = winners / (winners + losers) * 100 if (winners + losers) else 0
    usd = total_pl * 2 * 5
    avg = np.mean(daily_pls) if daily_pls else 0
    label = f"SHIELD {dist}pts" if dist > 0 else "BASELINE"
    print(f"{label:<16} Trades:{total_trades:>5}  Win%:{wr:>5.1f}%  Pts:{total_pl:>+8.0f}  ${usd:>+10,.0f}  Avg:{avg:>+6.1f}/day  Shields:{total_shields}", flush=True)
