"""_flatten_position.py -- Emergency flatten: closes all open YM/MYM positions."""
import asyncio
asyncio.set_event_loop(asyncio.new_event_loop())
from ib_insync import IB, MarketOrder, util
import time

util.logToConsole()

ib = IB()
ib.connect("127.0.0.1", 4002, clientId=99, timeout=30)  # paper port

positions = ib.positions()
print("\nCurrent positions:")
for p in positions:
    print(f"  {p.contract.symbol} {p.contract.localSymbol}  pos={p.position}  avgCost={p.avgCost:.2f}")

for p in positions:
    sym = p.contract.symbol
    if sym not in ("YM", "MYM"):
        continue
    pos = p.position
    if pos == 0:
        continue
    action = "BUY" if pos < 0 else "SELL"
    qty = int(abs(pos))
    print(f"\nFlattening {sym}: {action} {qty} contracts...")
    p.contract.exchange = "CBOT"
    order = MarketOrder(action, qty)
    order.tif = "DAY"
    trade = ib.placeOrder(p.contract, order)
    ib.sleep(3)
    print(f"  Status: {trade.orderStatus.status}  filled={trade.orderStatus.filled}  avgFill={trade.orderStatus.avgFillPrice}")

ib.sleep(2)
print("\nDone. Final positions:")
for p in ib.positions():
    if p.contract.symbol in ("YM", "MYM"):
        print(f"  {p.contract.localSymbol}  pos={p.position}")

ib.disconnect()
