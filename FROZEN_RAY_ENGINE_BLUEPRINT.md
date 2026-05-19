# FROZEN RAY ENGINE BLUEPRINT

## Purpose

Replace the current rolling least-squares regression line engine with a frozen two-point geometric ray system that faithfully represents Scott's line methodology.

This document defines architecture only. No implementation code until approved.

---

## APPROVED ARCHITECTURE DECISIONS (Scott-approved 2026-05-19)

### Decision 1: P2 Confirmation Logic — APPROVED (D modified)

P2 confirmation requires ALL of:
- One-bar swing confirmation (high[j] > high[j-1] AND high[j] > high[j+1])
- Minimum 10-point threshold from neighbors
- P2 must remain OUTSIDE all CLOSED bars

Purpose: Prevent tiny noise pivots from becoming structure. P2 must represent meaningful structure. Fast enough to react, filtered enough to avoid noise.

### Decision 2: Wick Adjustment Logic — APPROVED (C modified)

When wick pierces line and candle CLOSE remains inside:
- Adjust line AFTER CLOSE only
- Find the MINIMUM slope adjustment required so line again encompasses ALL CLOSED bars
- Preserve original geometry as much as possible
- DO NOT recalculate best fit
- DO NOT flatten excessively

Goal: Smallest legal adjustment. Not a new regression fit.

### Decision 3: Orange/Yellow Retirement — APPROVED (Modified B)

When new session high forms:
- Create new Orange line from new high
- Retire previous Orange (active=False)
- BUT preserve historical structure (do NOT overwrite)

When new session low forms:
- Create new Yellow line from new low
- Retire previous Yellow (active=False)
- BUT preserve historical structure

Reason: Previous Orange/Yellow structure may matter later for touch count, authority, break significance, historical context.

### Decision 4: Touch Proximity — APPROVED (D modified)

Touch threshold is DYNAMIC:
```
proximity_threshold = max(10, 0.5 * average_bar_range_over_lookback)
```

Reason: Fixed thresholds distort touch counts. Quiet days use 10 pts minimum. Volatile days expand naturally. Touch counting reflects market conditions.

### Decision 5: Rescue Line Creation — APPROVED (B)

Create rescue line ONLY IF:
- Parent touch_count >= 3
- AND confirmed structural shift exists (swing in resolve direction)
- AND price resolved away from parent structure

Rescue anchor: second touch point of parent line.

Additional rule: Parent line ALWAYS retains higher authority. Rescue lines never exceed parent authority.

### CRITICAL IMPLEMENTATION RULE

Do not silently simplify architecture.
Do not replace frozen rays with rolling regression.
Do not infer missing behavior.
If implementation requires additional assumptions: STOP AND ASK FIRST.

---

## 1. Data Model — Line Object

Every active line is represented as:

```
Line {
    line_id:            int         # unique identifier
    line_type:          enum        # ORANGE, YELLOW, PURPLE_ORIGINAL, BLUE_ORIGINAL,
                                    # PURPLE_SECONDARY, BLUE_SECONDARY, RESCUE
    authority_rank:     int         # 1=highest (orange/yellow), 2=original purple/blue,
                                    # 3=secondary, 4=rescue
    anchor_p1:          float       # price at Point 1 (anchor)
    anchor_p1_bar:      int         # bar index of P1
    confirmation_p2:    float       # price at Point 2 (confirmed swing)
    confirmation_p2_bar: int        # bar index of P2
    slope:              float       # price change per bar (frozen after P2 confirmation)
    intercept:          float       # price at P1 bar (= anchor_p1)
    created_at_bar:     int         # bar when line was first created
    status:             enum        # PROVISIONAL (P1 only), FROZEN (P1+P2 confirmed),
                                    # ADJUSTING (wick adjust pending), RETIRED
    touch_count:        int         # times price approached and rejected
    wick_adjust_count:  int         # times slope was adjusted after wick pierce
    age:                int         # bars since creation
    parent_line_id:     int|null    # if secondary/rescue, references parent line
    direction:          enum        # RESISTANCE (descending/flat) or SUPPORT (ascending/flat)
}
```

---

## 2. P1 Anchor Logic

### Orange Line
- P1 = session high (highest high seen so far)
- Updates if new session high is made
- When P1 updates, line resets (new line from new high)

### Yellow Line
- P1 = session low (lowest low seen so far)
- Updates if new session low is made
- When P1 updates, line resets (new line from new low)

### Original Purple Line
- P1 = session high (same as orange anchor)
- Created at session start
- Does NOT move when new session high is made (that creates a NEW purple, old one may retire)

### Original Blue Line
- P1 = session low (same as yellow anchor)
- Created at session start
- Does NOT move when new session low is made

### Secondary/Rescue Lines
- P1 = second touch point of parent line
- Created only after price resolves away from parent

---

## 3. P2 Confirmation Logic

### Purple P2 (resistance, descending)
```
WAIT for confirmed swing high:
    bar[j] is a swing high IF:
        high[j] > high[j-1]  (higher than previous bar)
        high[j] > high[j+1]  (higher than next bar — confirmed 1 bar later)
        high[j] < P1 price   (LOWER than anchor — line must descend)
    
    P2 = high[j]
    P2_bar = j
    
    slope = (P2 - P1) / (P2_bar - P1_bar)
    
    VERIFY: slope must be negative (descending)
    VERIFY: line must not pass through any CLOSED bar between P1 and P2
    
    IF verification passes:
        FREEZE line
        status = FROZEN
    ELSE:
        reject P2, continue searching
```

### Blue P2 (support, ascending)
```
WAIT for confirmed swing low:
    bar[j] is a swing low IF:
        low[j] < low[j-1]   (lower than previous bar)
        low[j] < low[j+1]   (lower than next bar — confirmed 1 bar later)
        low[j] > P1 price   (HIGHER than anchor — line must ascend)
    
    P2 = low[j]
    P2_bar = j
    
    slope = (P2 - P1) / (P2_bar - P1_bar)
    
    VERIFY: slope must be positive (ascending)
    VERIFY: line must not pass through any CLOSED bar between P1 and P2
    
    IF verification passes:
        FREEZE line
        status = FROZEN
    ELSE:
        reject P2, continue searching
```

### Orange/Yellow P2
- Orange: fixed slope of -2.5 degrees (no P2 needed, slope is constant)
- Yellow: fixed slope of +2.5 degrees (no P2 needed, slope is constant)
- These lines are always FROZEN immediately (slope is predetermined)

---

## 4. Frozen Ray Behavior

Once a line reaches FROZEN status:

```
FOR each new CLOSED bar:
    line_value_at_bar = intercept + slope * (bar_idx - P1_bar)
    
    DO NOT:
        - refit the line
        - change slope
        - change intercept
        - move anchor points
    
    The line extends as a straight ray indefinitely until retired.
```

Key difference from current engine:
- Current: recalculates slope every bar using least-squares on growing window
- New: slope is fixed at P2 confirmation and never changes (except wick adjustments)

---

## 5. Containment Rule

```
FOR every CLOSED bar in the line's active range:
    IF line is RESISTANCE (purple/orange):
        ASSERT: line_value >= high[bar]
        IF line_value < high[bar]:
            VIOLATION — line is invalid or needs adjustment
    
    IF line is SUPPORT (blue/yellow):
        ASSERT: line_value <= low[bar]
        IF line_value > low[bar]:
            VIOLATION — line is invalid or needs adjustment
```

A line that violates containment on CLOSED bars is structurally invalid.

---

## 6. Wick Adjustment Rule

```
ON each new CLOSED bar:
    IF line is RESISTANCE and high[bar] > line_value:
        # Wick pierced above resistance
        IF close[bar] > line_value:
            # CONFIRMED BREAK — do not adjust, this is a signal event
            EMIT signal: LINE_BREAK(line_id, direction=BULLISH)
        ELSE:
            # Wick pierce only, close held below
            # ADJUST slope so line encompasses this bar's high
            new_slope = (high[bar] - anchor_p1) / (bar_idx - P1_bar)
            
            # Verify new slope still encompasses all previous CLOSED bars
            IF verify_containment(new_slope):
                slope = new_slope
                wick_adjust_count += 1
            ELSE:
                # Cannot adjust without violating other bars
                # Line is becoming invalid — may need retirement
                status = RETIRING
    
    IF line is SUPPORT and low[bar] < line_value:
        # Wick pierced below support
        IF close[bar] < line_value:
            # CONFIRMED BREAK
            EMIT signal: LINE_BREAK(line_id, direction=BEARISH)
        ELSE:
            # Wick pierce only, close held above
            new_slope = (low[bar] - anchor_p1) / (bar_idx - P1_bar)
            IF verify_containment(new_slope):
                slope = new_slope
                wick_adjust_count += 1
            ELSE:
                status = RETIRING
```

### Adjustment direction constraint:
- Resistance lines can only adjust UPWARD (become less steep or more flat)
- Support lines can only adjust DOWNWARD (become less steep or more flat)
- If adjustment would make line horizontal or past horizontal → retire

---

## 7. Touch Counting

```
Definition of a TOUCH:
    Price approaches line within proximity_threshold
    AND
    Price then moves AWAY from line (next bar's close is further from line)
    AND
    No confirmed close beyond line occurred

    proximity_threshold = max(10, 0.5 * average_bar_range_over_lookback)
    # Dynamic: adapts to volatility. Minimum 10 pts.

ON each CLOSED bar:
    distance = abs(relevant_price - line_value)
    # relevant_price = high for resistance, low for support
    
    IF distance <= proximity_threshold:
        IF previous bar was NOT in proximity:
            # New approach
            touch_pending = True
    
    IF touch_pending AND price moved away:
        touch_count += 1
        touch_pending = False

Touch significance:
    1 touch:  line exists but unproven
    2 touches: line is meaningful
    3+ touches: line is strong — high probability of future rejection
```

---

## 8. Line Hierarchy

```
authority_rank mapping:
    1: ORANGE, YELLOW          (session extremes, fixed slope)
    2: PURPLE_ORIGINAL, BLUE_ORIGINAL  (first purple/blue from session start)
    3: PURPLE_SECONDARY, BLUE_SECONDARY (later re-anchored lines)
    4: RESCUE                  (steeper lines from repeated resolution)

Signal weighting:
    break of rank 1 line = highest conviction signal
    break of rank 2 line = standard signal
    break of rank 3 line = moderate signal
    break of rank 4 line = weak signal (may ignore in CHOP)

Conflict resolution:
    IF two lines give opposing signals:
        higher authority wins
    IF same authority:
        higher touch_count wins
```

---

## 9. Rescue Line Creation

```
Trigger:
    Price has touched parent line 2+ times
    AND
    Price is now resolving AWAY from parent line (moving toward opposite side)
    AND
    Distance from parent line > rescue_threshold (e.g., 50 pts)

Creation:
    rescue_P1 = parent line's SECOND touch point (price and bar)
    rescue_P2 = most recent swing point in the resolve direction
    
    slope = (rescue_P2 - rescue_P1) / (rescue_P2_bar - rescue_P1_bar)
    
    VERIFY containment
    IF valid:
        create new line with:
            line_type = RESCUE
            authority_rank = 4
            parent_line_id = parent.line_id
            status = FROZEN

Purpose:
    Captures newly forming structure when price has moved away from original lines.
    Provides tighter stop/entry levels.
    Lower authority — breaks of rescue lines are less significant.
```

---

## 10. Retirement Rules

A line is retired (removed from active set) when:

```
1. HORIZONTAL: slope has been adjusted to 0 or past horizontal
   - Resistance with positive slope = past horizontal → retire
   - Support with negative slope = past horizontal → retire

2. INVALIDATED: confirmed close beyond line
   - After a break signal is emitted, the line is no longer valid structure
   - Mark as RETIRED

3. SUPERSEDED: new session extreme creates a new primary line
   - When new session high → new orange/purple created
   - Old orange/purple may be retired if price has moved far away

4. AGE: line has not been touched in N bars (e.g., 100 bars)
   - If price has moved far from line and never returns, line is irrelevant

5. STRUCTURALLY IRRELEVANT: line is far from current price action
   - If line_value is > 200 pts from current price, retire
```

---

## 11. Signal Interpretation

### CHOP Mode (default assumption)
```
Lines are BUMPERS. Trade AGAINST approach.

ON touch event (price approaches line without break):
    IF resistance line touched:
        SIGNAL: SELL (expect rejection downward)
        confidence = authority_rank * touch_count
    IF support line touched:
        SIGNAL: BUY (expect rejection upward)
        confidence = authority_rank * touch_count
```

### TREND Mode (confirmed by break)
```
Lines are BREAKOUT LEVELS. Trade WITH confirmed close.

ON confirmed break (close beyond line):
    IF close ABOVE resistance:
        SIGNAL: BUY (breakout, trend continuation)
        confidence = authority_rank
    IF close BELOW support:
        SIGNAL: SELL (breakdown, trend continuation)
        confidence = authority_rank
```

### Mode determination
```
Same lines, different interpretation.
Mode is determined by:
    - resolve state (are new extremes being made?)
    - failed expansions (is momentum fading?)
    - evidence accumulation (which direction has more weight?)

The line engine itself does NOT determine mode.
The belief engine determines mode and interprets line events accordingly.
```

---

## 12. Visualization Test Requirements

### Chart must prove:
1. No line passes through any CLOSED candle body or wick
2. Lines are continuous straight rays (no jumps between bars)
3. Touch counts are visible (annotated on chart)
4. Authority ranks are color-coded:
   - Orange/Yellow: rank 1 (thickest)
   - Original Purple/Blue: rank 2
   - Secondary: rank 3 (thinner)
   - Rescue: rank 4 (thinnest/dashed)
5. Wick adjustments are visible (slope change after pierce)
6. Retired lines are grayed out

### Automated validation (20 random days):
```
FOR each day:
    FOR each active line:
        FOR each CLOSED bar in line's range:
            IF resistance: ASSERT line_value >= high
            IF support: ASSERT line_value <= low
    
    Report:
        violation_count (must be 0)
        touch_counts per line
        authority_ranks
        wick_adjustments
        retirements
```

---

## 13. Acceptance Criteria

The new engine PASSES if and only if:

| Criterion | Requirement |
|-----------|-------------|
| Body violations | ZERO on closed bars |
| Wick violations | ZERO on closed bars (line must encompass) |
| Line jumps >5pts | ZERO (lines are frozen rays) |
| Containment | 100% — every line stays outside closed price |
| Continuity | Lines extend as straight rays until retired |
| Hierarchy | Authority ranks correctly assigned and used |
| Touch counting | Accurate count matching visual inspection |
| Freeze behavior | Lines do NOT move while bar is open |
| Wick adjustment | Slope adjusts ONLY after close, ONLY if wick pierced |
| Signal generation | Only from frozen line interactions (touch or break) |
| Regression test | Run on same 20 days as current audit — zero violations |

---

## 14. Implementation Phases (proposed)

### Phase 1: Core ray engine
- Line data model
- P1/P2 detection
- Freeze logic
- Containment verification
- Replace `_compute_rays_nb`

### Phase 2: Adjustment and retirement
- Wick adjustment after close
- Retirement rules
- Secondary/rescue line creation

### Phase 3: Touch counting and hierarchy
- Touch detection
- Authority ranking
- Signal weighting

### Phase 4: Integration
- Wire into belief engine
- Signal interpretation (CHOP/TREND)
- Backtest validation

### Phase 5: Visualization
- Chart rendering with new lines
- Automated violation testing
- 20-day audit (must pass with zero violations)

---

## 15. What This Replaces

| Current (rolling regression) | New (frozen rays) |
|------------------------------|-------------------|
| `_fit_trendlines_nb` | Eliminated |
| `_compute_rays_nb` (purple/blue section) | Replaced with frozen ray logic |
| Slope recalculated every bar | Slope frozen at P2 confirmation |
| No touch counting | Full touch tracking |
| No hierarchy | 4-level authority system |
| Lines jump between bars | Lines are continuous rays |
| 440 containment violations per 20 days | Zero violations |
| 529 discontinuous jumps per 20 days | Zero jumps |

---

## Approval Required

All 5 architecture questions have been APPROVED by Scott (2026-05-19).
See "APPROVED ARCHITECTURE DECISIONS" section at top of document.
No further approval needed for implementation to begin.

Remaining open items (ask if encountered during implementation):
- None currently. All decisions are locked.
