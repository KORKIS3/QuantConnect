# YM Futures Trendline Strategy — Interactive Brokers Bridge

Real-time trading system for the YM E-mini Dow Jones futures contract.
Connects to TWS or IB Gateway via **ib_async**, streams 5-second bars,
runs the trendline algorithm on each bar, and redraws a live chart every minute.

---

## Architecture

```
IB Gateway / TWS
       │
       │  5-sec real-time bars (reqRealTimeBars)
       ▼
 IBDataBridge._on_bar()
       ├── every 5 sec  ──► run_trading_algo()  ──► _place_order()  (BUY / SELL / LIQUIDATE)
       ├── every 1 min  ──► _resample_to_minutes()
       │                         └──► run_trading_algo()
       │                                   └──► _LiveChartWindow.update()  (live matplotlib chart)
       └── end of day   ──► run_live_session()  ──► final chart image + tracking CSV
```

---

## Prerequisites

```bash
pip install ib_async pandas pytz matplotlib numpy
```

**TWS / IB Gateway setup:**
1. Open TWS or IB Gateway.
2. Go to **Configuration → API → Settings**.
3. Enable *"Enable ActiveX and Socket Clients"*.
4. Confirm the port matches the preset you intend to use (see table below).
5. Uncheck *"Read-Only API"* if you want live order execution.

---

## Connection Presets

| Platform        | Mode  | Host        | Port |
|-----------------|-------|-------------|------|
| TWS             | Paper | 127.0.0.1   | 7497 |
| TWS             | Live  | 127.0.0.1   | 7496 |
| IB Gateway      | Paper | 127.0.0.1   | 4002 |
| IB Gateway      | Live  | 127.0.0.1   | 4001 |

---

## Quick Start

```bash
# 1. Verify connectivity (no bars subscribed, no orders placed):
python InteractiveBrokers.py --test --port 4002

# 2. Live feed — signals logged, no orders, live chart visible:
python InteractiveBrokers.py --port 4002 --dry-run --show-plot

# 3. Live feed with order execution (paper account):
python InteractiveBrokers.py --port 4002 --show-plot

# 4. Live feed with output saved:
python InteractiveBrokers.py --port 4002 --show-plot \
    --tracking-root ./tracking \
    --image-root    ./charts
```

---

## CLI Reference

| Flag | Default | Description |
|---|---|---|
| `--host` | `127.0.0.1` | TWS / Gateway host |
| `--port` | `7497` | TWS / Gateway port |
| `--client-id` | `1` | IB client ID (must be unique per connection) |
| `--test` | off | Run connection test only, then exit |
| `--dry-run` | off | Log signals without placing orders |
| `--start-time` | `09:30` | Session window start (ET) passed to algo |
| `--end-time` | `10:00` | Session window end (ET) passed to algo |
| `--show-plot` | off | Display live chart + end-of-session chart |
| `--tracking-root` | `None` | Directory to save per-day tracking CSVs |
| `--image-root` | `None` | Directory to save per-day chart images |

---

## File Structure

```
InteractiveBrokers.py   ← entry point; IB bridge, live chart, order execution
TradingAlgo.py          ← core trendline algorithm (run_trading_algo)
TrendLineAutomation.py  ← trendline math utilities
plotFigure.py           ← ChartPlotter (create_figure / update_plot)
Plotter.py              ← plot_results used at end-of-session
ReOrgMain.py            ← run_live_session (end-of-day CSV + chart pipeline)
                           run_single_day  (offline backtesting from CSV)
RunFullDataSet.py       ← CSV loader (_load_csv_as_df)
RunAllDays.py           ← batch historical backtest runner
tests/
  test_interactive_brokers.py  ← unit tests for IBDataBridge (no gateway required)
  test_scenarios.py            ← scenario / integration tests for TradingAlgo
pyproject.toml          ← pytest configuration
```

---

## Running Tests

```bash
pytest
```

No IB Gateway connection is required — all IB calls are mocked.

---

## Historical Backtesting

Run a single day from a local CSV file:

```python
from ReOrgMain import run_single_day
run_single_day("2026-02-11", show_plot=True)
```

Run every available day in batch mode:

```bash
python RunAllDays.py
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `Connection refused` | TWS/Gateway not running or wrong port | Start TWS/Gateway; check port preset |
| `No YM contract details returned` | API not enabled | Enable socket clients in TWS config |
| `clientId already in use` | Another script connected with the same ID | Change `--client-id` |
| Chart does not appear | `--show-plot` not passed | Add `--show-plot` flag |
| Orders not placed | `--dry-run` active | Remove `--dry-run`; ensure *Read-Only API* is off |

