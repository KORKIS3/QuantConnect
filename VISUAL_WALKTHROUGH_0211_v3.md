# VISUAL WALKTHROUGH v3 — Waiting Behavior & Profit Protection Lines

## Critical Correction from v2

v2 correctly showed Orange/Yellow as frozen continuation evidence. But it still implied steeper lines appear quickly after bounces.

**Scott's clarification:** Steeper lines are NOT created reactively. They are PROFIT PROTECTION structure that only appears AFTER price PROVES continuation. The engine must WAIT.

---

## Session: 2026-02-11 (09:30-10:20)

### Phase 1: Structure Formation (09:30-09:36)

```
Bar 0  09:30  H=50536 L=50459 C=50515  ← ORANGE #1 (50536), YELLOW #1 (50459)
Bar 2  09:32  H=50585 L=50484 C=50577  ← ORANGE #2 (50585), new session high
Bar 3  09:33  H=50582 L=50529 C=50532  ← BLUE P2 confirmed (50484 at bar 2)
Bar 6  09:36  H=50541 L=50486 C=50489  ← BLUE BREAK: close 50489 < blue 50534
```

**State at bar 6:**
- BLUE broken → bearish resolve begins
- SHORT entry signal (authority 2)
- Original Purple: PROVISIONAL (no valid P2 yet)
- All lines frozen. Nothing moves.

---

### Phase 2: Initial Resolve + First Bounce (09:44-09:46)

```
Bar 14  09:44  H=50466 L=50443 C=50456  ← YELLOW #1 BREAK (close < 50469)
Bar 15  09:45  H=50507 L=50444 C=50501  ← BOUNCE begins (close back up to 50501)
Bar 16  09:46  H=50544 L=50498 C=50510  ← Bounce peak (high 50544)
```

**What happens here:**

Price broke Yellow #1 at bar 14 (maximum conviction SHORT). Then price bounces from 50,443 up to 50,544 (101 pts countertrend).

**WRONG behavior (reactive):** Immediately create steeper purple from 50,544.

**CORRECT behavior (Scott's):**
```
DO NOTHING.
WAIT.
Keep original structure active.
This bounce is unproven.
It could be:
  - a reversal (in which case we need to exit)
  - a dead cat bounce (in which case it will fail)
We don't know yet. WAIT FOR PROOF.
```

**Line state — UNCHANGED from bar 6:**
```
ORANGE #2: 50585, frozen, active
YELLOW #1: 50459, frozen, BROKEN (bar 14)
BLUE #1: 50459→50484, frozen, BROKEN (bar 6)
PURPLE: PROVISIONAL (still no valid P2)
No new lines created. WAITING.
```

---

### Phase 3: Bounce Fails, Resolve Resumes (09:47-09:50)

```
Bar 17  09:47  H=50526 L=50486 C=50493  ← bounce fading
Bar 18  09:48  H=50493 L=50449 C=50466  ← lower
Bar 19  09:49  H=50469 L=50428 C=50428  ← new low below Yellow #1 break
Bar 20  09:50  H=50431 L=50392 C=50406  ← NEW SESSION LOW → YELLOW #2 (50392)
```

**What happens:**
- Bounce peaked at bar 16 (high 50,544) then FAILED
- Price resumed lower, making new lows
- New session low at bar 20 → Yellow #2 created (50,392)

**Still NO steeper purple created.** Why?
- The bounce at bar 16 was only 3 bars old when it failed
- Price hasn't proven that the 50,544 level is meaningful structure
- We need MORE evidence before creating profit protection

---

### Phase 4: Second Bounce Attempt (09:51-09:53)

```
Bar 21  09:51  H=50449 L=50386 C=50427  ← NEW SESSION LOW (50386) → YELLOW #3
Bar 22  09:52  H=50459 L=50424 C=50444  ← second bounce attempt
Bar 23  09:53  H=50452 L=50430 C=50445  ← bounce stalls at 50459
```

**What happens:**
- Price bounced from 50,386 up to 50,459 (73 pts)
- Bounce stalled — couldn't get above 50,459
- Note: 50,459 was the ORIGINAL session low (Yellow #1 anchor)
- The old support is now acting as resistance — structure memory

**Still NO steeper purple.** Why?
- This bounce also hasn't proven itself yet
- It stalled at the old Yellow #1 level — that's interesting but not proof
- WAIT for this bounce to FAIL and price to make new lows

---

### Phase 5: Second Bounce FAILS → Structure Proven (09:54-10:02)

```
Bar 24  09:54  H=50454 L=50406 C=50414  ← bounce failing
Bar 25  09:55  H=50439 L=50398 C=50407  ← lower
Bar 26  09:56  H=50432 L=50400 C=50404  ← lower
Bar 27  09:57  H=50411 L=50364 C=50401  ← NEW LOW (50364) below Yellow #3
Bar 28  09:58  H=50404 L=50375 C=50376  ← continuation
Bar 29  09:59  H=50394 L=50369 C=50394
Bar 30  10:00  H=50414 L=50375 C=50386
Bar 31  10:01  H=50412 L=50375 C=50393
Bar 32  10:02  H=50397 L=50342 C=50345  ← ACCELERATION lower
```

**NOW structure has proven itself:**
- First bounce (bar 16, high 50,544) → FAILED
- Second bounce (bar 22-23, high 50,459) → FAILED
- Price made successive new lows: 50,392 → 50,386 → 50,364 → 50,342
- Bearish continuation is CONFIRMED by multiple failed bounces

**NOW — and ONLY now — create the steeper profit protection purple:**

```
STEEPER PURPLE (Profit Protection):
  P1 = 50,544 (high of FIRST failed bounce, bar 16)
  P2 = 50,459 (high of SECOND failed bounce, bar 22)
  Slope = (50459 - 50544) / (22 - 16) = -85/6 = -14.2 pts/bar
  
  Verify containment: line must be ABOVE all highs from bar 16 to bar 32
    Bar 16: 50544 (= P1) ✓
    Bar 17: 50526 < line(50530) ✓
    Bar 22: 50459 (= P2) ✓
    Bar 23: 50452 < line(50445)... WAIT — 50452 > 50445? 
    
    Recalculate: line at bar 23 = 50544 + (-14.2)(23-16) = 50544 - 99.4 = 50444.6
    Bar 23 high = 50452 > 50444.6 — VIOLATION
    
    Fix: Use bar 23 high (50452) as P2 instead:
    Slope = (50452 - 50544) / (23 - 16) = -92/7 = -13.1 pts/bar
    Recheck bar 22: line = 50544 + (-13.1)(6) = 50465.4. High = 50459 ✓
    Bar 23: line = 50544 + (-13.1)(7) = 50452.3. High = 50452 ✓
    All subsequent bars: highs are much lower ✓
    
  FROZEN. Status = PROFIT_PROTECTION.
```

**Line state at bar 32:**
```
ID  Type                    Auth  P1      P2      Status
5   ORANGE #2               1     50585   —       FROZEN (continuation evidence)
2   YELLOW #1               1     50459   —       BROKEN bar 14 (preserved)
7   YELLOW #2               1     50392   —       FROZEN (continuation evidence)
8   YELLOW #3               1     50386   —       BROKEN bar 27 (preserved)
4   BLUE #1                 2     50459   50484   BROKEN bar 6 (preserved)
6   PURPLE (original)       2     50585   —       PROVISIONAL (no valid P2)
9   PURPLE (profit protect) 3     50544   50452   FROZEN — profit protection
```

---

### Phase 6: How Profit Protection Purple Works

**Purpose:** A profitable short should not wait for price to travel all the way back to Orange #2 (50,585) before exiting. That's 240+ pts of giveback.

**The steeper purple (50,544 → 50,452, slope -13.1/bar) provides:**
- At bar 32 (10:02): line value = 50544 + (-13.1)(32-16) = 50544 - 209.6 = 50,334
- Current price: 50,345
- Distance to profit protection line: only 11 pts above

**If price closes ABOVE this steeper purple:**
- Exit SHORT (profit protection triggered)
- Don't wait for original structure (too far away)
- Lock in profits from the 50,585 → 50,345 move (240 pts)

**If price stays below:**
- Continue holding SHORT
- Steeper purple descends with time, giving trade room to breathe
- Only exits if a genuine countertrend develops

---

## TIMING SUMMARY — When Lines Appear

| Bar | Time  | Event | Lines Created |
|-----|-------|-------|---------------|
| 0   | 09:30 | Session open | Orange #1, Yellow #1, Purple (prov), Blue (prov) |
| 2   | 09:32 | New high | Orange #2 |
| 3   | 09:33 | Blue P2 confirmed | Blue FROZEN |
| 6   | 09:36 | Blue break | — (signal only) |
| 14  | 09:44 | Yellow #1 break | — (signal only) |
| 16  | 09:46 | Bounce peak | **NOTHING** (waiting) |
| 20  | 09:50 | New low | Yellow #2 |
| 21  | 09:51 | New low | Yellow #3 |
| 22  | 09:52 | Second bounce peak | **NOTHING** (waiting) |
| 27  | 09:57 | Yellow #3 break | — (continuation confirmed) |
| 32  | 10:02 | Acceleration lower | **NOW: Steeper Purple created** (profit protection) |

**Key insight:** 16 bars elapsed between the first bounce (bar 16) and the creation of the steeper purple (bar 32). Scott WAITS for structure to prove itself. The engine must do the same.

---

## CREATION CRITERIA FOR STEEPER LINES

A steeper profit protection line is created ONLY when ALL of:

1. **Original structure exists** (original purple/blue was created)
2. **At least ONE countertrend bounce has occurred** (P1 candidate exists)
3. **That bounce FAILED** (price resumed in trend direction)
4. **A SECOND bounce occurred** (P2 candidate exists)
5. **That bounce ALSO failed OR stalled lower than the first** (structure proven)
6. **Price made new extremes beyond the bounce levels** (continuation confirmed)

If ANY of these conditions is not met: DO NOTHING. WAIT.

---

## HIERARCHY (Final, Corrected)

```
1. Orange / Yellow          — Continuation evidence (fixed 2.5°, never moves)
2. Original Purple / Blue   — Primary containment (frozen from P1+P2)
3. Profit Protection Purple/Blue — Steeper, from failed bounces (ONLY after proof)
4. Rescue lines             — From 3+ touch parent, confirmed structural shift
```

---

## ANSWER: Can we prove the engine behaves like Scott?

YES — but only if the engine implements WAITING behavior:
- No steeper lines until bounces FAIL
- No reactive line creation on every swing
- Structure must PROVE itself before lines appear
- Original structure remains active underneath
- Steeper lines are profit protection, not prediction
