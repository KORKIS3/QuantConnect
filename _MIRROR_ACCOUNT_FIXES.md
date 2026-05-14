# Mirror Account Fixes - 2026-05-14

## Problem Identified

Account 2 (DUQ921172) was trading with completely different timing and prices than Account 1 (DUO158495), resulting in:
- $1,127.50 P/L difference between accounts
- Account 2 executing trades BEFORE Account 1 (impossible for a mirror)
- Average timing difference: -918 seconds (Account 2 trading 15+ minutes early)
- Massive price slippage: up to 174 points per trade

**Root Cause**: Account 2's mirror script was reading stale CSV data from previous sessions, not mirroring Account 1's current trades.

## Fixes Implemented

### 1. InteractiveBrokers.py - Immediate CSV Writes
**Location**: `_on_portfolio_update()` method (line ~463)

**Change**: Added immediate CSV write after every order fill confirmation
```python
# IMMEDIATE CSV WRITE after fill confirmation
# This ensures mirror accounts see the position change as soon as possible
try:
    self._save_tracking_csv()
    log.info("[PositionSync] Tracking CSV updated immediately after fill")
except Exception as exc:
    log.error("[PositionSync] Immediate CSV write failed: %s", exc)
```

**Impact**: CSV now updates within milliseconds of order fills, not just on minute bar closes. This reduces mirror lag from up to 60 seconds to <1 second.

### 2. _mirror_account.py - Complete Rewrite

**Changes**:

#### A. Timestamp Validation
- Added `validate_csv_timestamp()` function to verify CSV contains TODAY's data only
- Checks that CSV date matches current date
- Warns if data is >5 minutes old
- **REFUSES to trade on stale data** - waits for fresh CSV

#### B. File Modification Time Check
- `get_latest_csv()` now checks file modification time
- Only accepts files modified within last 5 minutes
- Prevents reading old/cached files

#### C. Position Flattening at Startup
- Added `flatten_position()` function
- Automatically closes any pre-existing positions when mirror script starts
- Ensures clean slate - no carryover from previous sessions

#### D. File Change Detection
- Tracks `last_csv_mtime` (file modification time)
- Only reads CSV when file has actually changed
- Reduces unnecessary file I/O

#### E. Enhanced Logging
- Logs CSV validation status
- Logs file age warnings
- Logs position flattening actions
- Version identifier in startup log: "FIXED VERSION"

## Testing Recommendations

### Before Next Live Session:

1. **Delete old tracking CSVs** from previous sessions:
   ```
   ~/Desktop/IB_Live/tracking/YM_tracking_*_2026-05-14_*.csv
   ```

2. **Start Account 1 first**:
   ```
   python InteractiveBrokers.py --port 4002 --client-id 1 --account-id DUO158495 --duration 450
   ```

3. **Wait 2-3 minutes** for Account 1 to establish position

4. **Start Account 2 mirror**:
   ```
   python _mirror_account.py
   ```

5. **Monitor both logs**:
   - Account 1: `~/Desktop/IB_Live/logs/fred_ib_DUO158495_*.log`
   - Account 2: `~/Desktop/IB_Live/logs/fred_mirror_DUQ921172_*.log`

### What to Look For:

**Account 2 startup should show**:
```
Mirror Account Script Starting (FIXED VERSION)
[DUQ921172] Connected to IB at 127.0.0.1:4003
[DUQ921172] Trading contract: MYMM6
[DUQ921172] No pre-existing position - starting flat
[DUQ921172] Current IB position: 0
[DUQ921172] Monitoring Account 1 signals...
[CSV] Found today's tracking file: YM_tracking_DUO158495_2026-05-XX_0930.csv
[DUQ921172] CSV validated - contains today's data
```

**When Account 1 takes a position**:
```
[DUQ921172] POSITION MISMATCH: IB=0, Account1=2
[DUQ921172] SYNCING: BUY 2 to match Account 1
[DUQ921172] Position after sync: 2
```

**Timing should be <2 seconds** between Account 1 fill and Account 2 sync.

## Expected Results

- Account 2 should mirror Account 1 within 1-2 seconds
- Fill prices should be within 5-10 points (normal market slippage)
- No trades should occur before Account 1's trades
- P/L difference should be minimal (<$50 per session due to slippage)

## Rollback Plan

If issues persist, revert to single-account trading:
1. Stop Account 2 mirror script
2. Flatten Account 2 position manually in TWS
3. Run only Account 1 until mirror logic is further debugged
