"""Mirror Account - Copy trades from Account 1 to Account 2.

Account 1 (DUO158495) generates signals from market data.
Account 2 (DUQ921172) reads Account 1's tracking CSV and mirrors positions.

This avoids paying for duplicate market data subscriptions.
"""

import asyncio
import sys
import time
import os
from datetime import datetime
import pytz
import pandas as pd

# Fix for Python 3.14 asyncio
if sys.version_info >= (3, 10):
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

from ib_insync import IB, Future, MarketOrder
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
log.info("Mirror Account Script Starting")
log.info(f"Log file: {log_file}")
log.info("=" * 70)

def get_latest_csv(account_id="DUO158495"):
    """Find the most recent tracking CSV for Account 1."""
    tracking_root = os.path.join(os.path.expanduser("~"), "Desktop", "IB_Live", "tracking")
    today = datetime.now(pytz.timezone("US/Eastern")).strftime("%Y-%m-%d")
    pattern = f"YM_tracking_{account_id}_{today}_*.csv"
    
    import glob
    files = glob.glob(os.path.join(tracking_root, pattern))
    if files:
        return max(files, key=os.path.getmtime)
    return None

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
    
    # Get current IB position
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
    
    log.info(f"[{account_id}] Monitoring Account 1 signals...")
    
    try:
        while True:
            csv_path = get_latest_csv()
            if csv_path and os.path.exists(csv_path):
                try:
                    df = pd.read_csv(csv_path)
                    
                    # Only process if there are new rows
                    if len(df) > last_csv_row_count:
                        # Get the latest row
                        latest_row = df.iloc[-1]
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
            
            ib.sleep(0.1)  # Check every 100ms for minimal delay
            
    except KeyboardInterrupt:
        log.info(f"[{account_id}] Stopping...")
    finally:
        ib.disconnect()

if __name__ == "__main__":
    mirror_trades()
