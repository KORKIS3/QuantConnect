"""Check current IB position."""
import asyncio
asyncio.set_event_loop(asyncio.new_event_loop())
from ib_insync import IB, util
util.logToConsole("ERROR")

ib = IB()
ib.connect("127.0.0.1", 4002, clientId=99, timeout=30)

positions = ib.positions()
mym = [p for p in positions if p.contract.symbol in ("YM", "MYM")]

if not mym:
    print("FLAT — no open MYM/YM positions")
else:
    for p in mym:
        print(f"{p.contract.localSymbol}  pos={p.position}  avgCost={p.avgCost:.2f}")

ib.disconnect()
