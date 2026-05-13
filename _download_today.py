"""Download today's data (May 12, 2026)."""

import os
import logging
from datetime import date
from ib_insync import IB, Future
import pandas as pd
import pytz

logging.basicConfig(level=logging.INFO, format='%(asctime)s  %(levelname)-8s %(message)s', datefmt='%H:%M:%S')

target_date = date(2026, 5, 12)
output_dir = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")
os.makedirs(output_dir, exist_ok=True)

logging.info(f"Target date: {target_date}")
logging.info("Connecting to 127.0.0.1:4002 with clientId 99...")

ib = IB()
ib.connect("127.0.0.1", 4002, clientId=99, timeout=30)

logging.info("Connected to IB at 127.0.0.1:4002")

# YM June 2026 contract
contract = Future(symbol="YM", lastTradeDateOrContractMonth="20260618", exchange="CBOT", currency="USD")
ib.qualifyContracts(contract)

logging.info(f"Contract: {contract.localSymbol}  expiry={contract.lastTradeDateOrContractMonth}")

# Request historical data for today
end_datetime = f"{target_date} 17:00:00 US/Eastern"
logging.info(f"Fetching {target_date} from {contract.localSymbol} ...")

bars = ib.reqHistoricalData(
    contract,
    endDateTime=end_datetime,
    durationStr="1 D",
    barSizeSetting="1 min",
    whatToShow="TRADES",
    useRTH=False,
    formatDate=1
)

if bars:
    df = pd.DataFrame([{
        "time": b.date,
        "Open": b.open,
        "High": b.high,
        "Low": b.low,
        "Close": b.close,
        "Volume": b.volume
    } for b in bars])
    
    df["time"] = pd.to_datetime(df["time"])
    df = df.set_index("time")
    
    # Convert to ET
    est = pytz.timezone("US/Eastern")
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC").tz_convert(est)
    else:
        df.index = df.index.tz_convert(est)
    
    output_path = os.path.join(output_dir, f"CBOT_MINI_YM1_{target_date}.csv")
    df.to_csv(output_path)
    logging.info(f"Saved {len(df)} bars → {output_path}")
else:
    logging.error("No data received")

ib.disconnect()
logging.info("Disconnected from IB")
logging.info(f"Done — {target_date} downloaded successfully")
