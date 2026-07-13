"""Mirror Account - Copy trades from Account 1 to Account 2.

Account 1 (DUO158495) generates signals from market data.
Account 2 (DUQ921172) reads Account 1's tracking CSV and mirrors positions.

This avoids paying for duplicate market data subscriptions.

CRITICAL FIXES (2026-05-14):
- Only read CSV data from TODAY's session (validate timestamps)
- Flatten any pre-existing positions at startup
- Ignore stale data from previous sessions
- Check file modification time to ensure fresh data
"""

import asyncio
import sys
import time
import os
from datetime import datetime, date
import pytz
import pandas as pd

# Fix for Python 3.14 asyncio
if sys.version_info >= (3, 10):
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

from ib_async import IB, Future, MarketOrder
import logging

# Setup logging to file
log_dir = os.path.join(os.path.expanduser("~"), "Desktop", "IB_Live", "logs")
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, f"fred_mirror_DUQ921172_{datetime.now().strftime('%Y%m%d_%H%M')}.log")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s  %(levelname)-8s %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()  # Also log to console
    ]
)
log = logging.getLogger(__name__)

log.info("=" * 70)
log.info("Mirror Account Script Starting (FIXED VERSION)")
log.info(f"Log file: {log_file}")
log.info("=" * 70)

_EST = pytz.timezone("US/Eastern")

def get_latest_csv(account_id="DUO158495"):
    """Find the most recent tracking CSV for Account 1 from TODAY's session only."""
    tracking_root = os.path.join(os.path.expanduser("~"), "Desktop", "IB_Live", "tracking")
    today = datetime.now(_EST).strftime("%Y-%m-%d")
    pattern = f"YM_tracking_{account_id}_{today}_*.csv"
    
    import glob
    files = glob.glob(os.path.join(tracking_root, pattern))
    if not files:
        return None
    
    latest = max(files, key=os.path.getmtime)
    
    # Verify the file was modified recently (within last 5 minutes)
    file_age = time.time() - os.path.getmtime(latest)
    if file_age > 300:  # 5 minutes
        log.warning(f"[CSV] File is stale (age: {file_age:.0f}s). Waiting for fresh data...")
        return None
    
    return latest

def validate_csv_timestamp(csv_path):
    """Validate that the CSV contains data from today's session only.
    
    Returns True if valid, False if stale/old data detected.
    """
    try:
        df = pd.read_csv(csv_path, index_col=0, parse_dates=True)
        if df.empty:
            return True  # Empty is OK, just starting
        
        # Check the most recent timestamp in the CSV
        last_timestamp = pd.to_datetime(df.index[-1])
        today = datetime.now(_EST).date()
        if last_timestamp.tzinfo is not None:
            csv_date = last_timestamp.tz_convert(_EST).date()
        else:
            csv_date = last_timestamp.date()
        
        if csv_date != today:
            log.error(f"[CSV] STALE DATA DETECTED: CSV contains data from {csv_date}, but today is {today}")
            return False
        
        # Check that the data is recent (within last 5 minutes)
        now = datetime.now(_EST)
        if last_timestamp.tzinfo is None:
            last_ts_est = _EST.localize(last_timestamp)
        else:
            last_ts_est = last_timestamp.tz_convert(_EST)
        age_seconds = (now - last_ts_est).total_seconds()
        if age_seconds > 300:  # 5 minutes
            log.warning(f"[CSV] Data is {age_seconds:.0f}s old - may be stale")
        
        return True
    except Exception as e:
        log.error(f"[CSV] Validation error: {e}")
        return False

def flatten_position(ib, contract, account_id):
    """Flatten any pre-existing position at startup to ensure clean slate."""
    try:
        positions = ib.positions()
        for pos in positions:
            if pos.contract.symbol in ("MYM", "YM") and pos.account == account_id:
                qty = int(pos.position)
                if qty != 0:
                    log.warning(f"[{account_id}] PRE-EXISTING POSITION DETECTED: {qty} contracts")
                    log.warning(f"[{account_id}] FLATTENING position to start clean...")
                    
                    action = "SELL" if qty > 0 else "BUY"
                    order = MarketOrder(action, abs(qty))
                    order.tif = "DAY"
                    trade = ib.placeOrder(contract, order)
                    ib.sleep(2)  # Wait for fill
                    
                    log.info(f"[{account_id}] Position flattened: {action} {abs(qty)}")
                    return
        
        log.info(f"[{account_id}] No pre-existing position - starting flat")
    except Exception as e:
        log.error(f"[{account_id}] Error flattening position: {e}")

def mirror_trades(port=4003, client_id=2, account_id="DUQ921172"):
    """Mirror trades from Account 1 to Account 2."""
    
    ib = IB()
    ib.connect('127.0.0.1', port, clientId=client_id)
    log.info(f"[{account_id}] Connected to IB at 127.0.0.1:{port}")
    
    # Get front-month contract
    base = Future(symbol="MYM", exchange="CBOT", currency="USD")
    contracts = ib.reqContractDetails(base)
    contract = sorted([d.contract for d in contracts], 
                     key=lambda c: c.lastTradeDateOrContractMonth)[0]
    log.info(f"[{account_id}] Trading contract: {contract.localSymbol}")
    
    # Flatten any pre-existing position to start clean
    flatten_position(ib, contract, account_id)
    
    # Get current IB position after flattening
    positions = ib.positions()
    ib_position = 0
    for pos in positions:
        if pos.contract.symbol in ("MYM", "YM"):
            ib_position = int(pos.position)
            log.info(f"[{account_id}] Current IB position: {ib_position}")
            break
    
    # Track what we think Account 1's position is
    account1_position = 0
    last_csv_row_count = 0
    last_csv_mtime = 0
    csv_validated = False
    
    log.info(f"[{account_id}] Monitoring Account 1 signals...")
    
    try:
        while True:
            csv_path = get_latest_csv()
            if csv_path and os.path.exists(csv_path):
                # Check if file has been modified since last read
                current_mtime = os.path.getmtime(csv_path)
                if current_mtime == last_csv_mtime:
                    ib.sleep(0.1)  # No changes, check again soon
                    continue
                
                last_csv_mtime = current_mtime
                
                # Validate CSV contains today's data only (only need to do this once per file)
                if not csv_validated:
                    if not validate_csv_timestamp(csv_path):
                        log.error(f"[{account_id}] REFUSING to trade on stale CSV data - waiting for fresh data...")
                        ib.sleep(5)  # Wait longer before checking again
                        csv_validated = False
                        continue
                    csv_validated = True
                    log.info(f"[{account_id}] CSV validated - contains today's data")
                
                try:
                    df = pd.read_csv(csv_path, index_col=0, parse_dates=True)
                    
                    # Only process if there are new rows
                    if len(df) > last_csv_row_count:
                        # Get the latest row
                        latest_row = df.iloc[-1]
                        
                        # Use ib_position column (actual IB fills) if available,
                        # otherwise fall back to theoretical position column
                        if 'ib_position' in df.columns and pd.notna(latest_row.get('ib_position')):
                            position_str = str(latest_row['ib_position']).lower()
                        else:
                            position_str = str(latest_row.get('position', 'flat')).lower()
                        
                        # Convert position string to number
                        if position_str == 'long':
                            account1_position = 2
                        elif position_str == 'short':
                            account1_position = -2
                        else:
                            account1_position = 0
                        
                        # Check if we need to sync
                        if ib_position != account1_position:
                            qty_diff = account1_position - ib_position
                            
                            if qty_diff > 0:
                                action = "BUY"
                                qty = abs(qty_diff)
                            else:
                                action = "SELL"
                                qty = abs(qty_diff)
                            
                            log.info(f"[{account_id}] POSITION MISMATCH: IB={ib_position}, Account1={account1_position}")
                            log.info(f"[{account_id}] SYNCING: {action} {qty} to match Account 1")
                            
                            # Place order to sync
                            order = MarketOrder(action, qty)
                            order.tif = "DAY"
                            trade = ib.placeOrder(contract, order)
                            
                            # Wait for fill
                            ib.sleep(2)
                            
                            # Update our tracked IB position
                            positions = ib.positions()
                            for pos in positions:
                                if pos.contract.symbol in ("MYM", "YM"):
                                    ib_position = int(pos.position)
                                    log.info(f"[{account_id}] Position after sync: {ib_position}")
                                    break
                        
                        last_csv_row_count = len(df)
                        
                except Exception as e:
                    log.error(f"[{account_id}] Error reading CSV: {e}")
            else:
                # No CSV file found yet - wait for Account 1 to start
                ib.sleep(1)
            
            ib.sleep(0.1)  # Check every 100ms for minimal delay
            
    except KeyboardInterrupt:
        log.info(f"[{account_id}] Stopping...")
    finally:
        ib.disconnect()

if __name__ == "__main__":
    mirror_trades()
