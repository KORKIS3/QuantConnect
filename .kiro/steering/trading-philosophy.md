---
inclusion: auto
description: "Trading philosophy from elite traders: risk management, conviction sizing, systematic thinking, trend following"
---

# Trading Philosophy — Principles from Elite Traders

This document captures key principles from the world's best traders and how they apply
to Fred's trading system. These are not rules to code directly, but mental frameworks
to guide decisions about the algo's behavior.

---

## Paul Tudor Jones — Risk First, Trend Second

Key principles applicable to Fred:
- **Protect capital above all else.** Every session has a hard stop. No single bad day
  should wipe out a week of gains. The 10-minute reversal filter exists for this reason.
- **5:1 reward-to-risk ratio.** Only take trades where the potential move is at least
  5x the risk. On a 60-minute session, a 300-point move is possible — don't risk 100
  to make 20.
- **80% of performance is determined by the underlying trend.** If the first 8 minutes
  show a clear downtrend, don't fight it with a long. Wait for confirmation.
- **Cut losers fast, let winners run.** The trailing stop line concept (60° angle,
  tightening as trade moves in favor) directly implements this.

---

## Stanley Druckenmiller — Conviction and Sizing

Key principles applicable to Fred:
- **Sizing is 70-80% of the equation.** When the setup is clear (e.g. strong trend,
  clean line cross, confirmed direction), size up. When uncertain, stay flat or small.
- **Concentrate when conviction is high.** The user's system already does this —
  2 contracts on clear setups, 1 on uncertain ones.
- **Never invest in the present — invest in where price will be.** The trendline system
  is forward-looking: the line projects where support/resistance will be, not where it is.
- **Follow the trend, protect capital otherwise.** Don't reverse against a strong trend
  just because a minor line was crossed.

---

## Ray Dalio — Radical Transparency and Systematic Thinking

Key principles applicable to Fred:
- **Build systems that don't require prediction.** The line-crossing system is rules-based
  — it doesn't predict direction, it reacts to price crossing defined levels.
- **Accept you don't know the future.** Every trade is a probability, not a certainty.
  The 54% win rate over 535 days is the edge — trust the system over individual trades.
- **Stress-test everything.** The 2-year backtest is Dalio's approach applied to intraday
  trading. Keep testing variants before committing to changes.
- **Pain + reflection = progress.** When the algo loses on a day, analyze why. The sim
  comparison process is exactly this.

---

## Mark Douglas — Trading in the Zone (Psychology)

Key principles applicable to Fred (and the user):
- **Think in probabilities, not certainties.** No single trade matters. The edge plays
  out over hundreds of trades. A losing day doesn't mean the system is broken.
- **Every trade is unique.** Don't let yesterday's loss make you hesitate today.
  The algo has no memory of past trades — this is actually an advantage.
- **The market can do anything.** The 10-minute rule exists because even a "perfect"
  setup can reverse immediately. Accept that and size accordingly.
- **Consistency comes from trusting the system.** The user's gap between sim and live
  is partly psychological — the bot removes that gap by executing without hesitation.
- **Define your risk before entering.** The trailing stop line is the pre-defined exit.
  Know it before you enter.

---

## George Soros — Reflexivity and Feedback Loops

Key principles applicable to Fred:
- **Markets are driven by participant behavior, not fundamentals alone.** Price action
  creates its own momentum — when a trendline breaks, other traders see it too and
  accelerate the move. This is why line crosses work.
- **When you're right, be very right.** When the trend is clear and the line cross is
  confirmed, hold the position. Don't exit early out of fear.
- **Admit mistakes quickly.** If the trade goes against you immediately and a line is
  crossed in the opposite direction, reverse. Don't hope.

---

## Mike Aston / The Trading Template — Core System (thetradingtemplate.com)

This is the actual system Fred is being built to emulate. Principles learned directly
from sim trade analysis sessions with the user (Kevin Orkis, student of Mike Aston).

### The Lines (Rays)
- **Orange ray** (upper yellow on user's chart): Descends from session high at shallow angle (~2.5°). Primary resistance.
- **Purple ray**: Descends from session high through subsequent lower highs. Steeper resistance. Key entry trigger for longs when price closes above it.
- **Blue/cyan ray**: Ascends from session low through subsequent higher lows. Steeper support. Key entry trigger for shorts when price closes below it.
- **Yellow ray** (lower yellow): Ascends from session low at shallow angle (~2.5°). Primary support.

### Entry Rules
1. Wait for the first 8 bars (warmup) to establish the trend and draw lines.
2. Enter on a **close** across a line — never on an intrabar wick or high/low.
3. The first trade of the day should be in the direction of the established trend.
4. A close above the purple ray = BUY signal (upward breakout of resistance).
5. A close below the blue ray = SELL signal (downward break of support).
6. A close above the orange ray = BUY (stronger signal, shallower line).
7. A close below the yellow ray = SELL (stronger signal, shallower line).

### Exit / Trailing Stop Rules
1. As price moves in your favor, draw a **steeper line (~60°)** from the most recent swing low (for longs) or swing high (for shorts).
2. If price closes across that steeper line → exit the trade.
3. If price continues moving away from the line → tighten it further (draw an even steeper line from the next swing point).
4. This creates a progressive trailing stop that locks in profits while giving the trade room to breathe.
5. Hard stop at 10:30 AM ET — always exit by session end.

### Reversal Rules
1. When a line is crossed in the opposite direction, reverse the position (close current + open opposite).
2. Give the trade at least 10 minutes before reversing (avoid whipsaws).
3. Exception: if price moves 80-100+ points against you AND a line is crossed, reverse immediately regardless of time held.

### Key Observations from Sim Analysis
- User consistently enters **one bar after** the first cross (confirmation bar).
- User draws **new steeper lines mid-session** as price moves away from original lines.
- User is patient — waits for the setup to develop, doesn't chase the open.
- User exits near 10:30 when a steeper trailing line is crossed, even if the original lines haven't been crossed.
- On strong trend days, user holds the entire session with minimal reversals.
- On choppy days, user may reverse 2-3 times but keeps losses small.
- User reads **market structure** (higher highs/higher lows) to decide whether to hold through pullbacks — not just line crosses.
- **Low/high water marks** — horizontal support/resistance at **price cluster levels** where multiple bar lows or highs have congregated (within ±10 points of each other). NOT the absolute session high/low (those are already covered by orange/yellow rays). These are mid-session pivot levels where price has repeatedly bounced. Example: on 02/13/26, ~49,350 was touched by multiple pullback lows and acted as a floor. A close below such a cluster = stronger sell. A close above = stronger buy. To be tested as additional signal triggers.



Key principles applicable to Fred (most directly applicable to YM day trading):
- **Trade the first hour.** The 9:30-10:30 window captures the highest volume and
  cleanest moves. After 10:30 the edge diminishes. This is already implemented.
- **Wait for the setup to develop.** Don't chase the open. The 8-12 minute warmup
  lets the first trend establish before entering. Cameron calls this "waiting for
  the first pullback."
- **The best trades are obvious.** If you have to talk yourself into a trade, it's
  probably not a good one. The algo should only fire on clear, unambiguous line crosses.
- **Respect the hard stop.** 10:30 is the hard stop. No exceptions.

---

## Synthesis — What This Means for Fred

The common thread across all these traders:

1. **Trend identification first** — don't fight the morning trend
2. **Patient entry** — wait for confirmation, not the first signal
3. **Defined exit** — know where you're wrong before you enter (trailing stop line)
4. **Let winners run** — don't exit a good trade early just because a minor line twitched
5. **Cut losers fast** — if the trade is immediately wrong and a line confirms it, reverse
6. **Trust the system** — 54% win rate over 535 days is a real edge; don't override it

The biggest gap between Fred and the user's sim performance is items 3 and 5 —
the trailing stop line and the fast reversal on strong moves. These are the next
two things to implement.
