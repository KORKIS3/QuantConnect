"""Download today's full day data from IB and save to 2YearsData/full_day."""
import asyncio
asyncio.set_event_loop(asyncio.new_event_loop())
import os, pandas as pd, pytz
from datetime import date
from ib_insync import IB, Future, util

util.logToConsole()
_EST = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")

ib = IB()
ib.connect("127.0.0.1", 4002, clientId=50, timeout=30)

today = date.today()
today_str = today.strftime("%Y-%m-%d")
fname = os.path.join(_DATA_ROOT, f"CBOT_MINI_YM1_{today_str}.csv")

# Resolve front month
base = Future(symbol="MYM", exchange="CBOT", currency="USD")
details = ib.reqContractDetails(base)
active = sorted([d.contract for d in details if d.contract.lastTradeDateOrContractMonth >= today.strftime("%Y%m%d")],
                key=lambda c: c.lastTradeDateOrContractMonth)
contract = active[0]
print(f"Contract: {contract.localSymbol}")

end_utc = pd.Timestamp(f"{today_str} 17:00:00").tz_localize(_EST).astimezone(pytz.utc).strftime("%Y%m%d-%H:%M:%S")
bars = ib.reqHistoricalData(contract, endDateTime=end_utc, durationStr="1 D",
    barSizeSetting="1 min", whatToShow="TRADES", useRTH=False, formatDate=1)

if bars:
    df = pd.DataFrame([{"time": b.date, "Open": b.open, "High": b.high,
                        "Low": b.low, "Close": b.close, "Volume": b.volume} for b in bars])
    df = df.set_index("time")
    df.index = pd.to_datetime(df.index)
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC").tz_convert(_EST)
    else:
        df.index = df.index.tz_convert(_EST)
    df.to_csv(fname)
    print(f"Saved {len(df)} bars to {fname}")
else:
    print("No bars returned")

ib.disconnect()
