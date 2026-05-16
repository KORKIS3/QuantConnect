# Fred Morning Prep Checklist

## Pre-Market (Before 9:28 AM ET)

### 1. IB Gateway Setup
- [ ] **Launch IB Gateway** (not TWS - Gateway is lighter)
- [ ] **Login credentials entered** and authenticated
- [ ] **Paper trading mode confirmed** (port 4002) OR **Live mode** (port 4001)
- [ ] **Gateway shows "Connected"** status (green indicator)
- [ ] **Check contract expiration**: Currently trading MYM (Micro YM)
  - Check if current contract month is still active
  - Roll to next month if needed (usually 2nd Friday of contract month)

### 2. Account Status Check
- [ ] **Verify account is FLAT** (no open positions)
  - Check IB Gateway portfolio tab
  - Or run: `python -c "from ib_insync import *; ib = IB(); ib.connect('127.0.0.1', 4002, clientId=99); print('Positions:', ib.positions()); ib.disconnect()"`
- [ ] **Check account balance** and available margin
- [ ] **Verify no pending orders** from previous session

### 3. Data & System Check
- [ ] **Download yesterday's data** (if not already done)
  - Run: `python download_yesterday.py`
  - Verify CSV created in `~/Desktop/2YearsData/full_day/`
- [ ] **Clear Numba cache** (if algo parameters changed)
  - Run: `python clear_numba_cache.py`
- [ ] **Check system time** is synced (critical for order timing)
- [ ] **Verify disk space** for logging (tracking folder can grow large)

### 4. Fred Configuration Review
- [ ] **Check current AlgoConfig** in `InteractiveBrokers.py` (lines 263-276):
  ```python
  warmup_minutes=5           # First signal at 9:42 (9:30 + 12 min)
  steep_angle_threshold=65.0 # Steep line cross angle
  proximity_points=8.0       # Suppress if within 8pts of shallow ray
  min_reversal_minutes=0     # No hold time (removed 10-min rule)
  min_entry_angle=15.0       # Wait for 15° before first entry
  partial_tp_pts=50.0        # Close 1 contract at +50pts
  num_contracts=2            # Trading 2 MYM contracts
  steep_line_reentry=True    # Allow steep line to trigger first trade
  ```
- [ ] **Verify dry_run setting**:
  - `dry_run=True` for paper trading (no real orders)
  - `dry_run=False` for live trading (REAL MONEY)
- [ ] **Check session times**: 9:30 - 17:00 ET (day session)

### 5. Fred Startup (9:28 AM ET)
- [ ] **Navigate to project folder**:
  ```bash
  cd C:\Users\Administrator\source\repos\KORKIS3\QuantConnect
  ```
- [ ] **Start Fred** (scheduled task should auto-start, or manual):
  ```bash
  run_fred_daily.bat
  ```
  - This runs: `python run_fred.py --duration 450`
  - Duration 450 = 7.5 hours (9:30 to 17:00)
- [ ] **Verify Fred connected to IB**:
  - Look for "Connected to IB" message in console
  - Check for "Subscribed to real-time bars" message
- [ ] **Monitor first few bars** (9:30-9:35):
  - Verify bars are arriving every minute
  - Check that orange/yellow/purple/blue rays are being calculated
  - Confirm no errors in console

### 6. During Session Monitoring
- [ ] **Check Fred console** every 15-30 minutes for errors
- [ ] **Monitor IB Gateway** for connection status (stays green)
- [ ] **Watch for first trade** (usually 9:42-9:50):
  - Console will show "BUY" or "SELL" signal
  - IB Gateway will show order submitted/filled
- [ ] **Check tracking CSV** periodically:
  - Located in: `~/Desktop/IB_Live/tracking/`
  - File: `live_session_YYYY-MM-DD_account1.csv` (or account2)
  - Verify `session_pl` column is updating correctly

### 7. End of Day (After 17:00 ET)
- [ ] **Verify Fred closed all positions** (should auto-liquidate at 17:00)
- [ ] **Check final P/L** in tracking CSV (`session_pl` last row)
- [ ] **Review trades** in IB Gateway "Trades" tab
- [ ] **Compare CSV P/L vs IB realized P/L**:
  - CSV shows points (multiply by $0.50 for MYM dollar P/L)
  - IB shows dollar P/L directly
  - Slippage is normal (1-3 points per trade)
- [ ] **Save chart snapshot** (if enabled):
  - Located in: `~/Desktop/IB_Live/charts/`
- [ ] **Stop Fred** (Ctrl+C in console, or it auto-stops after duration)

---

## Quick Commands Reference

```bash
# Download yesterday's data
python download_yesterday.py

# Clear cache (after config changes)
python clear_numba_cache.py

# Start Fred (day session, paper trading)
python run_fred.py --duration 450

# Start Fred (live trading - REAL MONEY)
python run_fred.py --duration 450  # (set dry_run=False in InteractiveBrokers.py first)

# Check if IB is reachable
python -c "from ib_insync import *; ib = IB(); ib.connect('127.0.0.1', 4002, clientId=99); print('Connected!'); ib.disconnect()"

# View today's tracking CSV
python -c "import pandas as pd; from pathlib import Path; from datetime import datetime; f = Path.home() / 'Desktop' / 'IB_Live' / 'tracking' / f'live_session_{datetime.now().strftime(\"%Y-%m-%d\")}_account1.csv'; print(pd.read_csv(f).tail(10) if f.exists() else 'No file yet')"
```

---

## Emergency Procedures

### If Fred Crashes Mid-Session
1. **Check IB Gateway** - still connected?
2. **Check account positions** - are we flat or holding?
3. **If holding a position**:
   - Manually close in IB Gateway, OR
   - Restart Fred (it will detect open position and manage it)
4. **Check error message** in console
5. **Restart Fred**: `python run_fred.py --duration [remaining_minutes]`

### If IB Gateway Disconnects
1. **Fred will show "Connection lost"** error
2. **Reconnect IB Gateway** (login again)
3. **Fred should auto-reconnect** within 30 seconds
4. **If not, restart Fred**

### If Wrong Direction Trade
1. **DO NOT PANIC** - Fred has trailing stops
2. **Let Fred manage the trade** (it will reverse on line cross)
3. **If emergency**: Manually close in IB Gateway
4. **Fred will detect flat position** and resume trading

### If Need to Stop Fred Immediately
1. **Press Ctrl+C** in Fred console (graceful shutdown)
2. **Fred will attempt to close open positions** before exiting
3. **If Fred doesn't respond**: Close IB Gateway (kills connection, Fred will error out)
4. **Manually close positions** in IB Gateway if needed

---

## Current Known Issues (as of May 14, 2026)

1. **P/L Calculation**: CSV may show different P/L than IB due to:
   - Partial TP averaging logic (recently fixed)
   - Slippage between signal price and fill price (1-3 pts normal)
   - **Action**: Always verify final P/L against IB realized P/L

2. **Steep Line Rendering**: Steep dotted lines may not show on chart
   - Data is correct, rendering issue only
   - Does NOT affect trading logic
   - **Action**: Ignore for now, chart is for visualization only

3. **Backtest Performance**: Recent fix to P/L calculation shows -9.6 pts/day (was +340)
   - Previous results were incorrect due to P/L bug
   - **Action**: Re-evaluate strategy parameters before going live with real money
   - **Recommendation**: Continue paper trading until positive backtest confirmed

---

## Notes

- **MYM contract value**: $0.50 per point (Micro YM)
- **YM contract value**: $5.00 per point (Mini YM) - NOT currently trading this
- **Typical slippage**: 1-3 points per trade (normal market conditions)
- **Fred's edge**: Based on line-crossing system, 50+ point threshold for steep lines
- **Risk per trade**: Max 2 contracts, partial TP at +50pts reduces risk
- **Session duration**: 7.5 hours (9:30-17:00 ET)
- **Scheduled task**: Fred auto-starts at 9:28 AM Mon-Fri (if configured)

---

**Last Updated**: May 14, 2026
**Current Branch**: `good-340-config` (note: 340 pts/day result is now known to be incorrect)
**Current Status**: Paper trading only - DO NOT trade live until backtest shows positive results
