"""
run_significance_audit.py — Re-run structure audit with significance filtering.

Filters:
1. Minimum 15 pts from previous extreme
2. Minimum 3 bars since last structure creation
3. Bounce requirement: price must move away by 10+ pts after the low/high
4. Resume: price must return and make new extreme after bounce

Question: How many Yellows/Oranges/day remain after filtering?
"""
import os, time
import numpy as np
import pandas as pd
import pytz

_EST = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")

MIN_PTS_FROM_PREV = 15.0    # new extreme must exceed previous by 15+ pts
MIN_BARS_BETWEEN = 3        # minimum bars between structure creation
MIN_BOUNCE_PTS = 10.0       # price must bounce 10+ pts away from extreme


def run_day_filtered(fname):
    """Run significance-filtered structure analysis on one day."""
    target_date = fname.replace("CBOT_MINI_YM1_", "").replace(".csv", "")
    fpath = os.path.join(_DATA_ROOT, fname)
    try:
        df = pd.read_csv(fpath, index_col=0, parse_dates=True)
        df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
    except:
        return None
    day_start = pd.Timestamp(f'{target_date} 09:30', tz=_EST)
    day_end = pd.Timestamp(f'{target_date} 16:59', tz=_EST)
    day_data = df[(df.index >= day_start) & (df.index <= day_end)]
    if len(day_data) < 15:
        return None
    if (day_data[["Open", "High", "Low", "Close"]] <= 0).any().any():
        return None
    if day_data["High"].max() == day_data["Low"].min():
        return None

    highs = day_data['High'].values
    lows = day_data['Low'].values
    closes = day_data['Close'].values
    n = len(day_data)

    # Track significant structure points
    sig_yellows = []  # (bar, price) — significant new lows
    sig_oranges = []  # (bar, price) — significant new highs

    session_low = lows[0]
    session_high = highs[0]
    last_yellow_bar = 0
    last_orange_bar = 0
    last_yellow_price = lows[0]
    last_orange_price = highs[0]

    # First bar always creates initial structure
    sig_yellows.append((0, lows[0]))
    sig_oranges.append((0, highs[0]))

    for i in range(1, n):
        # --- Check for significant new LOW ---
        if lows[i] < session_low:
            session_low = lows[i]

            # Filter 1: minimum distance from previous significant low
            pts_below = last_yellow_price - lows[i]
            if pts_below < MIN_PTS_FROM_PREV:
                continue  # too close to previous — noise

            # Filter 2: minimum bars since last structure
            if i - last_yellow_bar < MIN_BARS_BETWEEN:
                continue  # too soon

            # Filter 3: bounce requirement — check if price bounced after previous low
            # Look back: did price move UP by 10+ pts between last yellow and now?
            bounce_found = False
            for j in range(last_yellow_bar + 1, i):
                if highs[j] - last_yellow_price >= MIN_BOUNCE_PTS:
                    bounce_found = True
                    break

            if not bounce_found:
                continue  # no meaningful bounce — just grinding lower

            # All filters passed — this is significant structure
            sig_yellows.append((i, lows[i]))
            last_yellow_bar = i
            last_yellow_price = lows[i]

        # --- Check for significant new HIGH ---
        if highs[i] > session_high:
            session_high = highs[i]

            pts_above = highs[i] - last_orange_price
            if pts_above < MIN_PTS_FROM_PREV:
                continue

            if i - last_orange_bar < MIN_BARS_BETWEEN:
                continue

            bounce_found = False
            for j in range(last_orange_bar + 1, i):
                if last_orange_price - lows[j] >= MIN_BOUNCE_PTS:
                    bounce_found = True
                    break

            if not bounce_found:
                continue

            sig_oranges.append((i, highs[i]))
            last_orange_bar = i
            last_orange_price = highs[i]

    # Session range
    session_range = max(highs) - min(lows)

    # Classification based on SIGNIFICANT structure count
    bearish_score = len(sig_yellows) - 1  # subtract initial
    bullish_score = len(sig_oranges) - 1

    if bearish_score >= 6 or bullish_score >= 6:
        classification = "STRONG_TREND"
    elif bearish_score >= 3 or bullish_score >= 3:
        classification = "RESOLVE"
    elif session_range < 150:
        classification = "COMPRESSION"
    elif bearish_score <= 1 and bullish_score <= 1:
        classification = "CHOP"
    else:
        classification = "MIXED"

    if bearish_score > bullish_score + 1:
        resolve_dir = "BEARISH"
    elif bullish_score > bearish_score + 1:
        resolve_dir = "BULLISH"
    else:
        resolve_dir = "NEUTRAL"

    return {
        'date': target_date,
        'sig_yellows': len(sig_yellows),
        'sig_oranges': len(sig_oranges),
        'bearish_score': bearish_score,
        'bullish_score': bullish_score,
        'session_range': session_range,
        'classification': classification,
        'resolve_direction': resolve_dir,
    }


def main():
    files = sorted([f for f in os.listdir(_DATA_ROOT)
                    if f.startswith('CBOT_MINI_YM1_') and f.endswith('.csv')])
    print(f"Running significance-filtered audit on {len(files)} files...")
    print(f"Filters: min_pts={MIN_PTS_FROM_PREV}, min_bars={MIN_BARS_BETWEEN}, min_bounce={MIN_BOUNCE_PTS}")

    results = []
    t0 = time.time()
    for i, fname in enumerate(files):
        r = run_day_filtered(fname)
        if r:
            results.append(r)
        if (i + 1) % 100 == 0:
            print(f"  [{i+1}/{len(files)}] {len(results)} valid, {time.time()-t0:.0f}s")

    n = len(results)
    print(f"\nCompleted: {n} days in {time.time()-t0:.1f}s")

    df = pd.DataFrame(results)

    print(f"\n{'='*70}")
    print(f"SIGNIFICANCE-FILTERED STRUCTURE AUDIT — {n} days")
    print(f"Filters: >{MIN_PTS_FROM_PREV}pts, >{MIN_BARS_BETWEEN}bars, >{MIN_BOUNCE_PTS}pts bounce")
    print(f"{'='*70}")

    print(f"\n1. SIGNIFICANT STRUCTURE COUNTS:")
    print(f"   Avg significant Yellows/day: {df['sig_yellows'].mean():.1f}")
    print(f"   Avg significant Oranges/day: {df['sig_oranges'].mean():.1f}")
    print(f"   Total structure/day: {(df['sig_yellows'] + df['sig_oranges']).mean():.1f}")
    print(f"   (Compare: unfiltered was 14.6 yellows + 16.0 oranges = 30.6/day)")

    print(f"\n2. SESSION CLASSIFICATIONS:")
    for cls in ['STRONG_TREND', 'RESOLVE', 'COMPRESSION', 'CHOP', 'MIXED']:
        count = (df['classification'] == cls).sum()
        print(f"   {cls}: {count} ({count/n*100:.1f}%)")

    print(f"\n3. RESOLVE DIRECTION:")
    for d in ['BEARISH', 'BULLISH', 'NEUTRAL']:
        count = (df['resolve_direction'] == d).sum()
        print(f"   {d}: {count} ({count/n*100:.1f}%)")

    print(f"\n{'='*70}")
    print(f"COMPARISON: Three engines")
    print(f"{'='*70}")
    chop_count = (df['classification'] == 'CHOP').sum() + (df['classification'] == 'COMPRESSION').sum() + (df['classification'] == 'MIXED').sum()
    trend_count = (df['classification'] == 'STRONG_TREND').sum() + (df['classification'] == 'RESOLVE').sum()
    print(f"   OLD (regression):        550 Chop / 15 Trend  (97% / 3%)")
    print(f"   NEW (unfiltered frozen):  40 Chop / 605 Trend  (6% / 94%)")
    print(f"   NEW (significance filter): {chop_count} Chop / {trend_count} Trend  ({chop_count/n*100:.0f}% / {trend_count/n*100:.0f}%)")

    print(f"\n4. DISTRIBUTION OF SIGNIFICANT STRUCTURE:")
    print(f"   Days with 0-1 sig yellows: {(df['sig_yellows'] <= 1).sum()}")
    print(f"   Days with 2-3 sig yellows: {((df['sig_yellows'] >= 2) & (df['sig_yellows'] <= 3)).sum()}")
    print(f"   Days with 4-6 sig yellows: {((df['sig_yellows'] >= 4) & (df['sig_yellows'] <= 6)).sum()}")
    print(f"   Days with 7+ sig yellows: {(df['sig_yellows'] >= 7).sum()}")

    # Top lists
    print(f"\n--- TOP 10 STRONGEST TREND DAYS (filtered) ---")
    df['trend_score'] = df[['bearish_score', 'bullish_score']].max(axis=1)
    for _, r in df.nlargest(10, 'trend_score').iterrows():
        d = "BEAR" if r['bearish_score'] > r['bullish_score'] else "BULL"
        print(f"  {r['date']} score={r['trend_score']} ({d}) range={r['session_range']:.0f} Y={r['sig_yellows']} O={r['sig_oranges']}")

    print(f"\n--- TOP 10 CHOP/COMPRESSION DAYS ---")
    chop_days = df[df['classification'].isin(['CHOP', 'COMPRESSION', 'MIXED'])].nsmallest(10, 'session_range')
    for _, r in chop_days.iterrows():
        print(f"  {r['date']} class={r['classification']} range={r['session_range']:.0f} Y={r['sig_yellows']} O={r['sig_oranges']}")

    print(f"\nCSV: significance_audit_results.csv")
    df.to_csv('significance_audit_results.csv', index=False)


if __name__ == "__main__":
    main()
