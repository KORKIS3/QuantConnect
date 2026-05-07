"""_sell_2mym.py -- Sell 2 MYM contracts (go short)."""
import asyncio
asyncio.set_event_loop(asyncio.new_event_loop())
from ib_insync import IB, Future, MarketOrder, util

util.logToConsole()

ib = IB()
ib.connect("127.0.0.1", 4002, clientId=99, timeout=30)

# Show current position first
positions = ib.positions()
print("\nCurrent positions:")
for p in positions:
    if p.contract.symbol in ("YM", "MYM"):
        print(f"  {p.contract.localSymbol}  pos={p.position}  avgCost={p.avgCost:.2f}")

# Resolve front month contract
from datetime import date
base = Future(symbol="MYM", exchange="CBOT", currency="USD")
details = ib.reqContractDetails(base)
today = date.today().strftime("%Y%m%d")
active = sorted([d.contract for d in details if d.contract.lastTradeDateOrContractMonth >= today],
                key=lambda c: c.lastTradeDateOrContractMonth)
contract = active[0]
print(f"\nSelling 2 {contract.localSymbol} @ market...")

order = MarketOrder("SELL", 2)
order.tif = "DAY"
trade = ib.placeOrder(contract, order)
ib.sleep(5)
print(f"Status: {trade.orderStatus.status}  filled={trade.orderStatus.filled}  avgFill={trade.orderStatus.avgFillPrice}")

print("\nFinal position:")
for p in ib.positions():
    if p.contract.symbol in ("YM", "MYM"):
        print(f"  {p.contract.localSymbol}  pos={p.position}  avgCost={p.avgCost:.2f}")

ib.disconnect()
