"""Visualize low/high water marks on sample days.
Find price clusters where 3+ bar lows or highs land within ±10 pts.
Show where breaks of these levels would have triggered vs what the algo did."""
import os
import pandas as pd, pytz, numpy as np
from TradingAlgoFast import AlgoConfig
from TradingAlgoFast import run_trading_algo_fast

_EST = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")

config = AlgoConfig(warmup_minutes=12, steep_angle_threshold=70.0,
                    proximity_points=15.0, min_reversal_minutes=0, max_loss_per_trade=0,
                    confirmation_bars=0)

CLUSTER_TOLERANCE = 10  # points — lows/highs within this range form a cluster
MIN_TOUCHES = 3         # minimum bars touching the level to qualify
LOOKBACK = 30           # bars to scan for clusters


def find_clusters(values, times, tolerance, min_touches):
    """Find price clusters in a series of values (lows or highs).
    Returns list of (level, touch_count, touch_times) sorted by touch count desc."""
    if len(values) < min_touches:
        return []

    # Sort values to find groups
    indexed = sorted(zip(values, times), key=lambda x: x[0])
    clusters = []
    used = set()

    for i in range(len(indexed)):
        if i in used:
            continue
        base_val = indexed[i][0]
        group = [(indexed[i][0], indexed[i][1])]
        used.add(i)
        for j in range(i + 1, len(indexed)):
            if j in used:
                continue
            if abs(indexed[j][0] - base_val) <= tolerance:
                group.append((indexed[j][0], indexed[j][1]))
                used.add(j)
            elif indexed[j][0] - base_val > tolerance:
                break

        if len(group) >= min_touches:
            level = np.mean([g[0] for g in group])
            touch_times = [g[1] for g in group]
            clusters.append((level, len(group), touch_times))

    clusters.sort(key=lambda x: -x[1])  # most touches first
    return clusters


def analyze_day(dd, day_data, algo_df):
    """Analyze one day: find clusters bar-by-bar and show where breaks happen."""
    closes = day_data["Close"].values.astype(float)
    highs = day_data["High"].values.astype(float)
    lows = day_data["Low"].values.astype(float)
    times = day_data.index

    # Get algo signals for comparison
    signals = algo_df[algo_df["signal"].isin(["BUY", "SELL"])]
    algo_signals = [(ts.strftime("%H:%M"), row["signal"]) for ts, row in signals.iterrows()]

    print(f"\n{'='*80}")
    print(f"  {dd}  |  Open: {closes[0]:.0f}  High: {max(highs):.0f}  Low: {min(lows):.0f}  Close: {closes[-1]:.0f}")
    print(f"  Range: {max(highs) - min(lows):.0f} pts  |  Move: {closes[-1] - closes[0]:+.0f} pts")
    print(f"{'='*80}")

    # Scan bar-by-bar for clusters and breaks
    active_low_clusters = []   # (level, touches, first_seen_bar)
    active_high_clusters = []
    breaks = []

    for i in range(LOOKBACK, len(day_data)):
        # Look back LOOKBACK bars for clusters
        window_lows = lows[max(0, i - LOOKBACK):i]
        window_highs = highs[max(0, i - LOOKBACK):i]
        window_times = times[max(0, i - LOOKBACK):i]

        low_clusters = find_clusters(window_lows, window_times, CLUSTER_TOLERANCE, MIN_TOUCHES)
        high_clusters = find_clusters(window_highs, window_times, CLUSTER_TOLERANCE, MIN_TOUCHES)

        # Check if current close breaks any cluster
        for level, touches, touch_times in low_clusters:
            if closes[i] < level - 5:  # close below the cluster level (with small buffer)
                # Check this isn't a repeat of a recent break
                already_broken = any(
                    b["type"] == "LOW_BREAK" and abs(b["level"] - level) < CLUSTER_TOLERANCE
                    for b in breaks[-5:]  # last 5 breaks
                )
                if not already_broken:
                    breaks.append({
                        "bar": i, "time": times[i].strftime("%H:%M"),
                        "type": "LOW_BREAK", "level": level, "close": closes[i],
                        "touches": touches, "direction": "SELL",
                        "touch_times": [t.strftime("%H:%M") for t in touch_times]
                    })

        for level, touches, touch_times in high_clusters:
            if closes[i] > level + 5:  # close above the cluster level
                already_broken = any(
                    b["type"] == "HIGH_BREAK" and abs(b["level"] - level) < CLUSTER_TOLERANCE
                    for b in breaks[-5:]
                )
                if not already_broken:
                    breaks.append({
                        "bar": i, "time": times[i].strftime("%H:%M"),
                        "type": "HIGH_BREAK", "level": level, "close": closes[i],
                        "touches": touches, "direction": "BUY",
                        "touch_times": [t.strftime("%H:%M") for t in touch_times]
                    })

    # Print clusters found at key times
    print(f"\n  Algo signals: {algo_signals[:10]}")
    print(f"\n  Water mark breaks (close through cluster of {MIN_TOUCHES}+ touches within ±{CLUSTER_TOLERANCE} pts):")
    if not breaks:
        print("    None found")
    else:
        for b in breaks:
            arrow = "▼" if b["direction"] == "SELL" else "▲"
            print(f"    {b['time']} {arrow} {b['direction']}  level={b['level']:.0f}  close={b['close']:.0f}  "
                  f"touches={b['touches']}  touched@{','.join(b['touch_times'][:5])}")

    # Show snapshot of clusters at 10:00 (30 min in)
    bar_1000 = None
    for i, t in enumerate(times):
        if t.strftime("%H:%M") == "10:00":
            bar_1000 = i
            break
    if bar_1000 and bar_1000 >= LOOKBACK:
        window_lows = lows[bar_1000 - LOOKBACK:bar_1000]
        window_highs = highs[bar_1000 - LOOKBACK:bar_1000]
        window_times = times[bar_1000 - LOOKBACK:bar_1000]
        lc = find_clusters(window_lows, window_times, CLUSTER_TOLERANCE, MIN_TOUCHES)
        hc = find_clusters(window_highs, window_times, CLUSTER_TOLERANCE, MIN_TOUCHES)
        print(f"\n  Clusters at 10:00 (looking back {LOOKBACK} bars):")
        if lc:
            for level, touches, _ in lc[:3]:
                print(f"    LOW  cluster @ {level:.0f}  ({touches} touches) — support")
        if hc:
            for level, touches, _ in hc[:3]:
                print(f"    HIGH cluster @ {level:.0f}  ({touches} touches) — resistance")
        if not lc and not hc:
            print("    No clusters found")

    return breaks


# Pick interesting days: some big winners, some big losers, some choppy
test_dates = [
    "2026-02-23",  # CRUSHER: algo whipsawed 7 times, user held 1 trade
    "2025-04-07",  # Big volatile day
    "2025-04-10",  # +1008 pts monster
    "2026-03-12",  # Worst day -514
    "2026-03-10",  # Best day +637
    "2025-03-05",  # -184 baseline, interesting reversal
    "2024-07-25",  # +629 big winner
    "2025-11-18",  # +382 with late recovery
]

all_breaks = {}
for dd in test_dates:
    fname = f"CBOT_MINI_YM1_{dd}.csv"
    fpath = os.path.join(_DATA_ROOT, fname)
    if not os.path.exists(fpath):
        print(f"\n  {dd}: file not found, skipping")
        continue
    try:
        df = pd.read_csv(fpath, index_col=0, parse_dates=True)
        df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
    except Exception as e:
        print(f"\n  {dd}: error loading: {e}")
        continue

    day_start = pd.Timestamp(f"{dd} 09:30", tz=_EST)
    day_end = pd.Timestamp(f"{dd} 16:59", tz=_EST)
    day_data = df[(df.index >= day_start) & (df.index <= day_end)]
    if len(day_data) < 40:
        print(f"\n  {dd}: only {len(day_data)} bars, skipping")
        continue

    try:
        algo = run_trading_algo_fast(day_data, dd, "09:30", "17:00", config=config)
        breaks = analyze_day(dd, day_data, algo)
        all_breaks[dd] = breaks
    except Exception as e:
        print(f"\n  {dd}: algo error: {e}")

# Summary
print(f"\n\n{'='*80}")
print("SUMMARY")
print(f"{'='*80}")
total_breaks = sum(len(b) for b in all_breaks.values())
print(f"Total water mark breaks across {len(all_breaks)} days: {total_breaks}")
print(f"Average per day: {total_breaks / len(all_breaks):.1f}")
sell_breaks = sum(1 for b in all_breaks.values() for x in b if x["direction"] == "SELL")
buy_breaks = sum(1 for b in all_breaks.values() for x in b if x["direction"] == "BUY")
print(f"SELL breaks: {sell_breaks}  BUY breaks: {buy_breaks}")
avg_touches = np.mean([x["touches"] for b in all_breaks.values() for x in b]) if total_breaks else 0
print(f"Average touches per cluster: {avg_touches:.1f}")
