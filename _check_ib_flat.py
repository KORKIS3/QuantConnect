"""Check if IB account is flat."""

import asyncio
from ib_insync import IB

async def check_position():
    ib = IB()
    
    try:
        # Connect to paper trading
        print("Connecting to IB Gateway (paper)...")
        await ib.connectAsync('127.0.0.1', 4002, clientId=99, timeout=10)
        print("Connected!")
        
        # Get all positions
        positions = ib.positions()
        
        if not positions:
            print("\n✓ Account is FLAT - no open positions")
            return True
        
        print(f"\n❌ Account has {len(positions)} open position(s):")
        for pos in positions:
            print(f"  {pos.contract.symbol} {pos.contract.lastTradeDateOrContractMonth}: {pos.position:+.0f} contracts")
        
        return False
        
    except Exception as e:
        print(f"\n❌ Error connecting to IB: {e}")
        print("\nMake sure:")
        print("  1. IB Gateway is running")
        print("  2. Paper trading port 4002 is configured")
        print("  3. API connections are enabled")
        return False
        
    finally:
        ib.disconnect()


if __name__ == "__main__":
    is_flat = asyncio.run(check_position())
