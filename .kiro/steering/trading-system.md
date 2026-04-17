# YM Futures Trading System — Project Context

## Goal
Build a bot ("Fred") that trades YM E-mini Dow Jones futures exactly the way the user trades in their sim account. The user averages 300+ points/week in their live account and significantly more in sim. The bot should match or exceed sim performance.

## Current Proven Settings (AlgoConfig)
```python
AlgoConfig(
    warmup_minutes=12,          # first signal fires on 9:42 close (proven optimal over 535 days)
    steep_angle_threshold=70.0, # proven optimal over 535 days
    proximity_points=15.0,      # suppress steep ray cross if within 15pts of shallow ray
    min_reversal_minutes=10,    # proven optimal over 535 days (+$123,810 on 2 contracts)
)
```

## Backtest Results (505 trading days excl April 2025, 9:30-10:30 ET, 2 contracts)
- Baseline (no filters): -$495,500
- 10-min reversal filter: +$115,960
- With trailing stop v3: **+$116,490** ← current best
  - Worst day: -208 (vs -438 without trailing stop)
  - Avg losing day: -50 pts (vs -70 without)
- Angle threshold sweep: 70° is optimal
- Loss protection overrides (50/65/80 pts): all worse than plain 10-min hold

## Line/Ray Mapping (User's System → Algo)
| User's Chart | Algo Ray | Behavior |
|---|---|---|
| Upper yellow (descending) | Orange ray | Anchors at session high, -2.5° fixed angle |
| Purple (descending) | Purple ray | Anchors at rolling session high, trendline slope |
| Cyan/teal (ascending) | Blue ray | Anchors at rolling session low, trendline slope |
| Lower yellow (ascending) | Yellow ray | Anchors at session low, +2.5° fixed angle |

## Key Patterns Observed from Sim Trade Analysis

### What the user does that the algo doesn't yet:
1. **Steeper mid-session trailing lines** — as price moves away from original blue/purple lines, user draws progressively steeper lines (~60°) from more recent anchor points. These act as trailing stops. If price closes across the line → exit. If price keeps moving away → tighten the line further.

2. **Fast reversal on strong moves** — user reverses within 10 minutes when price moves 80-100+ points against position AND a line is crossed. The 10-min rule blocks this. This is the biggest gap.

3. **Patient first entry** — user waits for a clear setup to develop before the first trade. The algo sometimes fires at 9:38-9:40 in the wrong direction on trending days.

4. **Confirmation bar** — user appears to enter one bar after the first cross (not on the first cross itself).

### Days analyzed (sim vs algo):
| Date | Sim P/L | Algo P/L | Key Issue |
|---|---|---|---|
| 02/03/26 | +275 pts | similar | 9:44 sell missed (67° blue line, now passes 70° threshold) |
| 02/04/26 | +275 pts | -350 pts | Algo went wrong direction at 9:38, 10-min rule held bad short |
| 02/05/26 | +353 pts | +224 pts | Algo entry 7 min late, reversal 8 min late |
| 02/09/26 | +171 pts | +268 pts | Algo actually better — held long to session end |
| 02/10/26 | +130 pts | -160 pts | Algo reversed at wrong price (10-min rule delayed by 4 min) |
| 02/11/26 | +362 pts | +207 pts | Algo went wrong direction at 9:40 |
| 02/13/26 | -48 pts | +137 pts | Algo better — correctly identified downtrend |
| 02/17/26 | -48 pts | +137 pts | Algo better — correctly identified downtrend |
| 02/18/26 | +157 pts | +56 pts | Algo entry late, exit worse |
| 02/20/26 | +312 pts | +24 pts | CRUSHER: Algo missed spike exit — needs "take the gift" rule |
| 02/23/26 | +549 pts | +380 pts | CRUSHER: Algo whipsawed 7 times, user held 1 trade with trailing stop |

## Pending Tests / Work Items

### Currently running:
- Warmup sweep: 8, 10, 12, 15 minutes — does longer warmup reduce wrong-direction first entries?

### To implement / test next:
1. **Trailing stop line (v4)** — current v3 activates at 75pts, needs tuning. Key insight from 02/23: the trailing line should adjust angle when wicks push it but only exit on a CLOSE above/below. Avoid unnecessary reversals on strong trend days.
2. **Spike profit take** — if a single bar moves 200+ points in your favor, exit at the close of that bar. Captures "gift" moves like 02/20 spike. Rare but hugely profitable.
3. **Low/high water marks** — horizontal lines at price cluster levels where multiple bar lows or highs have congregated (Mike Aston's concept).
4. **Hourly session optimization** — test which hours of the day are most profitable. Full day data downloaded.
5. **Confirmation bar** — require 2 consecutive closes beyond a ray before triggering.

### Sim screenshots analyzed:
All February 2026 days complete. User to capture more examples.

## Architecture
- `InteractiveBrokers.py` — live IB bridge, real-time bars via reqRealTimeBars
- `TradingAlgo.py` — core signal engine (AlgoConfig, RayManager, run_trading_algo)
- `plotFigure.py` — chart rendering (pure visualization, no calculations)
- `ReOrgMain.py` — orchestration for live and historical sessions
- `RunHistoricalData.py` — pull IB historical data + run algo + interactive chart
- `Backtest2Year.py` — 2-year backtest with variant comparison
- `AnalyseTrades.py` — crossback theory tester
- `compare_day.py` — single-day sim vs algo comparison

## Data
- Historical CSVs: `~/Desktop/2YearsData/930_1000/CBOT_MINI_YM1_YYYY-MM-DD.csv`
- Live session data: `~/Desktop/IB_Live/tracking/` and `~/Desktop/IB_Live/charts/`
- Sim screenshots: `SIM/` folder in workspace

## IB Connection
- Paper: port 4002
- Live: port 4001 (needed for historical data beyond a few days)
- Contract: YMH6 (March 2026), rolls to YMM6 (June 2026) around March 2026
