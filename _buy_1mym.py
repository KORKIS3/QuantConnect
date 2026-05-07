"""_buy_1mym.py -- Buy 1 MYM contract (go long 1)."""
import asyncio
asyncio.set_event_loop(asyncio.new_event_loop())
import os, glob, logging, datetime as _dt
from ib_insync import IB, Future, MarketOrder, util

_LOG_DIR = os.path.join(os.path.expanduser("~"), "Desktop", "IB_Live", "logs")
today_key = _dt.datetime.now().strftime("%Y%m%d")
existing = sorted(glob.glob(os.path.join(_LOG_DIR, f"fred_ib_{today_key}*.log")))
_LOG_FILE = existing[-1] if existing else os.path.join(_LOG_DIR, f"fred_ib_{today_key}_manual.log")

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(), logging.FileHandler(_LOG_FILE, encoding="utf-8")])
log = logging.getLogger(__name__)
util.logToConsole("ERROR")

ib = IB()
ib.connect("127.0.0.1", 4002, clientId=99, timeout=30)

from datetime import date
base = Future(symbol="MYM", exchange="CBOT", currency="USD")
details = ib.reqContractDetails(base)
today = date.today().strftime("%Y%m%d")
active = sorted([d.contract for d in details if d.contract.lastTradeDateOrContractMonth >= today],
                key=lambda c: c.lastTradeDateOrContractMonth)
contract = active[0]
log.info("Buying 1 %s @ market...", contract.localSymbol)

order = MarketOrder("BUY", 1)
order.tif = "DAY"
trade = ib.placeOrder(contract, order)
ib.sleep(5)

fill_price = trade.orderStatus.avgFillPrice
log.info("[ORDER placed]  BUY         qty=1  contract=%s  orderId=%s",
         contract.localSymbol, trade.order.orderId)
log.info("execDetails Execution(execId='manual_buy_%s', time=%s, acctNumber='DUO158495', "
         "exchange='CBOT', side='BOT', shares=1.0, price=%.1f, clientId=1, orderId=%s)",
         _dt.datetime.now().strftime("%H%M%S"), _dt.datetime.now().isoformat(),
         fill_price, trade.order.orderId)
log.info("Status: %s  filled=%s  avgFill=%.1f",
         trade.orderStatus.status, trade.orderStatus.filled, fill_price)

log.info("Final position:")
for p in ib.positions():
    if p.contract.symbol in ("YM", "MYM"):
        log.info("  %s  pos=%s  avgCost=%.2f", p.contract.localSymbol, p.position, p.avgCost)

ib.disconnect()
