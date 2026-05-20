---
inclusion: auto
description: "Final architecture principles: quadrant-first, 4-layer separation, evidence accumulation, no line-cross signals"
---

# FRED ARCHITECTURE PRINCIPLES — Final (Scott-approved 2026-05-19)

## NEVER DO THIS

- Line cross → immediate order
- Continuously create new lines after every turn
- Treat steeper lines as predictive
- Merge strategic and tactical purposes
- React to every price movement with new structure
- Assign permanent fixed meaning to a line
- Treat a line as dead after one crossing

## ALWAYS DO THIS

- Quadrant transition → evidence → conviction → execution
- Wait for structure to PROVE itself before creating steeper lines
- Separate strategic thesis from tactical management
- Accumulate evidence before acting
- Allow price to breathe inside structure
- Recognize that line meaning EVOLVES with market context
- Same line can shift role as conviction changes

## CORE PRINCIPLE: Lines Are Evolving Evidence

A line does NOT have permanent fixed purpose.
The same line changes role depending on market context.

### FAILED ATTEMPTS ARE EVIDENCE FOR THE OTHER SIDE

This is the most critical evidence rule:
- If bears repeatedly attempt lower and CANNOT close below yellow → bullish evidence increases
- If bulls repeatedly attempt higher and CANNOT maintain structure → bearish evidence increases

Scott is not measuring line interactions. Scott is measuring WHICH SIDE WON THE ATTEMPT.

**CRITICAL: Failed attempts accumulate gradually, not instantly.**

Engine flow: Attempt → Failure observed → Counter-evidence accumulates → Winner score changes → Belief evolves → Trade

A single failed attempt is NOT a reversal signal. It is one data point.
- 1 failed close below yellow: interesting (counter-evidence +0.5)
- 2 failed closes: possible trapped bears (counter-evidence +1.0)
- 3 failed closes + blue reclaim: bullish argument strengthening (counter-evidence +2.0)

Failure alone is not reversal.
Failure + accumulation + structure response = belief shift.

Scott does not instantly flip sides. He gradually realizes one side is losing the argument.

### Probe Trades

Trades are not only for profit. Small probe trades gather information.
Risk small + information large = valid trade.
FRED should be capable of low-risk probes at structural boundaries to test thesis.

### State Labels vs Argument Evaluation

FRED currently labels states: "I am in BEARISH_CONVICTION"
Scott evaluates arguments: "Which side is winning right now?"

The engine must track:
- Who is attempting (bulls or bears)
- What they're attempting (break a line, hold structure, reclaim)
- Whether they succeeded or failed
- What that outcome means for the evolving argument

Example — Continuation Blue during downward resolve:
- Initial role: "Is bearish resolve still healthy?"
- Price closes below → bearish conviction increases
- Price cannot break below → bearish conviction weakens

If market later reverses upward:
- The SAME Blue changes role
- Now asks: "Can price reclaim and live above me?"
- If yes → old bearish evidence becomes bullish support evidence
- Belief shifts: bearish thesis → weakening → neutral → bullish thesis

Do not think: "line crossed → signal"
Think: "evidence changed → belief changed"

Lines are not static objects. They are participants in evolving conviction.

### CRITICAL REFINEMENT: Belief Evolves Slowly

Line meaning evolves. Belief evolves MORE SLOWLY.
Do NOT fully reinterpret line meaning every bar.
Scott does not change convictions on every candle.

Evidence accumulates. Questions evolve GRADUALLY:
- bearish continuation → weakening bearish thesis → transition → bullish support candidate → bullish confirmation

The line may stay identical geometrically. Only its contextual meaning changes over time.

Belief requires ACCUMULATED evidence. Not single-bar reactions.
Otherwise we recreate chop behavior using smarter language.

Conviction state transitions require MULTIPLE confirming bars, not one.

## CORE SEPARATION

### Strategic Lines (Original structure)
- Orange / Yellow / Original Purple / Original Blue
- Purpose: "Is my thesis still alive?"
- Created at session start or on new session extremes
- FROZEN. Never move. Never redraw.
- Breaking these = thesis change (potential reversal)

### Tactical Lines (Steeper / rescue / profit protection)
- Created ONLY after price PROVES continuation
- Purpose: "How much profit do I protect?"
- NOT entry signals. NOT predictive.
- Require: resolve → counter-move → failed reversal → renewed continuation
- Only THEN does steeper structure appear

## STEEPER LINE CREATION CRITERIA

A steeper line is created ONLY when ALL of:
1. Original structure exists and is active
2. Price resolved away from original structure
3. Price attempted countertrend move
4. Original structure HELD (was not broken)
5. Price resumed in trend direction
6. Price created NEW extremes beyond the counter-move

If ANY condition is not met: DO NOTHING. WAIT.

## THE 4-LAYER ARCHITECTURE

```
Layer 1: STRUCTURE ENGINE
  Computes frozen rays. Maintains quadrants.
  No signals. No execution.

Layer 2: EVIDENCE ENGINE
  Observes behavior. Counts touches, breaks, failed bounces.
  Tracks quadrant transitions.
  No execution.

Layer 3: CONVICTION ENGINE
  Weighs evidence. Determines belief state.
  Decides when conviction is sufficient.
  Outputs: ready / not-ready.

Layer 4: EXECUTION ENGINE
  Only fires when Layer 3 says "ready."
  Entry at tactical levels.
  Stop at strategic levels.
```

## QUADRANT STATE MACHINE

```
NEUTRAL:     Price between Blue and Purple (inner boundaries)
EMERGING:    Price broke one inner boundary, evidence accumulating
ESTABLISHED: Multiple failed bounces, continuation confirmed
STRONG:      Outer boundary (Orange/Yellow) broken
```

## MULTI-TIMEFRAME AUTHORITY

```
Weekly    = 10
Daily     = 8
4-hour    = 6
30-minute = 4
1-minute original = 3
1-minute rescue   = 1
```

Higher timeframe lines create HIGH ATTENTION ZONES, not automatic signals.

## IMPLEMENTATION RULE

If implementation requires assumptions not covered here: STOP AND ASK.
Do not silently simplify. Do not collapse layers. Do not merge purposes.
