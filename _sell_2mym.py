"""_sell_2mym.py -- Sell 2 MYM contracts at market."""
from ib_insync import IB, Future, MarketOrder, util

util.logToConsole()

ib = IB()
ib.connect("127.0.0.1", 4002, clientId=99, timeout=30)

contract = Future(symbol="MYM", exchange="CBOT", currency="USD",
                  lastTradeDateOrContractMonth="20260618")
ib.qualifyContracts(contract)

order = MarketOrder("SELL", 2)
trade = ib.placeOrder(contract, order)
ib.sleep(3)
print(f"Status: {trade.orderStatus.status}  filled={trade.orderStatus.filled}  avgFill={trade.orderStatus.avgFillPrice}")
ib.disconnect()
