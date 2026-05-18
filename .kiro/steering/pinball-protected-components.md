---
inclusion: auto
---

# Pinball Protected Components

## CHOP_TP and PARTIAL_TP are PROTECTED

These two trade types represent the core edge of the Pinball system. Their entry and exit logic must NEVER be modified.

### Protected Logic (DO NOT CHANGE):
- CHOP_TP: Fixed TP at 30 pts when price reaches target from rejection entry
- PARTIAL_TP: Book 1 contract at 50 pts unrealized profit

### Baseline Values (Pinball v4, 565 days):
- CHOP_TP: 955 trades, +77,928 pts, avg +81.6, 100% win rate
- PARTIAL_TP: 1,021 trades, +60,388 pts, avg +59.1, 100% win rate
- Combined: +138,316 pts (the entire positive edge)

### Regression Check (MANDATORY for every experiment):
Every future backtest MUST report:
1. CHOP_TP total P/L
2. PARTIAL_TP total P/L

If either decreases by more than 5% from baseline:
- FLAG AS REGRESSION
- DO NOT proceed with that change
- Investigate why the protected component was affected

### Optimization Focus (ALLOWED changes):
- False trend detection / entry filtering
- EXIT_FLAT loss reduction (currently -111,629 pts)
- EARLY_HARD_STOP loss reduction (currently -34,859 pts)
- Session timing / window scheduling
- Hybrid scheduling (skip toxic windows)
- Trade management after entry (trailing stops, faster exits)
- TREND mode entry criteria tightening

### Forbidden Changes:
- CHOP_TP threshold (30 pts)
- PARTIAL_TP threshold (50 pts)
- Rejection entry logic for CHOP bounces
- Line proximity detection for CHOP entries
- Any logic that would reduce the number of CHOP_TP or PARTIAL_TP events
