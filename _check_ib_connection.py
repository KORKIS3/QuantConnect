"""Quick IB Gateway connection check"""
import asyncio
from ib_insync import IB

async def check():
    ib = IB()
    try:
        await ib.connectAsync('127.0.0.1', 4002, clientId=99, timeout=5)
        print("✓ Connected to IB Gateway (Paper Trading - Port 4002)")
        
        positions = ib.positions()
        if positions:
            print(f"\n⚠ WARNING: Account has {len(positions)} open position(s):")
            for p in positions:
                print(f"  {p.contract.symbol}: {p.position} contracts @ {p.avgCost}")
        else:
            print("✓ Account is FLAT (no open positions)")
        
        ib.disconnect()
        return True
    except Exception as e:
        print(f"✗ Failed to connect to IB Gateway: {e}")
        print("\nTroubleshooting:")
        print("  1. Is IB Gateway running?")
        print("  2. Is it configured for port 4002 (paper) or 4001 (live)?")
        print("  3. Is 'Enable ActiveX and Socket Clients' enabled in Gateway settings?")
        return False

if __name__ == "__main__":
    asyncio.run(check())
