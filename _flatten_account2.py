"""Flatten Account 2 (DUQ921172) — emergency close all positions."""
import asyncio
asyncio.set_event_loop(asyncio.new_event_loop())
from ib_insync import IB, MarketOrder, util
import time

util.logToConsole()

ib = IB()
ib.connect("127.0.0.1", 4003, clientId=98, timeout=30)

print("\n=== ACCOUNT 2 (DUQ921172) FLATTEN ===")
positions = ib.positions()
print("\nAll positions across all accounts:")
for p in positions:
    print(f"  Account={p.account} {p.contract.symbol} {p.contract.localSymbol} pos={p.position} avgCost={p.avgCost:.2f}")

for p in positions:
    if p.account != "DUQ921172":
        continue
    sym = p.contract.symbol
    if sym not in ("YM", "MYM"):
        continue
    pos = int(p.position)
    if pos == 0:
        continue
    action = "BUY" if pos < 0 else "SELL"
    qty = abs(pos)
    print(f"\nFlattening Account 2: {action} {qty} {sym} contracts...")
    p.contract.exchange = "CBOT"
    order = MarketOrder(action, qty)
    order.tif = "DAY"
    order.account = "DUQ921172"
    trade = ib.placeOrder(p.contract, order)
    ib.sleep(3)
    print(f"  Status: {trade.orderStatus.status} filled={trade.orderStatus.filled} avgFill={trade.orderStatus.avgFillPrice}")

ib.sleep(2)
print("\nFinal positions (Account 2):")
for p in ib.positions():
    if p.account == "DUQ921172" and p.contract.symbol in ("YM", "MYM"):
        print(f"  {p.contract.localSymbol} pos={p.position}")

ib.disconnect()
print("\nDone.")
