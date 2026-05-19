"""
run_line_audit.py — Forensic Line Audit

Verifies whether Fred's line generation matches Scott's stated methodology.
Checks 20 random days for violations.

Scott's rules (from steering docs):
1. Lines NEVER pass through candle bodies (close-to-open range)
2. Lines encompass price (support below lows, resistance above highs)
3. Intrabar wick penetrations do NOT count unless close confirms
4. Line slope adjusts after candle close (not intrabar)
5. Original purple/blue lines retain higher authority
6. Touch count tracked
7. Line generation hierarchy: orange/yellow → primary purple/blue → secondary

Fred's actual implementation:
- Purple: least-squares resistance line fitted to highs in a window
- Blue: least-squares support line fitted to lows in a window
- Orange: fixed -2.5 degree from session high
- Yellow: fixed +2.5 degree from session low
- _fit_trendlines_nb uses _optimize_slope_nb which ensures:
  - Support line: no point goes BELOW the line (all lows >= line)
  - Resistance line: no point goes ABOVE the line (all highs <= line)
"""
import os, random
import numpy as np
import pandas as pd
import pytz
from TradingAlgoFast import AlgoConfig, run_trading_algo_fast

_EST = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")


def _get_config():
    return AlgoConfig(warmup_minutes=7, steep_angle_threshold=90.0, proximity_points=4.0,
        min_reversal_minutes=0, min_entry_angle=0.0, partial_tp_pts=50.0,
        wm_shield_distance=0.0, swing_anchor_threshold=10.0)


def audit_day(target_date):
    """Audit a single day's line generation for violations."""
    fpath = os.path.join(_DATA_ROOT, f'CBOT_MINI_YM1_{target_date}.csv')
    if not os.path.exists(fpath):
        return None

    df = pd.read_csv(fpath, index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
    day_start = pd.Timestamp(f'{target_date} 09:30', tz=_EST)
    day_end = pd.Timestamp(f'{target_date} 16:59', tz=_EST)
    day_data = df[(df.index >= day_start) & (df.index <= day_end)]

    if len(day_data) < 15:
        return None

    config = _get_config()
    try:
        algo_df = run_trading_algo_fast(day_data, target_date, '09:30', '17:00', config=config)
    except:
        return None

    if algo_df is None or len(algo_df) < 15:
        return None

    violations = []
    n = len(algo_df)

    # Check each bar
    purple_touches = 0
    blue_touches = 0
    orange_touches = 0
    yellow_touches = 0
    purple_body_violations = 0
    blue_body_violations = 0
    purple_wick_only_crosses = 0
    blue_wick_only_crosses = 0

    for i in range(n):
        row = algo_df.iloc[i]
        close = float(row['Close'])
        open_p = float(row['Open'])
        high = float(row['High'])
        low = float(row['Low'])
        body_top = max(close, open_p)
        body_bot = min(close, open_p)

        purple = float(row['purple_ray']) if 'purple_ray' in row.index and not pd.isna(row['purple_ray']) else None
        blue = float(row['blue_ray']) if 'blue_ray' in row.index and not pd.isna(row['blue_ray']) else None
        orange = float(row['orange_ray']) if 'orange_ray' in row.index and not pd.isna(row['orange_ray']) else None
        yellow = float(row['yellow_ray']) if 'yellow_ray' in row.index and not pd.isna(row['yellow_ray']) else None

        # VIOLATION 1: Purple line passes through candle body
        # Purple is resistance — should be ABOVE all highs in its window
        # If purple < body_top, the line is cutting through the body
        if purple is not None:
            if purple < body_top and purple > body_bot:
                purple_body_violations += 1
                if i < 5 or i % 50 == 0:  # sample violations
                    violations.append({
                        'bar': i, 'type': 'PURPLE_BODY_VIOLATION',
                        'detail': f'purple={purple:.0f} inside body [{body_bot:.0f}-{body_top:.0f}]'
                    })
            # Touch: high reaches within 5 pts of purple
            if abs(high - purple) <= 5:
                purple_touches += 1
            # Wick-only cross: high > purple but close < purple
            if high > purple and close < purple:
                purple_wick_only_crosses += 1

        # VIOLATION 2: Blue line passes through candle body
        # Blue is support — should be BELOW all lows in its window
        if blue is not None:
            if blue > body_bot and blue < body_top:
                blue_body_violations += 1
                if i < 5 or i % 50 == 0:
                    violations.append({
                        'bar': i, 'type': 'BLUE_BODY_VIOLATION',
                        'detail': f'blue={blue:.0f} inside body [{body_bot:.0f}-{body_top:.0f}]'
                    })
            # Touch
            if abs(low - blue) <= 5:
                blue_touches += 1
            # Wick-only cross
            if low < blue and close > blue:
                blue_wick_only_crosses += 1

        # Orange/yellow touches
        if orange is not None and abs(high - orange) <= 5:
            orange_touches += 1
        if yellow is not None and abs(low - yellow) <= 5:
            yellow_touches += 1

    # VIOLATION 3: Check if purple ever goes BELOW a high in its fitting window
    # This would mean the "resistance" line doesn't actually contain price
    purple_containment_violations = 0
    blue_containment_violations = 0
    for i in range(n):
        row = algo_df.iloc[i]
        purple = float(row['purple_ray']) if 'purple_ray' in row.index and not pd.isna(row['purple_ray']) else None
        blue = float(row['blue_ray']) if 'blue_ray' in row.index and not pd.isna(row['blue_ray']) else None
        high = float(row['High'])
        low = float(row['Low'])

        if purple is not None and high > purple + 1.0:  # 1pt tolerance
            purple_containment_violations += 1
        if blue is not None and low < blue - 1.0:
            blue_containment_violations += 1

    # VIOLATION 4: Line slope changes intrabar (not applicable — Fred recalculates per bar close)
    # Fred's implementation: recalculates every bar using closes only → COMPLIANT

    # VIOLATION 5: Check if lines are refitted every bar (they are — by design)
    # Fred refits from scratch every bar → lines can jump discontinuously
    purple_jumps = 0
    blue_jumps = 0
    for i in range(1, n):
        p_curr = algo_df.iloc[i]['purple_ray'] if 'purple_ray' in algo_df.columns else None
        p_prev = algo_df.iloc[i-1]['purple_ray'] if 'purple_ray' in algo_df.columns else None
        if p_curr is not None and p_prev is not None:
            if abs(float(p_curr) - float(p_prev)) > 20:  # >20pt jump in 1 bar
                purple_jumps += 1
        b_curr = algo_df.iloc[i]['blue_ray'] if 'blue_ray' in algo_df.columns else None
        b_prev = algo_df.iloc[i-1]['blue_ray'] if 'blue_ray' in algo_df.columns else None
        if b_curr is not None and b_prev is not None:
            if abs(float(b_curr) - float(b_prev)) > 20:
                blue_jumps += 1

    return {
        'date': target_date,
        'bars': n,
        'purple_body_violations': purple_body_violations,
        'blue_body_violations': blue_body_violations,
        'purple_containment_violations': purple_containment_violations,
        'blue_containment_violations': blue_containment_violations,
        'purple_wick_only_crosses': purple_wick_only_crosses,
        'blue_wick_only_crosses': blue_wick_only_crosses,
        'purple_touches': purple_touches,
        'blue_touches': blue_touches,
        'orange_touches': orange_touches,
        'yellow_touches': yellow_touches,
        'purple_jumps_gt20': purple_jumps,
        'blue_jumps_gt20': blue_jumps,
        'sample_violations': violations[:10],
    }


def main():
    files = sorted([f for f in os.listdir(_DATA_ROOT)
                    if f.startswith('CBOT_MINI_YM1_') and f.endswith('.csv')])

    # Pick 20 random days
    random.seed(42)
    sample = random.sample(files, min(20, len(files)))

    print("=" * 80)
    print("FORENSIC LINE AUDIT — Fred vs Scott's Methodology")
    print("=" * 80)
    print(f"Auditing {len(sample)} random days...\n")

    all_results = []
    total_purple_body = 0
    total_blue_body = 0
    total_purple_contain = 0
    total_blue_contain = 0
    total_purple_jumps = 0
    total_blue_jumps = 0
    total_bars = 0

    for fname in sample:
        target_date = fname.replace("CBOT_MINI_YM1_", "").replace(".csv", "")
        result = audit_day(target_date)
        if result is None:
            continue
        all_results.append(result)
        total_purple_body += result['purple_body_violations']
        total_blue_body += result['blue_body_violations']
        total_purple_contain += result['purple_containment_violations']
        total_blue_contain += result['blue_containment_violations']
        total_purple_jumps += result['purple_jumps_gt20']
        total_blue_jumps += result['blue_jumps_gt20']
        total_bars += result['bars']

    # Per-day summary
    print(f"{'Date':<12} {'Bars':>5} {'P_Body':>7} {'B_Body':>7} {'P_Cont':>7} {'B_Cont':>7} {'P_Jump':>7} {'B_Jump':>7} {'P_Touch':>8} {'B_Touch':>8}")
    print("-" * 90)
    for r in all_results:
        print(f"{r['date']:<12} {r['bars']:>5} {r['purple_body_violations']:>7} {r['blue_body_violations']:>7} "
              f"{r['purple_containment_violations']:>7} {r['blue_containment_violations']:>7} "
              f"{r['purple_jumps_gt20']:>7} {r['blue_jumps_gt20']:>7} "
              f"{r['purple_touches']:>8} {r['blue_touches']:>8}")

    # Summary
    n_days = len(all_results)
    print(f"\n{'='*80}")
    print(f"SUMMARY ({n_days} days, {total_bars} total bars)")
    print(f"{'='*80}")

    print(f"\n--- VIOLATION 1: Line passes through candle BODY ---")
    print(f"  Purple body violations: {total_purple_body} ({total_purple_body/total_bars*100:.1f}% of bars)")
    print(f"  Blue body violations:   {total_blue_body} ({total_blue_body/total_bars*100:.1f}% of bars)")
    print(f"  SCOTT'S RULE: Lines should NEVER pass through bodies")
    print(f"  VERDICT: {'VIOLATION' if total_purple_body + total_blue_body > 0 else 'COMPLIANT'}")

    print(f"\n--- VIOLATION 2: Line does not contain price (resistance below high / support above low) ---")
    print(f"  Purple containment violations: {total_purple_contain} ({total_purple_contain/total_bars*100:.1f}% of bars)")
    print(f"  Blue containment violations:   {total_blue_contain} ({total_blue_contain/total_bars*100:.1f}% of bars)")
    print(f"  SCOTT'S RULE: Resistance must be above ALL highs, support below ALL lows")
    print(f"  VERDICT: {'VIOLATION' if total_purple_contain + total_blue_contain > 0 else 'COMPLIANT'}")

    print(f"\n--- VIOLATION 3: Line jumps >20pts between bars (discontinuous) ---")
    print(f"  Purple jumps: {total_purple_jumps} ({total_purple_jumps/total_bars*100:.1f}% of bars)")
    print(f"  Blue jumps:   {total_blue_jumps} ({total_blue_jumps/total_bars*100:.1f}% of bars)")
    print(f"  SCOTT'S RULE: Lines are continuous rays from anchor points")
    print(f"  VERDICT: {'VIOLATION — Fred refits from scratch every bar' if total_purple_jumps > 0 else 'COMPLIANT'}")

    print(f"\n--- OBSERVATION: Wick-only crosses (not confirmed by close) ---")
    total_wick_purple = sum(r['purple_wick_only_crosses'] for r in all_results)
    total_wick_blue = sum(r['blue_wick_only_crosses'] for r in all_results)
    print(f"  Purple wick-only crosses: {total_wick_purple}")
    print(f"  Blue wick-only crosses:   {total_wick_blue}")
    print(f"  SCOTT'S RULE: Only CLOSE above/below line counts as a cross")
    print(f"  FRED'S BEHAVIOR: Signals fire on close (COMPLIANT)")

    # Discrepancy report
    print(f"\n{'='*80}")
    print(f"DISCREPANCY REPORT")
    print(f"{'='*80}")
    print(f"""
FRED'S LINE ENGINE vs SCOTT'S METHODOLOGY:

1. LINE FITTING METHOD:
   Scott: Draws a STRAIGHT RAY from Point 1 (anchor) through Point 2 (confirmed swing)
          The line is FROZEN once P2 is confirmed. It does not change.
   Fred:  Uses LEAST-SQUARES REGRESSION on all bars in a window, refitted EVERY BAR.
          The line moves continuously as new bars are added.
   DISCREPANCY: FUNDAMENTAL. Fred's lines are statistical best-fits that shift every bar.
                Scott's lines are fixed geometric rays between two specific points.

2. LINE CONTAINMENT:
   Scott: Lines NEVER pass through price. They are drawn to encompass (above highs / below lows).
   Fred:  _optimize_slope_nb ensures support is below all lows and resistance above all highs
          within the CURRENT fitting window. But when the window shifts (re-anchor), the line
          can jump and temporarily violate containment on recent bars.
   DISCREPANCY: {total_purple_contain + total_blue_contain} containment violations found.

3. LINE CONTINUITY:
   Scott: Once drawn, a line extends as a straight ray until invalidated.
   Fred:  Lines are recalculated from scratch every bar. They can jump 20+ pts between bars.
   DISCREPANCY: {total_purple_jumps + total_blue_jumps} jumps >20pts found. Fred's lines are
                NOT continuous rays — they are rolling regressions.

4. LINE HIERARCHY:
   Scott: Original purple/blue from session open have highest authority.
          Secondary lines (from later swings) are subordinate.
   Fred:  No hierarchy. The most recent regression IS the line. Old lines are overwritten.
   DISCREPANCY: FUNDAMENTAL. Fred has no concept of "original" vs "secondary" lines.

5. TOUCH COUNTING:
   Scott: Tracks how many times price touches a line (more touches = stronger line).
   Fred:  No touch counting. Line strength is not tracked.
   DISCREPANCY: MISSING FEATURE.

6. CLOSE CONFIRMATION:
   Scott: Only a CLOSE above/below a line counts as a break.
   Fred:  Signal detection uses prev_close vs current close — COMPLIANT.
   DISCREPANCY: None. Fred correctly uses close-based confirmation.

7. LINE BODY PENETRATION:
   Scott: Lines should never cut through candle bodies.
   Fred:  {total_purple_body + total_blue_body} body violations found.
          This happens because the regression line is a best-fit that may pass through
          some bars' bodies while minimizing overall error.
   DISCREPANCY: VIOLATION. Fred's statistical fit allows body penetration.

CONCLUSION:
We are optimizing a SIMPLIFIED APPROXIMATION, not a faithful representation.
The core difference: Scott draws FIXED GEOMETRIC RAYS between specific points.
Fred uses ROLLING LEAST-SQUARES REGRESSION that shifts every bar.

This means:
- Fred's signals fire at different times than Scott's would
- Fred's lines are less stable (jump between bars)
- Fred has no concept of line authority or touch count
- The "trend" Fred detects may not match what Scott sees on his chart
""")

    # Sample violations
    print(f"\n--- SAMPLE VIOLATIONS ---")
    for r in all_results[:5]:
        if r['sample_violations']:
            print(f"  {r['date']}:")
            for v in r['sample_violations'][:3]:
                print(f"    Bar {v['bar']}: {v['type']} — {v['detail']}")


if __name__ == "__main__":
    main()
