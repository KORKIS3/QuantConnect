"""Download recent missing days from IB and save to full_day folder."""
import os, time
import pandas as pd, pytz
from ib_insync import IB, Future

_EST      = pytz.timezone("US/Eastern")
DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")

DATES_TO_FETCH = ["2026-04-21"]

ib = IB()
ib.connect("127.0.0.1", 4002, clientId=99)
print(f"Connected to IB")

base = Future(symbol="YM", exchange="CBOT", currency="USD", includeExpired=True)
all_contracts = sorted([d.contract for d in ib.reqContractDetails(base)],
                       key=lambda c: c.lastTradeDateOrContractMonth)

def front_month_for(date_str):
    for c in all_contracts:
        if c.lastTradeDateOrContractMonth >= date_str.replace("-",""):
            return c
    return all_contracts[-1]

for date_str in DATES_TO_FETCH:
    fname = os.path.join(DATA_ROOT, f"CBOT_MINI_YM1_{date_str}.csv")
    contract = front_month_for(date_str)
    # Always re-download to get latest complete data
    end_utc  = pd.Timestamp(f"{date_str} 23:59:00").tz_localize(_EST).astimezone(pytz.utc).strftime("%Y%m%d-%H:%M:%S")

    print(f"{date_str}: fetching from {contract.localSymbol} ...", end=" ", flush=True)
    try:
        bars = ib.reqHistoricalData(
            contract,
            endDateTime=end_utc,
            durationStr="2 D",
            barSizeSetting="1 min",
            whatToShow="TRADES",
            useRTH=False,
            formatDate=1,
        )
    except Exception as e:
        print(f"ERROR: {e}")
        continue

    if not bars:
        print("no data returned")
        continue

    df = pd.DataFrame([{
        "time": b.date, "Open": b.open, "High": b.high,
        "Low": b.low, "Close": b.close, "Volume": b.volume
    } for b in bars]).set_index("time")
    df.index = pd.to_datetime(df.index)
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC").tz_convert(_EST)
    else:
        df.index = df.index.tz_convert(_EST)

    # Filter to just the requested date
    df = df[df.index.strftime("%Y-%m-%d") == date_str]

    df.to_csv(fname)
    print(f"saved {len(df)} bars → {fname}")
    time.sleep(1)

ib.disconnect()
print("Done.")
