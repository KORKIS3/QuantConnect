---
inclusion: auto
description: "Post-rebuild reset: all prior market classifications invalid after frozen-ray engine, recompute from zero"
---

# POST-REBUILD RESET — Classification Studies Invalid

## After frozen-ray engine implementation completes:

ALL prior market classifications must be recomputed from scratch.

### INVALID (generated from old regression engine):
- 550/565 CHOP day classification
- 15/565 TREND day classification
- TREND false positive analysis
- First-hour weakness statistics
- Session window P/L breakdowns
- Opportunity window rankings
- Day-type conditional parameters

### WHY:
The old engine generated signals from rolling regression lines.
The new engine generates signals from structural quadrants.
These are fundamentally different market models.
Classifications from one cannot be assumed valid for the other.

### RECOMPUTE FROM ZERO:
- Chop frequency (quadrant-based: price stays inside boundaries)
- Trend frequency (quadrant-based: price breaks through and continues)
- Compression frequency (quadrant narrows → breakout imminent)
- Resolve continuation patterns
- Multi-timeframe conflict zones
- Quadrant transition statistics
- Touch behavior per line type and authority
- Conviction state distributions
- Evidence accumulation patterns

### STILL VALID (behavioral observations, not engine-dependent):
- QUICK_KILL concept (immediately-wrong entries identifiable by bar 3)
- MFE/MAE separation (winners move favorably from bar 1)
- EXIT_FLAT loss patterns (entries that never work)
- Protected component concept (CHOP_TP / PARTIAL_TP mechanics)
- Session discipline principles (waiting, not chasing)
- Profit protection concept (tactical vs strategic)

### TREAT POST-REBUILD AS:
A new species of engine.
Do not carry forward assumptions.
Validate everything empirically.
