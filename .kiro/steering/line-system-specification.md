---
inclusion: auto
description: "Frozen ray line system specification: containment rules, freeze behavior, hierarchy, touch counting"
---

# FRED LINE SYSTEM SPECIFICATION

## STATUS: LINE ENGINE REBUILD REQUIRED

All strategy optimization and backtesting is PAUSED until the line engine faithfully represents Scott's methodology.

The current engine uses rolling least-squares regression. Scott uses frozen two-point geometric rays. These produce fundamentally different signals.

## CORE PRINCIPLE

Lines are NOT indicators.
Lines are dynamic structural boundaries.
Lines determine confidence and probability.
Lines NEVER pass through candle bodies or wicks OF CLOSED BARS.
Lines ALWAYS encompass price.
A line exists outside price and acts as a boundary.
If a line cuts through CLOSED bars, the line is invalid.

## CRITICAL RULE — LINE FREEZE BEHAVIOR

Only CLOSED bars are evaluated.
OPEN bars are still forming and are ignored for line adjustment.

While a bar is actively printing:
- FREEZE all existing line positions
- Do NOT move lines
- Do NOT adjust slope
- Do NOT recalculate anchors
- Do NOT modify structure
- Wait until candle close

Only AFTER a candle closes, evaluate:
- Did candle CLOSE beyond the line?
- IF NO: Line remains valid. If wick pierced but close remained inside → adjust slope AFTER close so line again encompasses all CLOSED bars.
- IF YES: This is a confirmed line-break event. Apply CHOP or TREND interpretation.

Lines cannot move while price is still printing. Otherwise the line continuously chases price and valid crosses never occur. Line movement ONLY happens AFTER completed candle close.

## LINE HIERARCHY

1. Highest authority: Orange, Yellow
2. Second: Original Purple, Original Blue
3. Third: Secondary Purple, Secondary Blue
4. Lowest: Steeper rescue lines

NOT all line breaks have equal significance. Higher authority = higher probability.

## ORANGE LINE

- Anchor: Current day high
- Behavior: Very shallow inward slope (~2.5 degrees)
- Purpose: Highest authority resistance
- Must remain OUTSIDE all CLOSED bars

## YELLOW LINE

- Anchor: Current day low
- Behavior: Very shallow inward slope (~2.5 degrees)
- Purpose: Highest authority support
- Must remain OUTSIDE all CLOSED bars

## ORIGINAL PURPLE LINE

- Anchor: Day high
- Behavior: Slope downward toward next major lower high while staying OUTSIDE CLOSED price bars
- Purpose: Primary upper containment structure
- Must encompass bars
- Must never intersect CLOSED candles
- Higher authority than later rescue lines

## ORIGINAL BLUE LINE

- Anchor: Day low
- Behavior: Slope upward toward next major higher low while staying OUTSIDE CLOSED price bars
- Purpose: Primary lower containment structure
- Must encompass bars
- Must never intersect CLOSED candles
- Higher authority than later rescue lines

## LINE ADJUSTMENT RULES

Wicks DO NOT invalidate a line. Only CLOSED bars matter.

Example: Price wick pierces line intrabar. Bar eventually closes back inside. This is NOT a break.

After close: adjust slope so line again encompasses all CLOSED bars.
Continue adjusting only after completed closes.
Continue until: line becomes horizontal OR past horizontal.
Then: remove line. Line no longer relevant.

## SECONDARY / RESCUE LINES

If price repeatedly resolves away from original line: create steeper line.
- Anchor: SECOND touch point of original line
- Purpose: capture newly forming structure
- Lower authority

## TOUCH COUNT LOGIC

Track: touch_count

Definition: Price approaches line and changes direction WITHOUT confirmed close beyond.

- 1 touch: weak
- 2 touches: meaningful
- 3+ touches: strong

Higher touch count = stronger probability.

Track for every line: touch_count, line_age, line_type, authority_rank, slope, anchor

## CHOP INTERPRETATION

In CHOP: Lines behave as bumpers. Trade AGAINST approach.
- Price approaches purple resistance: SHORT
- Price approaches blue support: LONG
- Expect rejection. Ping-pong behavior.
- Highest probability: Orange/Yellow, then Original Purple/Blue, then later lines

## TREND INTERPRETATION

Same exact lines. Different interpretation. Only CLOSED bar beyond line matters.
- Close above purple: BUY
- Close below blue: SELL
- Break original lines > break rescue lines
- Break orange/yellow = highest conviction

## CURRENT AUDIT RESULTS (from run_line_audit.py)

- 128 body violations (lines cutting through closed candles)
- 440 containment failures (resistance below highs / support above lows)
- 529 discontinuous jumps (>20pts between bars)
- No line hierarchy implemented
- No touch counting implemented
- No freeze behavior (lines recalculate every bar)

## REBUILD REQUIREMENTS

The line engine must be rewritten to:
1. Use two-point frozen rays (P1 anchor → P2 confirmed swing)
2. Never pass through closed candle bodies or wicks
3. Only adjust after candle close
4. Track touch count per line
5. Maintain line hierarchy (orange/yellow > original purple/blue > secondary)
6. Support line invalidation (horizontal or past-horizontal = removed)
7. Support secondary/rescue line creation from second touch point
