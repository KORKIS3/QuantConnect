# Fred Live Trading — Monday Go-Live Checklist

## Pre-Market (Before 9:28 AM ET)

### 1. Run Pre-Flight Check
```bash
python _preflight_check.py
```
**All checks must pass before proceeding.**

### 2. Verify IB Gateway
- [ ] IB Gateway is running and logged in
- [ ] Connected to LIVE account (port 4001)
- [ ] Account is FLAT (no open YM/MYM positions)
- [ ] No pending orders

### 3. Verify Scheduled Task
```powershell
Get-ScheduledTask -TaskName "FredDaySession" | Select-Object State, LastRunTime, NextRunTime
```
- [ ] State = "Ready"
- [ ] NextRunTime = Today 9:28 AM

### 4. Clear Stop File (if exists)
```bash
rm ~/Desktop/IB_Live/FRED_STOP
```

---

## During Market Hours (9:30 AM - 4:55 PM ET)

### First 30 Minutes (Critical Monitoring Period)

#### 9:30 AM - Fred Starts
- [ ] Live chart window opens automatically
- [ ] Chart shows price bars updating every minute
- [ ] Orange/yellow/purple/blue rays are visible
- [ ] No error messages in console

#### 9:42 AM - First Signal Possible
- [ ] If signal fires, verify:
  - [ ] Log shows `[TradingAlgo] BUY` or `[TradingAlgo] SELL`
  - [ ] Log shows `[ORDER placed]`
  - [ ] IB Gateway shows order filled
  - [ ] Chart shows position change (red/green background)

#### 9:45 AM - Run IB Monitor
```bash
python _ib_log_monitor.py
```
- [ ] Monitor shows today's fills
- [ ] Fill times match chart signal times (within 1 minute)
- [ ] Fill prices match chart prices (within 5 points)
- [ ] Position matches chart position

### Ongoing Monitoring

#### Every Hour
- [ ] Check live chart is still updating
- [ ] Check IB monitor matches chart
- [ ] Verify no error messages in log

#### If Anything Looks Wrong
**STOP IMMEDIATELY:**
```bash
python _flatten_position.py
```
This will:
1. Create `FRED_STOP` file to halt Fred
2. Flatten any open position
3. Stop Fred from placing new orders

---

## Post-Market (After 4:55 PM ET)

### 1. Verify Session End
- [ ] Fred flattened position at 4:55 PM
- [ ] Final position = FLAT (0 contracts)
- [ ] Session summary email received

### 2. Review Results
```bash
python _ib_log_monitor.py
```
- [ ] All fills are accounted for
- [ ] No unexpected trades
- [ ] P/L matches chart

### 3. Compare to Backtest
```bash
python _run_may8.py  # replace with today's date
```
- [ ] Live P/L within 50 pts of backtest P/L
- [ ] Trade count similar to backtest
- [ ] No major divergence

### 4. Check Logs
```bash
ls ~/Desktop/IB_Live/logs/fred_ib_*.log
```
- [ ] Log file exists for today
- [ ] No ERROR messages (WARNING is OK)
- [ ] Position sync messages show correct tracking

---

## What Changed Since May 8th

### Bugs Fixed
1. **Liquidation order direction** — was inverted, now correct
2. **Session end flatten timing** — now uses wall-clock safety net
3. **Timestamped CSV filenames** — prevents overwriting on restart

### New Safety Features
1. **Pre-trade position reconciliation** — Fred queries IB position before every signal
2. **Portfolio update tracking** — Fred syncs `_ib_position` on every fill confirmation
3. **Pending order flag** — prevents rapid-fire orders before fill confirmation

### Position Tracking Flow
```
Startup:
  → Fred queries IB positions
  → Syncs _ib_position to actual IB position
  → Subscribes to portfolio updates

Every Signal:
  → Fred queries IB positions (reconciliation)
  → Corrects _ib_position if out of sync
  → Places order based on actual IB position

Every Fill:
  → IB sends portfolio update
  → Fred updates _ib_position
  → Clears _pending_order flag
```

---

## Emergency Contacts

### If Fred Malfunctions
1. Run `python _flatten_position.py` immediately
2. Check IB Gateway for actual position
3. Manually flatten if needed
4. Review logs: `~/Desktop/IB_Live/logs/fred_ib_*.log`

### If Position Gets Out of Sync
**DO NOT place manual trades while Fred is running.**

If you must intervene:
1. Stop Fred: `python _flatten_position.py`
2. Manually flatten position in IB Gateway
3. Wait 1 minute
4. Restart Fred: `run_fred_daily.bat`
5. Fred will sync to flat position on startup

---

## Success Criteria

### Day 1 (Monday)
- [ ] Fred starts and stops cleanly
- [ ] All fills match chart signals
- [ ] Position tracking stays accurate all day
- [ ] Ends flat at 4:55 PM
- [ ] P/L within 50 pts of backtest

### Week 1
- [ ] 5 consecutive days with no position sync issues
- [ ] Average P/L > 200 pts/day
- [ ] Win rate > 70%
- [ ] No manual interventions needed

### Month 1
- [ ] Average P/L > 250 pts/day
- [ ] Win rate > 75%
- [ ] Matches or exceeds backtest baseline (276.5 pts/day)

---

## Backtest Baseline (as of 2026-05-09)

**Full day session (9:30-17:00, 667 days):**
- Average: **276.5 pts/day**
- Win rate: **79.6%**
- Losing days: **119**
- Total: **184,466 pts** ($922,330)

**Strategy:**
- 2 contracts
- Partial TP @ 50 pts (close 1 of 2)
- Spike exit @ 100 pts within 5 bars
- Trailing stop v4 (50/60/70° angles)
- Blue/purple ray re-anchoring enabled
- WM shield @ 12 pts
- Min entry angle 30°
- Steep angle threshold 70°

---

## Notes

- Fred uses **clientId=1** for day session
- Manual trades should use **different clientId** (98, 99) to avoid confusion
- **NEVER place manual trades while Fred is running** — this caused the May 8th issue
- If you need to intervene, stop Fred first, then act, then restart Fred
