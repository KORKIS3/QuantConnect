from ib_insync import IB, Future
import pandas as pd, pytz

est = pytz.timezone("US/Eastern")
ib = IB()
ib.connect("127.0.0.1", 4001, clientId=21)
contract = Future(symbol="YM", exchange="CBOT", currency="USD")
contract = ib.reqContractDetails(contract)[0].contract
print(f"Contract: {contract.localSymbol}")

d = "2026-04-07"
end_ts = pd.Timestamp(f"{d} 10:35:00").tz_localize(est).astimezone(pytz.utc)

formats = [
    end_ts.strftime("%Y%m%d-%H:%M:%S"),
    end_ts.strftime("%Y%m%d %H:%M:%S"),
    f"{d} 10:35:00 US/Eastern",
    "20260407 14:35:00",
]

for fmt in formats:
    print(f"\nTrying: {fmt!r}")
    try:
        bars = ib.reqHistoricalData(contract, endDateTime=fmt,
            durationStr="4200 S", barSizeSetting="1 min",
            whatToShow="TRADES", useRTH=False, formatDate=1)
        print(f"  Got {len(bars)} bars")
        if bars:
            df = pd.DataFrame([{"time": b.date} for b in bars])
            df["time"] = pd.to_datetime(df["time"])
            if df["time"].dt.tz is None:
                df["time"] = df["time"].dt.tz_localize("UTC").dt.tz_convert(est)
            else:
                df["time"] = df["time"].dt.tz_convert(est)
            print(f"  First: {df['time'].iloc[0]}")
            print(f"  Last:  {df['time'].iloc[-1]}")
    except Exception as e:
        print(f"  ERROR: {e}")

ib.disconnect()
