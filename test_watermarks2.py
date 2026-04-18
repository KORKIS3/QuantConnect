"""Water marks v2 — tighter parameters, close-based breaks only.
- Min 4 touches to form a cluster
- Touches must span at least 15 minutes (not just consecutive bars)
- Only fire once per cluster (first close through it)
- Break = close below low cluster or close above high cluster
- ±12 pts tolerance for clustering
- 30-bar lookback
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

CLUSTER_TOLERANCE = 12
MIN_TOUCHES = 4
MIN_SPAN_MINUTES = 15
LOOKBACK = 30


def find_clusters(values, times, tolerance, min_touches, min_span_minutes):
    """Find price clusters where touches span at least min_span_minutes."""
    if len(values) < min_touches:
        return []

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
            touch_times = sorted([g[1] for g in group])
            span = (touch_times[-1] - touch_times[0]).total_seconds() / 60
            if span >= min_span_minutes:
                level = np.mean([g[0] for g in group])
                clusters.append((level, len(group), touch_times, span))

    clusters.sort(key=lambda x: -x[1])
    return clusters


def analyze_day(dd, day_data, algo_df):
    closes = day_data["Close"].values.astype(float)
    highs = day_data["High"].values.astype(float)
    lows = day_data["Low"].values.astype(float)
    times = day_data.index

    signals = algo_df[algo_df["signal"].isin(["BUY", "SELL"])]
    algo_signals = [(ts.strftime("%H:%M"), row["signal"]) for ts, row in signals.iterrows()]

    print(f"\n{'='*90}")
    print(f"  {dd}  |  O:{closes[0]:.0f}  H:{max(highs):.0f}  L:{min(lows):.0f}  C:{closes[-1]:.0f}  "
          f"Range:{max(highs)-min(lows):.0f}  Move:{closes[-1]-closes[0]:+.0f}")
    print(f"{'='*90}")
    print(f"  Algo: {algo_signals[:8]}{'...' if len(algo_signals) > 8 else ''}")

    # Track which clusters have already been broken (by level, rounded)
    broken_low_levels = set()
    broken_high_levels = set()
    breaks = []

    for i in range(LOOKBACK, len(day_data)):
        window_lows = lows[max(0, i - LOOKBACK):i]
        window_highs = highs[max(0, i - LOOKBACK):i]
        window_times = times[max(0, i - LOOKBACK):i]

        low_clusters = find_clusters(window_lows, window_times, CLUSTER_TOLERANCE, MIN_TOUCHES, MIN_SPAN_MINUTES)
        high_clusters = find_clusters(window_highs, window_times, CLUSTER_TOLERANCE, MIN_TOUCHES, MIN_SPAN_MINUTES)

        # LOW cluster break: close below the cluster level
        for level, touches, touch_times, span in low_clusters:
            level_key = round(level / 10) * 10  # round to nearest 10 for dedup
            if level_key in broken_low_levels:
                continue
            if closes[i] < level:
                broken_low_levels.add(level_key)
                breaks.append({
                    "time": times[i].strftime("%H:%M"), "type": "LOW_BREAK",
                    "level": level, "close": closes[i], "touches": touches,
                    "span": span, "direction": "SELL",
                    "touch_times": [t.strftime("%H:%M") for t in touch_times[:6]]
                })

        # HIGH cluster break: close above the cluster level
        for level, touches, touch_times, span in high_clusters:
            level_key = round(level / 10) * 10
            if level_key in broken_high_levels:
                continue
            if closes[i] > level:
                broken_high_levels.add(level_key)
                breaks.append({
                    "time": times[i].strftime("%H:%M"), "type": "HIGH_BREAK",
                    "level": level, "close": closes[i], "touches": touches,
                    "span": span, "direction": "BUY",
                    "touch_times": [t.strftime("%H:%M") for t in touch_times[:6]]
                })

    print(f"\n  Water mark breaks ({MIN_TOUCHES}+ touches, {MIN_SPAN_MINUTES}+ min span, close through, fire once):")
    if not breaks:
        print("    None")
    else:
        for b in breaks:
            arrow = "▼" if b["direction"] == "SELL" else "▲"
            print(f"    {b['time']} {arrow} {b['direction']}  lvl={b['level']:.0f}  close={b['close']:.0f}  "
                  f"touches={b['touches']}  span={b['span']:.0f}min  @{','.join(b['touch_times'])}")

    return breaks


test_dates = [
    "2026-02-23", "2025-04-07", "2025-04-10", "2026-03-12",
    "2026-03-10", "2025-03-05", "2024-07-25", "2025-11-18",
    "2026-01-28", "2025-05-07", "2024-10-04", "2025-09-30",
]

all_breaks = {}
for dd in test_dates:
    fname = f"CBOT_MINI_YM1_{dd}.csv"
    fpath = os.path.join(_DATA_ROOT, fname)
    if not os.path.exists(fpath):
        print(f"\n  {dd}: not found")
        continue
    try:
        df = pd.read_csv(fpath, index_col=0, parse_dates=True)
        df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
    except Exception as e:
        print(f"\n  {dd}: error: {e}")
        continue

    day_start = pd.Timestamp(f"{dd} 09:30", tz=_EST)
    day_end = pd.Timestamp(f"{dd} 16:59", tz=_EST)
    day_data = df[(df.index >= day_start) & (df.index <= day_end)]
    if len(day_data) < 40:
        continue

    try:
        algo = run_trading_algo_fast(day_data, dd, "09:30", "17:00", config=config)
        breaks = analyze_day(dd, day_data, algo)
        all_breaks[dd] = breaks
    except Exception as e:
        print(f"\n  {dd}: error: {e}")

print(f"\n\n{'='*90}")
print("SUMMARY")
print(f"{'='*90}")
total = sum(len(b) for b in all_breaks.values())
days = len(all_breaks)
print(f"Days analyzed: {days}")
print(f"Total breaks: {total}  ({total/days:.1f} per day)")
sells = sum(1 for b in all_breaks.values() for x in b if x["direction"] == "SELL")
buys = sum(1 for b in all_breaks.values() for x in b if x["direction"] == "BUY")
print(f"SELL breaks: {sells}  BUY breaks: {buys}")
if total:
    avg_touches = np.mean([x["touches"] for b in all_breaks.values() for x in b])
    avg_span = np.mean([x["span"] for b in all_breaks.values() for x in b])
    print(f"Avg touches: {avg_touches:.1f}  Avg span: {avg_span:.0f} min")
