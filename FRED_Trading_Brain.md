# FRED Trading Brain — Master Rule Document

**Generated**: 2026-05-16
**Sources**: trading-system.md, trading-philosophy.md, SIM/sim_trade_analysis.csv, SIM/validation_results.csv, git commit history, markdown docs
**Method**: Every rule below has a source citation. Rules labeled [INFERENCE] are derived from patterns, not explicit statements.

---

## 1. ENTRY RULES

| # | Rule | Source | Evidence |
|---|------|--------|----------|
| E1 | Enter on a CLOSE across a line — never on intrabar wick or high/low | trading-philosophy.md (Mike Aston section) | "Enter on a close across a line — never on an intrabar wick or high/low" |
| E2 | Wait 7-12 bars (warmup) before first signal | trading-system.md | "warmup_minutes=12, first signal fires on 9:42 close"; best commit used warmup=7 |
| E3 | Close above purple ray = BUY (upward breakout of resistance) | trading-philosophy.md | Mike Aston Entry Rules #4 |
| E4 | Close below blue ray = SELL (downward break of support) | trading-philosophy.md | Mike Aston Entry Rules #5 |
| E5 | Close above orange ray = BUY (stronger signal, shallower line) | trading-philosophy.md | Mike Aston Entry Rules #6 |
| E6 | Close below yellow ray = SELL (stronger signal, shallower line) | trading-philosophy.md | Mike Aston Entry Rules #7 |
| E7 | First trade of day should be in direction of established trend | trading-philosophy.md | Mike Aston Entry Rules #3 |
| E8 | User enters ONE BAR AFTER first cross (confirmation bar) | trading-system.md | "user appears to enter one bar after the first cross (not on the first cross itself)" |
| E9 | Wait for purple or blue to reach minimum angle before first entry | trading-system.md | "min_entry_angle=30.0 — wait for purple or blue to reach 30° before first entry" |
| E10 | Patient first entry — wait for clear setup, don't chase the open | trading-system.md | "user waits for a clear setup to develop before the first trade" |
| E11 | Best trades are obvious — if you have to talk yourself into it, skip | trading-philosophy.md | "The best trades are obvious. If you have to talk yourself into a trade, it's probably not a good one." |

---

## 2. EXIT RULES

| # | Rule | Source | Evidence |
|---|------|--------|----------|
| X1 | Draw steeper line (~60°) from most recent swing low (longs) or swing high (shorts) as price moves in favor | trading-philosophy.md | Mike Aston Exit Rules #1 |
| X2 | If price closes across that steeper trailing line → exit | trading-philosophy.md | Mike Aston Exit Rules #2 |
| X3 | If price continues moving away → tighten line further (draw even steeper line from next swing point) | trading-philosophy.md | Mike Aston Exit Rules #3 |
| X4 | Partial take profit: close 1 of 2 contracts at +50pts | trading-system.md | "partial_tp_pts=50.0 — close 1 of 2 contracts at 50pts profit" |
| X5 | Spike profit exit: if unrealized >= 100pts within 9 bars of entry, exit entire position | trading-system.md | "spike_profit_pts=100.0, spike_profit_bars=9" (original design; was temporarily set to 50) |
| X6 | Hard stop at session end (17:00 ET for day, 10:30 for first-hour-only) | trading-philosophy.md | "Hard stop at 10:30 AM ET — always exit by session end" |
| X7 | Trailing stop v4: activates at 50pts profit, angles 50/60/70°, locked anchor | trading-system.md (session log 2026-04-22) | "Added trailing stop v4: threshold=50pts, angles=50/60/70, locked anchor" |
| X8 | Exit on CLOSE across trailing line, not on wick | trading-system.md | "trailing line should adjust angle when wicks push it but only exit on a CLOSE above/below" |
| X9 | "Take the gift" — if single bar moves 200+ points in favor, exit at close of that bar | trading-system.md | "Spike profit take — if a single bar moves 200+ points in your favor, exit at the close of that bar. Captures 'gift' moves like 02/20 spike." |

---

## 3. REVERSAL RULES

| # | Rule | Source | Evidence |
|---|------|--------|----------|
| R1 | When line is crossed in opposite direction, reverse position (close current + open opposite) | trading-philosophy.md | Mike Aston Reversal Rules #1 |
| R2 | No minimum hold time before reversing (min_reversal_minutes=0) | trading-system.md (session log 2026-04-22) | "Removed 10-min reversal hold: +88 pts/day gain (263 vs 142 avg/day)" |
| R3 | Fast reversal on strong moves: reverse immediately when price moves 80-100+ points against AND line is crossed | trading-system.md | "user reverses within 10 minutes when price moves 80-100+ points against position AND a line is crossed" |
| R4 | Steep line cross (>70°) triggers reversal or exit | trading-system.md | "steep_angle_threshold=70.0 — proven optimal over 535 days" |
| R5 | Suppress steep line reversal if close is within proximity_points of original shallow ray | trading-system.md | "proximity_points=15.0 — suppress steep ray cross if within 15pts of shallow ray" |
| R6 | Don't reverse against strong trend just because minor line was crossed | trading-philosophy.md (Druckenmiller) | "Follow the trend, protect capital otherwise. Don't reverse against a strong trend just because a minor line was crossed." |

---

## 4. CONDITIONS TO AVOID TRADES

| # | Rule | Source | Evidence |
|---|------|--------|----------|
| A1 | Don't fight the morning trend | trading-philosophy.md (PTJ) | "80% of performance is determined by the underlying trend. If the first 8 minutes show a clear downtrend, don't fight it with a long." |
| A2 | Don't chase the open | trading-philosophy.md | "Wait for the setup to develop. Don't chase the open." |
| A3 | Suppress reversal if water mark cluster supports current position | trading-system.md | "wm_shield_distance=12.0 — suppress reversal if water mark cluster within 12pts" |
| A4 | Skip trades on choppy/ranging days with shallow lines (<30°) | sim_trade_analysis.csv (02/13/26) | "Lines shallow — no strong trend. Low conviction day for both user and algo." |
| A5 | Don't enter if algo fires at 9:38-9:40 in wrong direction on trending days | trading-system.md | "The algo sometimes fires at 9:38-9:40 in the wrong direction on trending days" |

---

## 5. TREND FILTERS

| # | Rule | Source | Evidence |
|---|------|--------|----------|
| T1 | Identify trend in first 8 minutes | trading-philosophy.md (PTJ) | "80% of performance is determined by the underlying trend" |
| T2 | Read market structure (higher highs/higher lows) to decide whether to hold through pullbacks | trading-system.md | "User reads market structure (higher highs/higher lows) to decide whether to hold through pullbacks — not just line crosses" |
| T3 | On strong trend days: hold entire session with minimal reversals | trading-system.md | "On strong trend days, user holds the entire session with minimal reversals" |
| T4 | On choppy days: may reverse 2-3 times but keep losses small | trading-system.md | "On choppy days, user may reverse 2-3 times but keeps losses small" |
| T5 | Steep lines (>60-70°) indicate strong trend, high conviction | sim_trade_analysis.csv | Multiple days show steep purple/cyan = strong trend = hold |
| T6 | Shallow lines (<30°) indicate low conviction, choppy ranging day | sim_trade_analysis.csv (02/13/26) | "Lines shallow — no strong trend" |

---

## 6. CHOP FILTERS

| # | Rule | Source | Evidence |
|---|------|--------|----------|
| C1 | Shallow lines (<30°) = low conviction, expect whipsaws | sim_trade_analysis.csv (02/13/26) | "Shallow ~30° / ~25° — Choppy ranging day. Multiple small reversals." |
| C2 | Converging wedge (purple descending + cyan ascending) = squeeze, wait for breakout | sim_trade_analysis.csv (02/17/26) | "Converging wedge — purple descending and cyan ascending squeezing price" |
| C3 | Multiple false crosses on choppy price action = reduce size or stay flat | sim_trade_analysis.csv (02/10/26) | "Got whipsawed on first trade. Purple lines descending but price kept bouncing." |
| C4 | [INFERENCE] Afternoon session (after 13:00) tends toward chop — system gives back morning gains | forensic P/L trace May 14 | From +446 to -34 in afternoon whipsaw trades |

---

## 7. LINE BEHAVIOR RULES

| # | Rule | Source | Evidence |
|---|------|--------|----------|
| L1 | Orange ray: descends from session high at shallow angle (~2.5°). Primary resistance. | trading-philosophy.md | Mike Aston "The Lines" section |
| L2 | Purple ray: descends from session high through subsequent lower highs. Steeper resistance. | trading-philosophy.md | Mike Aston "The Lines" section |
| L3 | Blue/cyan ray: ascends from session low through subsequent higher lows. Steeper support. | trading-philosophy.md | Mike Aston "The Lines" section |
| L4 | Yellow ray: ascends from session low at shallow angle (~2.5°). Primary support. | trading-philosophy.md | Mike Aston "The Lines" section |
| L5 | User draws NEW STEEPER LINES mid-session as price moves away from original lines | trading-system.md | "user draws progressively steeper lines (~60°) from more recent anchor points" |
| L6 | Cyan redrawn from swing lows — steeper than algo blue ray | sim_trade_analysis.csv (02/03/26) | "Cyan redrawn from 10:00 low — steeper than algo blue ray" |
| L7 | Purple redrawn progressively steeper as price descends | sim_trade_analysis.csv (02/04/26, 02/11/26) | "Two progressively steeper purple lines drawn" |
| L8 | Low/high water marks: horizontal S/R at price cluster levels (±10 pts) where multiple bar lows/highs congregated | trading-philosophy.md | "NOT the absolute session high/low. These are mid-session pivot levels where price has repeatedly bounced." |
| L9 | Close below water mark cluster = stronger sell. Close above = stronger buy. | trading-philosophy.md | Explicit statement in Mike Aston section |
| L10 | Steep lines spawn when price moves 50+ pts away from primary line | trading-system.md | "steep_line_threshold: float = 50.0 — pts above/below primary line to spawn steeper line" |
| L11 | Re-anchor blue/purple from next swing point when invalidated (price pierces ray) | trading-system.md | "reanchor_blue_purple: bool = True — re-anchor blue/purple from next swing point when invalidated mid-session" |

---

## 8. CONTEXT RULES

| # | Rule | Source | Evidence |
|---|------|--------|----------|
| CT1 | Trade the first hour (9:30-10:30) — highest volume, cleanest moves | trading-philosophy.md | "The 9:30-10:30 window captures the highest volume and cleanest moves. After 10:30 the edge diminishes." |
| CT2 | After 10:30 the edge diminishes | trading-philosophy.md | Same source as CT1 |
| CT3 | 5:1 reward-to-risk ratio — only take trades where potential move is 5x the risk | trading-philosophy.md (PTJ) | "Only take trades where the potential move is at least 5x the risk" |
| CT4 | Size up when setup is clear (strong trend, clean line cross, confirmed direction) | trading-philosophy.md (Druckenmiller) | "When the setup is clear, size up. When uncertain, stay flat or small." |
| CT5 | When right, be very right — hold the position on confirmed trend | trading-philosophy.md (Soros) | "When you're right, be very right. When the trend is clear and the line cross is confirmed, hold the position." |
| CT6 | Admit mistakes quickly — if immediately wrong and line confirms it, reverse | trading-philosophy.md (Soros) | "If the trade goes against you immediately and a line is crossed in the opposite direction, reverse. Don't hope." |

---

## 9. "USER SKIPS THIS TRADE WHEN..." PATTERNS

| # | Pattern | Source | Evidence |
|---|---------|--------|----------|
| S1 | User skips early entries (9:38-9:40) on trending days — waits for confirmation | trading-system.md + sim_trade_analysis.csv | "Patient first entry — user waits for a clear setup to develop" |
| S2 | User doesn't reverse on bounces during strong trends — holds through using steeper trailing lines | sim_trade_analysis.csv (02/11/26) | "Algo should catch short but may have reversed on bounces — user held through them using steeper trailing purple lines" |
| S3 | User doesn't take long on strong downtrend days (02/04/26) | sim_trade_analysis.csv | "No long attempted. Patient — waited for trend then held short all session." |
| S4 | User skips trades when lines are shallow (<30°) — low conviction | sim_trade_analysis.csv (02/13/26) | "Lines shallow — no strong trend. Low conviction day." |
| S5 | User exits at session end even if profitable — respects hard stop | trading-philosophy.md | "Respect the hard stop. 10:30 is the hard stop. No exceptions." |
| S6 | [INFERENCE] User likely reduces activity in afternoon when morning trend exhausts | forensic P/L trace May 14 | Morning: +446 pts. Afternoon: gave back 480 pts in whipsaw. User would have stopped or reduced. |

---

## 10. RECURRING OBSERVATIONS FROM SCREENSHOT SESSIONS

| # | Observation | Days Observed | Evidence |
|---|-------------|---------------|----------|
| O1 | User draws progressively steeper purple lines on downtrend days | 02/04, 02/11 | "Two progressively steeper purple lines drawn" |
| O2 | User redraws cyan from new swing lows (steeper than original) | 02/03, 02/17 | "Cyan redrawn from 10:00 low — steeper than algo blue ray" |
| O3 | User holds single trade entire session on strong trend days | 02/04, 02/05, 02/11, 02/18 | All show 1 trade held to session end |
| O4 | User enters at convergence of two lines (cyan+yellow, purple+orange) | 02/03, 02/18 | "Double support entry at cyan+yellow convergence" |
| O5 | Algo's biggest losses come from wrong-direction first entry | 02/04, 02/11 | "Algo went wrong direction at 9:38/9:40" |
| O6 | Algo's biggest gap vs user is on strong trend days where user holds 1 trade | 02/23 (+549 sim vs +380 algo) | "Algo whipsawed 7 times, user held 1 trade with trailing stop" |
| O7 | Algo blue ray is consistently shallower than user's cyan | 02/03, 02/17 | "Algo blue ray anchored from earlier session low — shallower slope" |
| O8 | Spike exits ("take the gift") are rare but hugely profitable when caught | 02/20 | "+312 sim vs +24 algo — CRUSHER: Algo missed spike exit" |

---

## 11. UNCERTAINTY AREAS

| # | Area | Status | Evidence |
|---|------|--------|----------|
| U1 | Confirmation bar — should algo wait 1 bar after cross? | Untested | "user appears to enter one bar after the first cross" — listed as pending test |
| U2 | Water mark shield — optimal distance unclear | Tested at 12, currently 0 | "wm_shield_distance=0 gained +96 pts/day — shield was blocking good reversals" (commit 0b05133) |
| U3 | Afternoon session value — does trading after 13:00 add or subtract? | Data shows negative | May 14 forensic: +446 at 12:54, -34 at 16:16. Backtest: 14:00 peak, 17:00 negative. |
| U4 | Optimal steep line angle threshold | Tested 65-90 | Best commit used 90 (allow all), current live uses 65 |
| U5 | Whether user reads news/context before trading | Unknown | No evidence in repo |
| U6 | How user identifies "choppy day" in real-time (before losses) | Partially known | Shallow lines (<30°) are the indicator, but detection timing unclear |
| U7 | Exact re-anchoring logic for user's cyan/purple lines | Partially implemented | "reanchor_blue_purple=True" exists but algo's version is shallower than user's |
| U8 | Whether user uses different rules for afternoon vs morning | [INFERENCE] Likely yes | User's sim data is 9:30-10:30 only. No afternoon sim data exists. |
| U9 | Spike profit threshold — 50 vs 100 vs 200 | Conflicting | Steering doc says "200+ points", code had 50 and 100 at various times |
| U10 | Whether TP should suppress same-bar reversal | Tested — suppression is WORSE | Suppressing reversal on TP bar: -25.9 pts/day. Allowing it: +7.8 pts/day. |

---

## APPENDIX: Day-by-Day Sim vs Algo Comparison

Source: `SIM/validation_results.csv` + `SIM/sim_trade_analysis.csv`

| Date | Sim Pts | Algo Pts | Gap | Key Observation |
|---|---|---|---|---|
| 02/03/26 | +275 | -18 | -293 | Algo blue ray too shallow, missed 10:05 entry |
| 02/04/26 | +212 | -65 | -277 | Algo went long first, user stayed short all session |
| 02/05/26 | +129 | -12 | -141 | Algo entry slightly late on strong uptrend |
| 02/09/26 | +116 | +316 | +200 | Algo BETTER — held long to session end |
| 02/10/26 | -61 | +75 | +136 | Algo BETTER on choppy day |
| 02/11/26 | +226 | +237 | +11 | Both caught downtrend |
| 02/13/26 | +16 | +14 | -2 | Both struggled on choppy day |
| 02/17/26 | -6 | +20 | +26 | Algo slightly better |
| 02/18/26 | +155 | +56 | -99 | Algo entry late, exit worse |

**Algo wins**: 02/09, 02/10, 02/11, 02/13, 02/17 (5 days)
**User wins**: 02/03, 02/04, 02/05, 02/18 (4 days)
**Biggest user advantage**: Strong trend days where user holds 1 trade (02/03, 02/04)
**Biggest algo advantage**: Days where algo correctly identifies trend and holds (02/09)

---

## APPENDIX: Parameter Evolution

| Date | Change | Result | Commit |
|---|---|---|---|
| 2026-04-20 | Consolidated to TradingAlgoFast.py | +87.8 pts/day at 10:30 | b1a2c0e |
| 2026-04-22 | Removed 10-min reversal hold | +88 pts/day gain | 4aa938e |
| 2026-04-22 | Added trailing stop v4 (50/60/70°) | 266.2 pts/day, 78.7% win | dd8f8ad |
| 2026-04-27 | Param sweep: warmup=7, steep=90, prox=4, entry=0, wm=0 | 348.5 pts/day, 82.3% win | 0b05133 |
| 2026-04-28 | Fix angle bug + clean P/L | 301.4 pts/day, 78.8% win | c995ad3 |
| 2026-05-15 | Fixed P/L calculation bug (was double-counting winners) | -3.8 pts/day (correct math) | forensic audit |
| 2026-05-16 | Wired warmup_minutes to cutoff, set to 8 | +6.3 pts/day | 36d33c9 |
| 2026-05-16 | Adopted best-commit config (warmup=7, steep=90, prox=4) | +7.8 pts/day | b42e5c5 |

**NOTE**: All results before 2026-05-15 used buggy P/L calculation and are inflated.


---

## 12. SESSION ANALYSIS: 04/21/2026 (9:30-11:00)

**User P/L**: +201 pts ($1,005) | **Fred P/L**: +284 pts
**User trades**: 9 | **Fred trades**: 5 signals + 4 TP/LIQ

### New Rules Confirmed

| # | Rule | Evidence from 04/21 |
|---|------|---------------------|
| N1 | User takes TP at exactly +50 pts (limit order), THEN spike exit is separate | User: SELL 1 @ 49960 (TP), then SELL 1 @ 50013 (spike). Two separate exits. |
| N2 | Spike exit threshold is 100 pts, not 50 | User: "LIQ because of 100 point spike" — entry 49910, exit 50013 = +103 pts |
| N3 | User reverses on STEEPER purple/blue lines mid-session, not just original lines | Trade 4: "BUY 2 @ 50039 (price closed above steeper purple)" |
| N4 | User gets chopped in sideways volatile markets — this is accepted as part of system | "i was chopped around quite a bit mid morning with the volatile sideways swings. this is all part of the system." |
| N5 | The system's edge comes from capturing legitimate runs, not avoiding chop | "once moves do happen...this is where we make our money" |
| N6 | There is a tension between steep line sensitivity and chop | "a fine line between having lines too steep and getting chopped with every little swing versus being aggressive enough to ensure we do capture the legitimate runs" |
| N7 | User uses limit orders for TP (left in market), which can fill unexpectedly | Trade 11: "accidental buy from a limit order that was left in to TP at 50 points" |
| N8 | After getting chopped, user rides the eventual trend move for remainder of session | "I then rode the remaining short position for the remainder of the morning" |

### Gaps Identified

| # | Gap | Detail |
|---|-----|--------|
| G1 | Fred's spike_profit_pts=50 causes same-bar TP+LIQ (exits everything at +50) | Should be 100 to match user's system |
| G2 | Fred doesn't see the steeper mid-session purple/blue lines that user draws | User reversed at 50008 (below blue) around 10:05 — Fred didn't see this line |
| G3 | Fred's lines in 10:00-10:25 window don't match user's steeper redrawn lines | User made 5 trades in this window, Fred made 0 |
| G4 | Fred eventually catches the downtrend but later than user | Fred SELL at 10:26 vs user's final SELL at 49933 earlier |

### Configuration Correction Needed
- `spike_profit_pts` should be **100**, not 50 (user explicitly stated "100 point spike")
- This eliminates the TP+LIQ same-bar issue (TP fires at +50, spike only at +100)
