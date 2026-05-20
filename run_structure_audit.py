"""
run_structure_audit.py — Post-rebuild forensic structure audit

Runs the frozen ray engine on all 565 days.
No P/L. No trades. Structure only.

Question: Does correcting geometry change our understanding of market behavior?
"""
import os, time
import numpy as np
import pandas as pd
import pytz
from frozen_ray_engine import FrozenRayEngine

_EST = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")


def run_day(fname):
    """Run frozen ray engine on one day, return structural statistics."""
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

    engine = FrozenRayEngine(swing_threshold=10.0)
    engine.run_session(day_data)

    # Collect statistics
    all_lines = engine.lines
    active_lines = [l for l in all_lines if l.status == "FROZEN"]
    retired_lines = [l for l in all_lines if l.status == "RETIRED"]

    # Line type counts
    oranges = [l for l in all_lines if l.line_type == "ORANGE"]
    yellows = [l for l in all_lines if l.line_type == "YELLOW"]
    purples_orig = [l for l in all_lines if l.line_type == "PURPLE_ORIGINAL"]
    blues_orig = [l for l in all_lines if l.line_type == "BLUE_ORIGINAL"]
    purples_profit = [l for l in all_lines if l.line_type == "PURPLE_PROFIT"]

    # Touch statistics
    all_touches = [l.touch_count for l in all_lines if l.touch_count > 0]
    max_touches = max(all_touches) if all_touches else 0
    avg_touches = np.mean(all_touches) if all_touches else 0

    # Strategic breaks (lines that were retired by confirmed close beyond)
    strategic_breaks = len(retired_lines)

    # Quadrant at end of session
    final_quadrant = engine.quadrant_state

    # Session range and resolve metrics
    session_high = max(engine.highs) if engine.highs else 0
    session_low = min(engine.lows) if engine.lows else 0
    session_range = session_high - session_low

    # Count how many times quadrant changed (transitions)
    # We need to re-run and track transitions
    quadrant_transitions = 0
    prev_quad = "UNKNOWN"
    temp_engine = FrozenRayEngine(swing_threshold=10.0)
    # Re-run tracking quadrant changes
    from frozen_ray_engine import FrozenRay
    temp_engine.lines.append(FrozenRay(
        line_id=temp_engine._new_id(), line_type="PURPLE_ORIGINAL", authority_rank=2,
        anchor_price=float(day_data.iloc[0]['High']), anchor_bar=0, slope=0.0,
        status="PROVISIONAL", direction="RESISTANCE", created_at_bar=0,
    ))
    temp_engine.lines.append(FrozenRay(
        line_id=temp_engine._new_id(), line_type="BLUE_ORIGINAL", authority_rank=2,
        anchor_price=float(day_data.iloc[0]['Low']), anchor_bar=0, slope=0.0,
        status="PROVISIONAL", direction="SUPPORT", created_at_bar=0,
    ))
    for i in range(len(day_data)):
        row = day_data.iloc[i]
        temp_engine.process_bar(float(row['Open']), float(row['High']),
                               float(row['Low']), float(row['Close']))
        if temp_engine.quadrant_state != prev_quad:
            quadrant_transitions += 1
            prev_quad = temp_engine.quadrant_state

    # Classify session structure
    # TREND: strong directional resolve (many yellow breaks, few reclaims, final quadrant strong)
    # COMPRESSION: narrowing range, few breaks, quadrant stays neutral
    # RESOLVE: clear directional movement with continuation evidence
    yellow_count = len(yellows)
    orange_count = len(oranges)

    # Resolve score: how many successive new lows (bearish) or new highs (bullish)
    bearish_resolve_score = yellow_count - 1  # each new yellow = new session low
    bullish_resolve_score = orange_count - 1  # each new orange = new session high

    # Compression: small range relative to typical, few breaks
    is_compression = session_range < 150 and strategic_breaks < 5
    is_strong_trend = (bearish_resolve_score >= 8 or bullish_resolve_score >= 8)
    is_resolve = (bearish_resolve_score >= 4 or bullish_resolve_score >= 4) and not is_compression

    if is_strong_trend:
        classification = "STRONG_TREND"
    elif is_resolve:
        classification = "RESOLVE"
    elif is_compression:
        classification = "COMPRESSION"
    else:
        classification = "MIXED"

    # Resolve direction
    if bearish_resolve_score > bullish_resolve_score + 2:
        resolve_dir = "BEARISH"
    elif bullish_resolve_score > bearish_resolve_score + 2:
        resolve_dir = "BULLISH"
    else:
        resolve_dir = "NEUTRAL"

    return {
        'date': target_date,
        'total_lines': len(all_lines),
        'active_lines_end': len(active_lines),
        'retired_lines': len(retired_lines),
        'orange_count': orange_count,
        'yellow_count': yellow_count,
        'purple_orig_count': len(purples_orig),
        'blue_orig_count': len(blues_orig),
        'purple_profit_count': len(purples_profit),
        'max_touches': max_touches,
        'avg_touches': avg_touches,
        'strategic_breaks': strategic_breaks,
        'quadrant_transitions': quadrant_transitions,
        'final_quadrant': final_quadrant,
        'session_range': session_range,
        'bearish_resolve_score': bearish_resolve_score,
        'bullish_resolve_score': bullish_resolve_score,
        'classification': classification,
        'resolve_direction': resolve_dir,
    }


def main():
    files = sorted([f for f in os.listdir(_DATA_ROOT)
                    if f.startswith('CBOT_MINI_YM1_') and f.endswith('.csv')])
    print(f"Running structure audit on {len(files)} files...")

    results = []
    t0 = time.time()
    for i, fname in enumerate(files):
        r = run_day(fname)
        if r:
            results.append(r)
        if (i + 1) % 100 == 0:
            print(f"  [{i+1}/{len(files)}] {len(results)} valid, {time.time()-t0:.0f}s")

    n = len(results)
    elapsed = time.time() - t0
    print(f"\nCompleted: {n} days in {elapsed:.1f}s")

    df = pd.DataFrame(results)
    df.to_csv('structure_audit_results.csv', index=False)

    # === REPORT ===
    print(f"\n{'='*70}")
    print(f"FORENSIC STRUCTURE AUDIT — {n} days")
    print(f"{'='*70}")

    print(f"\n1. AVERAGE ACTIVE LINE COUNT/DAY: {df['active_lines_end'].mean():.1f}")
    print(f"   (total lines created/day: {df['total_lines'].mean():.1f})")

    print(f"\n2. CONTINUATION EVIDENCE (Yellow = bearish continuation, Orange = bullish):")
    print(f"   Avg Yellow count/day: {df['yellow_count'].mean():.1f}")
    print(f"   Avg Orange count/day: {df['orange_count'].mean():.1f}")

    print(f"\n3. TACTICAL PURPLE (profit protection):")
    print(f"   Days with tactical purple: {(df['purple_profit_count'] > 0).sum()} ({(df['purple_profit_count'] > 0).sum()/n*100:.0f}%)")
    print(f"   Avg count when present: {df[df['purple_profit_count'] > 0]['purple_profit_count'].mean():.1f}" if (df['purple_profit_count'] > 0).any() else "   N/A")

    print(f"\n4. QUADRANT TRANSITIONS:")
    print(f"   Avg transitions/day: {df['quadrant_transitions'].mean():.1f}")
    print(f"   Max transitions: {df['quadrant_transitions'].max()}")
    print(f"   Min transitions: {df['quadrant_transitions'].min()}")

    print(f"\n5. TOUCH DISTRIBUTIONS:")
    print(f"   Avg max touches/day: {df['max_touches'].mean():.1f}")
    print(f"   Days with 3+ touch lines: {(df['max_touches'] >= 3).sum()} ({(df['max_touches'] >= 3).sum()/n*100:.0f}%)")

    print(f"\n6. STRATEGIC BREAK DISTRIBUTIONS:")
    print(f"   Avg breaks/day: {df['strategic_breaks'].mean():.1f}")
    print(f"   Median breaks/day: {df['strategic_breaks'].median():.0f}")

    print(f"\n7. SESSION CLASSIFICATIONS:")
    for cls in ['STRONG_TREND', 'RESOLVE', 'COMPRESSION', 'MIXED']:
        count = (df['classification'] == cls).sum()
        print(f"   {cls}: {count} ({count/n*100:.1f}%)")

    print(f"\n8. RESOLVE DIRECTION:")
    for d in ['BEARISH', 'BULLISH', 'NEUTRAL']:
        count = (df['resolve_direction'] == d).sum()
        print(f"   {d}: {count} ({count/n*100:.1f}%)")

    print(f"\n9. SESSION RANGE:")
    print(f"   Avg range: {df['session_range'].mean():.0f} pts")
    print(f"   Median range: {df['session_range'].median():.0f} pts")
    print(f"   Days > 300 pts range: {(df['session_range'] > 300).sum()}")
    print(f"   Days < 150 pts range: {(df['session_range'] < 150).sum()}")

    # === KEY QUESTION: Does "550/565 = Chop" survive? ===
    print(f"\n{'='*70}")
    print(f"KEY QUESTION: Does '550/565 = Chop' survive after geometry rebuild?")
    print(f"{'='*70}")
    chop_equivalent = (df['classification'] == 'MIXED').sum() + (df['classification'] == 'COMPRESSION').sum()
    trend_equivalent = (df['classification'] == 'STRONG_TREND').sum() + (df['classification'] == 'RESOLVE').sum()
    print(f"   OLD ENGINE: 550 Chop / 15 Trend")
    print(f"   NEW ENGINE: {chop_equivalent} Chop-equivalent / {trend_equivalent} Trend-equivalent")
    print(f"   STRONG_TREND: {(df['classification'] == 'STRONG_TREND').sum()}")
    print(f"   RESOLVE: {(df['classification'] == 'RESOLVE').sum()}")
    print(f"   COMPRESSION: {(df['classification'] == 'COMPRESSION').sum()}")
    print(f"   MIXED: {(df['classification'] == 'MIXED').sum()}")

    # === TOP 20 LISTS ===
    print(f"\n--- TOP 20 STRONGEST TREND STRUCTURE DAYS ---")
    trend_score = df['bearish_resolve_score'].combine(df['bullish_resolve_score'], max)
    df['trend_score'] = trend_score
    top_trend = df.nlargest(20, 'trend_score')
    for _, r in top_trend.iterrows():
        dir_str = "BEAR" if r['bearish_resolve_score'] > r['bullish_resolve_score'] else "BULL"
        print(f"  {r['date']} score={r['trend_score']:.0f} ({dir_str}) range={r['session_range']:.0f} yellows={r['yellow_count']} oranges={r['orange_count']}")

    print(f"\n--- TOP 20 STRONGEST COMPRESSION DAYS ---")
    top_compress = df.nsmallest(20, 'session_range')
    for _, r in top_compress.iterrows():
        print(f"  {r['date']} range={r['session_range']:.0f} breaks={r['strategic_breaks']} transitions={r['quadrant_transitions']}")

    print(f"\n--- TOP 20 STRONGEST RESOLVE DAYS ---")
    df['resolve_score'] = df[['bearish_resolve_score', 'bullish_resolve_score']].max(axis=1)
    top_resolve = df[(df['resolve_score'] >= 4)].nlargest(20, 'resolve_score')
    for _, r in top_resolve.iterrows():
        dir_str = "BEAR" if r['bearish_resolve_score'] > r['bullish_resolve_score'] else "BULL"
        print(f"  {r['date']} resolve={r['resolve_score']:.0f} ({dir_str}) range={r['session_range']:.0f} class={r['classification']}")

    print(f"\nCSV: structure_audit_results.csv ({n} rows)")


if __name__ == "__main__":
    main()
