# Fred Pre-Flight Status - May 15, 2026 9:12 AM

## ⚠️ NOT READY FOR LIVE TRADING

### Critical Issues

1. **Order Quantity Bug Just Fixed (9:10 AM)**
   - Root cause: IB position API returns stale data
   - Symptom: 6-contract orders instead of 2-contract orders
   - Fix: Changed to use algo's target position instead of IB's stale position
   - **Status**: Code fixed, NOT TESTED in paper trading yet

2. **Backtest Performance: -3.8 pts/day**
   - Previous 340 pts/day was due to P/L calculation bug
   - With correct P/L accounting: strategy loses money
   - **Status**: Strategy needs re-evaluation before live trading

3. **IB Gateway Connection: UNKNOWN**
   - Python 3.14 asyncio issue prevents connection check
   - Cannot verify account is flat
   - Cannot verify Gateway is running
   - **Status**: Manual verification required

### Configuration Status

✓ **Port**: 4002 (Paper Trading)
✓ **Contracts**: 2 MYM
✓ **Config**: Current live settings loaded
⚠️ **Dry Run**: Defaults to FALSE (live mode)
⚠️ **Duration**: Need --duration 450 for full day (9:30-17:00)

### Recommended Actions

**IMMEDIATE (Before 9:30 AM):**

1. **Manually verify IB Gateway**:
   - Open IB Gateway application
   - Confirm "Connected" status (green)
   - Check Portfolio tab - should show 0 positions
   - Verify port 4002 (paper trading)

2. **Run Fred in DRY RUN mode first**:
   ```bash
   python run_fred.py --duration 450 --dry-run
   ```
   - This will log signals without placing orders
   - Verify no 6-contract orders in logs
   - Monitor for 30-60 minutes

3. **If dry run looks good, switch to paper trading**:
   ```bash
   python run_fred.py --duration 450
   ```
   - Port 4002 = paper trading (no real money)
   - Monitor closely for order quantity issues
   - Verify orders are 2 or 4 contracts only (never 6)

**DO NOT RUN LIVE (port 4001) UNTIL:**
- [ ] Paper trading session completes successfully
- [ ] No 6-contract orders observed
- [ ] Backtest shows positive performance with correct P/L
- [ ] At least 3-5 successful paper trading days

### Manual IB Gateway Checklist

Since automated check failed, manually verify:

- [ ] IB Gateway is running
- [ ] Shows "Connected" (green indicator)
- [ ] Port configured: 4002 (paper) or 4001 (live)
- [ ] "Enable ActiveX and Socket Clients" is checked in settings
- [ ] Account shows 0 open positions
- [ ] No pending orders from yesterday
- [ ] Contract: MYM Jun'18/26 (check expiration)

### Commands to Run

```bash
# Navigate to project
cd C:\Users\Administrator\source\repos\KORKIS3\QuantConnect

# Start Fred in DRY RUN (no orders, just logs)
python run_fred.py --duration 450 --dry-run

# If dry run OK, start Fred in PAPER mode (port 4002)
python run_fred.py --duration 450 --port 4002

# DO NOT RUN THIS YET (live trading):
# python run_fred.py --duration 450 --port 4001
```

### What to Monitor

During session:
- Console output for "ORDER placed" messages
- Verify qty=2 for entries, qty=4 for reversals
- Never see qty=6 or higher
- Check IB Gateway "Orders" tab for actual orders placed
- Monitor P/L in tracking CSV

### Current Time
9:12 AM ET - 18 minutes until market open

### Decision
**PAPER TRADE TODAY** - Do not go live until:
1. Order quantity fix verified in paper trading
2. Backtest performance improved
3. Multiple successful paper trading sessions completed

---

**Last Updated**: 2026-05-15 09:12 AM
**Status**: Code fixed, awaiting paper trading verification
**Next Review**: After today's paper trading session (5:00 PM)
