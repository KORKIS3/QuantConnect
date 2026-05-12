"""Flatten Account 2 (DUQ921172) position.

This script closes any open position in Account 2 by placing an offsetting order.
"""

import sys
import asyncio

# Fix for Python 3.14 asyncio
if sys.version_info >= (3, 10):
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

from ib_insync import IB, Future, MarketOrder
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s  %(levelname)-8s %(message)s')
log = logging.getLogger(__name__)

def flatten_account2():
    """Flatten Account 2 position."""
    
    port = 4003
    client_id = 99  # Use different client ID to avoid conflicts
    account_id = "DUQ921172"
    
    ib = IB()
    
    try:
        log.info(f"Connecting to IB Gateway at 127.0.0.1:{port}...")
        ib.connect('127.0.0.1', port, clientId=client_id)
        log.info(f"Connected successfully")
        
        # Get front-month contract
        base = Future(symbol="MYM", exchange="CBOT", currency="USD")
        contracts = ib.reqContractDetails(base)
        contract = sorted([d.contract for d in contracts], 
                         key=lambda c: c.lastTradeDateOrContractMonth)[0]
        log.info(f"Trading contract: {contract.localSymbol}")
        
        # Get current position
        positions = ib.positions()
        current_position = 0
        
        for pos in positions:
            if pos.contract.symbol in ("MYM", "YM"):
                current_position = int(pos.position)
                log.info(f"Current position: {current_position}")
                break
        
        if current_position == 0:
            log.info("Account is already FLAT. Nothing to do.")
            return
        
        # Calculate offsetting order
        if current_position > 0:
            action = "SELL"
            qty = abs(current_position)
            log.info(f"Position is LONG {current_position}. Placing SELL {qty} to flatten.")
        else:
            action = "BUY"
            qty = abs(current_position)
            log.info(f"Position is SHORT {current_position}. Placing BUY {qty} to flatten.")
        
        # Place flatten order
        order = MarketOrder(action, qty)
        order.tif = "DAY"
        trade = ib.placeOrder(contract, order)
        log.info(f"Order placed: {action} {qty}")
        
        # Wait for fill
        log.info("Waiting for fill...")
        ib.sleep(5)
        
        # Check final position
        positions = ib.positions()
        final_position = 0
        
        for pos in positions:
            if pos.contract.symbol in ("MYM", "YM"):
                final_position = int(pos.position)
                break
        
        log.info(f"Final position: {final_position}")
        
        if final_position == 0:
            log.info("✓ Account successfully flattened!")
        else:
            log.warning(f"⚠ Account still has position: {final_position}")
        
    except Exception as e:
        log.error(f"Error: {e}")
    finally:
        ib.disconnect()
        log.info("Disconnected from IB")

if __name__ == "__main__":
    flatten_account2()
