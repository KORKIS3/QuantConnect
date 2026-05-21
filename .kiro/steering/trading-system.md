---
inclusion: auto
description: "YM Futures Trading System project context: goals, config, architecture, session log, data paths"
---

# YM Futures Trading System — Project Context

## Goal
Build a bot ("Fred") that trades YM E-mini Dow Jones futures exactly the way the user trades in their sim account. The user averages 300+ points/week in their live account and significantly more in sim. The bot should match or exceed sim performance.

## Backtest Standard — ALWAYS USE THIS
- **All backtests must use ALL available days** (`~/Desktop/2YearsData/full_day/`, currently 667 days)
- **Full day session only: 9:30 ET start, 17:00 ET end**
- Never use quick mode (10:30 end) or partial day windows for final results
- Always report: Total Pts, Avg/Day, Win%, Win Days, Lose Days
- Always compare against the current baseline: **275.3 pts/day, 74.8% win days, 145 losing days (as of 2026-04-28, 671 days)**

## Current Proven Settings (AlgoConfig)
```python
AlgoConfig(
    warmup_minutes=12,          # first signal fires on 9:42 close
    steep_angle_threshold=70.0, # proven optimal over 535 days
    proximity_points=15.0,      # suppress steep ray cross if within 15pts of shallow ray
    min_reversal_minutes=0,     # CHANGED 2026-04-22: removing 10-min hold gained +88pts/day (230 vs 142)
    min_entry_angle=30.0,       # wait for purple or blue to reach 30° before first entry
    partial_tp_pts=50.0,        # close 1 of 2 contracts at 50pts profit
    wm_shield_distance=12.0,    # suppress reversal if water mark cluster within 12pts
)
```

## How to Run Fred
```
# Daily session (auto-starts via scheduled task at 9:28 AM Mon-Fri)
run_fred_daily.bat

# Manual dry run (no orders)
python run_fred.py --dry-run --duration 450

# Manual live (real orders)
python run_fred.py --duration 450

# TradeStation (once credentials set)
python run_fred.py --broker ts --dry-run --duration 450

# Backtest full day
python Backtest2Year.py --skip-download

# Backtest quick (9:30-10:30 only, ~35 seconds)
python Backtest2Year.py --skip-download --quick

# Download yesterday's data
python download_yesterday.py

# Interactive chart for a specific day
python _check_chart.py  (edit date inside)

# Analyze today's session
python _analyze_today.py
```

## Backtest Results (664 trading days, full day 9:30-17:00, 2 contracts, partial TP @50pts)
Run: 2026-04-20. Data: `~/Desktop/2YearsData/full_day/` (Jul 2023 – Apr 2026)

### Day Session (9:30 start)
| End Time | Trades | Win% | Total Pts | P/L USD | Avg/Day |
|---|---|---|---|---|---|
| 10:00 | 964 | 62.3% | 19,933 | $99,665 | +34.5 |
| 10:30 | 1,646 | 69.9% | 52,257 | $261,285 | +87.8 |
| 11:00 | 2,244 | 70.0% | 70,229 | $351,145 | +116.3 |
| 11:30 | 2,804 | 71.0% | 91,987 | $459,935 | +151.0 |
| 12:00 | 3,311 | 71.5% | 110,181 | $550,905 | +180.3 |
| 13:00 | 4,262 | 70.8% | 138,079 | $690,395 | +224.5 |
| 14:00 | 5,126 | 71.1% | 169,830 | $849,150 | +273.5 |
| 15:00 | 5,919 | 70.1% | 192,363 | $961,815 | +309.3 |
| 16:00 | 6,723 | 69.8% | 214,030 | $1,070,150 | +344.1 |
| 17:00 | 7,079 | 69.2% | 221,554 | $1,107,770 | +356.2 |

### Overnight Session (18:00 start) — weaker edge, ~42-47% win rate
- Best end time: 09:00 → +$235,680 (+38.5 pts/day avg)

### Previous results (505 days, 9:30-10:30 only)
- Baseline (no filters): -$495,500
- 10-min reversal filter: +$115,960
- With trailing stop v3: **+$116,490** ← was current best
- Angle threshold sweep: 70° is optimal

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

### To implement / test next:
1. **Trailing stop line (v4)** — current v3 activates at 75pts, needs tuning. Key insight from 02/23: the trailing line should adjust angle when wicks push it but only exit on a CLOSE above/below. Avoid unnecessary reversals on strong trend days.
2. **Spike profit take** — if a single bar moves 200+ points in your favor, exit at the close of that bar. Captures "gift" moves like 02/20 spike. Rare but hugely profitable.
3. **Low/high water marks** — horizontal lines at price cluster levels where multiple bar lows or highs have congregated (Mike Aston's concept).
4. **Confirmation bar** — require 2 consecutive closes beyond a ray before triggering.

### Sim screenshots analyzed:
All February 2026 days complete. User to capture more examples.

## Architecture (as of 2026-04-20 rework)
- `TradingAlgoFast.py` — **single engine** (AlgoConfig, all ray computation, signal detection, all Numba-compiled). TradingAlgo.py deleted.
- `InteractiveBrokers.py` — live IB bridge, real-time bars via reqRealTimeBars. Uses `run_trading_algo_fast`. Has `enable_chart=True/False` toggle.
- `plotFigure.py` — chart rendering (pure visualization, no calculations)
- `ReOrgMain.py` — orchestration for live and historical sessions
- `RunHistoricalData.py` — pull IB historical data + run algo + interactive chart (requires IB connection)
- `Backtest2Year.py` — full day backtest. Run with `--skip-download --quick` for fast 9:30-10:30 mode (35s), or `--skip-download` for full day+overnight (~4.5 min)
- `compare_day.py` — single-day sim vs algo comparison
- `verify_algo_match.py` — runs all 3 engines on every day, writes results to `verify_algo_match_results.csv`
- `_check_chart.py`, `_run_fast_test.py` — quick test/debug scripts

### Deleted in rework:
- `TradingAlgo.py` — replaced by TradingAlgoFast.py
- `RunAllDays.py`, `RunFullDataSet.py` — replaced by Backtest2Year.py
- All `debug_*.py` files

## Protected Files — NEVER DELETE
These files are essential infrastructure for Fred's interactive charting and data pipeline.
Even if they appear unused during cleanup, they MUST be kept:

- `plotFigure.py` — interactive chart renderer (ChartPlotter with nav buttons)
- `Plotter.py` — thin wrapper around plotFigure for convenience
- `data_extraction.py` — Yahoo Finance data retrieval for YM
- `run_chart.py` — quick interactive chart launcher (`python run_chart.py 2025-04-07 09:30 17:00`)
- `run_chart_fred_alive.py` — FRED Is Alive interactive chart (`python run_chart_fred_alive.py 2025-04-07`)
- `visualize_replay.py` — bar-by-bar frozen ray replay with slider

## Data
- Full day CSVs: `~/Desktop/2YearsData/full_day/CBOT_MINI_YM1_YYYY-MM-DD.csv` (664 days, Jul 2023–Apr 2026)
- 9:30-10:30 CSVs: `~/Desktop/2YearsData/930_1000/`
- 9:30-11:30 CSVs: `~/Desktop/2YearsData/930_1130/`
- Live session data: `~/Desktop/IB_Live/tracking/` and `~/Desktop/IB_Live/charts/`
- Sim screenshots: `SIM/` folder in workspace

## IB Connection
- Paper: port 4002
- Live: port 4001 (needed for historical data beyond a few days)
- Contract: YMH6 (March 2026), rolls to YMM6 (June 2026) around March 2026

## Performance Notes
- `run_trading_algo_fast` on a full day (1380 bars): ~225ms after JIT warmup
- Backtest full day 664 days: ~4.5 minutes
- Backtest quick mode (9:30-10:30): ~35 seconds
- Bottleneck is O(n²) trendline fitting — refits from scratch every bar. Cannot be easily cached without changing signal accuracy.
- Numba JIT compiles: `_fit_trendlines_nb`, `_compute_rays_nb`, `_run_signals_nb`

## Session Log

### 2026-04-22
- Live paper session ran 9:30-17:00 on IB (port 4002). Result: +236 pts / $1,180
- Removed 10-min reversal hold: +88 pts/day gain (263 vs 142 avg/day baseline, 667 days)
- Added trailing stop v4: threshold=50pts, angles=50/60/70, locked anchor
- Combined result: **266.2 pts/day avg, 78.7% win days, 122 losing days** (667 days, 9:30-17:00)
- Night session added: run_fred_night.bat, scheduled task at 5:58 PM Mon-Fri, clientId=3
- Live chart monitor added: _live_chart_monitor.py (scroll zoom, refresh button, auto-refresh)
- Sweep scripts: _sweep_filters.py, _sweep_trailing.py, _sweep_touchpoints.py
- NOTE: _sweep_filters.py had a bug (defaulted to 10-min hold) — fixed 2026-04-22

### 2026-04-20
- Consolidated codebase: TradingAlgoFast.py is now the single engine
- Deleted TradingAlgo.py, RunAllDays.py, RunFullDataSet.py, all debug scripts
- Added `enable_chart` toggle to IBDataBridge
- Added `--quick` flag to Backtest2Year.py
- Compiled ray computation and signal detection into Numba JIT functions
- Fixed ray start price bug in plotFigure rendering
- Full day backtest run: 664 days, +87.8 pts/day at 10:30, 69.9% win rate
- Git branch: connect-the-highs
