import pandas as pd, pytz
from ib_insync import IB, Future
from TradingAlgo import run_trading_algo, AlgoConfig

est = pytz.timezone("US/Eastern")
TARGET = "2026-02-23"

ib = IB()
ib.connect("127.0.0.1", 4001, clientId=23)

base = Future(symbol="YM", exchange="CBOT", currency="USD", includeExpired=True)
all_contracts = sorted(
    [d.contract for d in ib.reqContractDetails(base)],
    key=lambda c: c.lastTradeDateOrContractMonth
)
target_ts = pd.Timestamp(f"{TARGET} 09:30", tz=est)
contract = None
for c in all_contracts:
    exp_ts = pd.Timestamp(c.lastTradeDateOrContractMonth, tz=est)
    days_to_expiry = (exp_ts - target_ts).days
    if days_to_expiry < 0:
        continue  # already expired
    if days_to_expiry < 7:
        continue  # within 1 week — skip, use next
    contract = c
    break
if contract is None:
    contract = all_contracts[-1]
print(f"Contract: {contract.localSymbol}")

end_ts = pd.Timestamp(f"{TARGET} 10:35:00").tz_localize(est).astimezone(pytz.utc)
bars = ib.reqHistoricalData(contract, endDateTime=end_ts.strftime("%Y%m%d-%H:%M:%S"),
    durationStr="4200 S", barSizeSetting="1 min", whatToShow="TRADES", useRTH=False, formatDate=1)
ib.disconnect()

df = pd.DataFrame([{"time": b.date, "Open": b.open, "High": b.high,
                     "Low": b.low, "Close": b.close, "Volume": b.volume}
                    for b in bars]).set_index("time")
df.index = pd.to_datetime(df.index)
if df.index.tz is None:
    df.index = df.index.tz_localize("UTC").tz_convert(est)
else:
    df.index = df.index.tz_convert(est)
df = df[(df.index >= pd.Timestamp(f"{TARGET} 09:30", tz=est)) &
        (df.index <= pd.Timestamp(f"{TARGET} 10:30", tz=est))]

config = AlgoConfig(warmup_minutes=12, steep_angle_threshold=70.0,
                    proximity_points=15.0, min_reversal_minutes=10)
algo_df = run_trading_algo(df, TARGET, "09:30", "10:30", config=config)

signals = algo_df[algo_df["signal"].isin(["BUY","SELL"])]
print(f"\nALGO signals for {TARGET}:")
for ts, row in signals.iterrows():
    sig   = row["signal"]
    price = float(row["buy_price"] if sig == "BUY" else row["sell_price"])
    pl    = float(row["pl"])
    print(f"  {ts.strftime('%H:%M')}  {sig:4s}  @ {int(price)}   P/L: {pl:+.0f}")
print(f"Final P/L: {float(algo_df['pl'].iloc[-1]):+.0f} pts")

print(f"\nYOUR sim trades: (type them in)")
