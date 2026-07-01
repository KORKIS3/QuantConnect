"""Check 11:00 snapshot state for July 1 - algo vs IB view."""
import pandas as pd, os, pytz
_EST = pytz.timezone("US/Eastern")
live = pd.read_csv(os.path.join(os.path.expanduser("~"), "Desktop", "IB_Live", "tracking",
                   "YM_tracking_DUO158495_2026-07-01_0930.csv"), index_col=0, parse_dates=True)

cutoff = "2026-07-01 11:00:00-04:00"
sliced = live[live.index <= cutoff]
last = sliced.iloc[-1]

print("=== 11:00 AM Snapshot State (July 1) ===")
print(f"Bars: {len(sliced)}")
print(f"Close: {last['Close']}")
print()
print("--- ALGO VIEW ---")
print(f"  Position: {last['position']}")
print(f"  Session P/L: {last['session_pl']}")
sigs = sliced[(sliced["signal"].notna()) & (sliced["signal"] != "")]
n_buys = len(sigs[sigs["signal"].str.upper() == "BUY"])
n_sells = len(sigs[sigs["signal"].str.upper() == "SELL"])
print(f"  Signals: {len(sigs)} ({n_buys}B {n_sells}S)")
print()
print("--- IB VIEW ---")
print(f"  IB Position: {last.get('ib_position', 'n/a')}")
print(f"  IB Session P/L: {last.get('ib_session_pl', 'n/a')}")
print(f"  IB Realized: {last.get('ib_realized_pl', 'n/a')}")
print(f"  IB Unrealized: {last.get('ib_unrealized_pl', 'n/a')}")
print(f"  IB Total (ib_pl): {last.get('ib_pl', 'n/a')}")
ib_sigs = sliced[(sliced["ib_signal"].notna()) & (sliced["ib_signal"] != "") & (sliced["ib_signal"] != "flat")]
print(f"  IB Signals: {len(ib_sigs)}")
print()

print("--- ALGO TRADES ---")
for idx, row in sigs.iterrows():
    sig = str(row["signal"]).upper()
    if sig == "SELL":
        price = row.get("sell_price", row["Close"])
    else:
        price = row["Close"]
    if pd.isna(price):
        price = row["Close"]
    print(f"  {idx}  {sig:<6} @ {float(price):.0f}  pl={row['session_pl']:.0f}")

print()
print("--- IB TRADES ---")
for idx, row in ib_sigs.iterrows():
    sig = row["ib_signal"]
    if sig == "BUY":
        p = row.get("ib_buy_price", row["Close"])
    else:
        p = row.get("ib_sell_price", row["Close"])
    if pd.isna(p):
        p = row["Close"]
    print(f"  {idx}  {sig:<6} @ {float(p):.0f}  ib_pl={row['ib_session_pl']:.0f}")

print()
print("--- GAP ---")
algo_pl = float(last["session_pl"])
ib_pl = float(last.get("ib_session_pl", 0))
print(f"  Algo P/L at 11:00: {algo_pl:+.0f}")
print(f"  IB P/L at 11:00:   {ib_pl:+.0f}")
print(f"  Difference:        {algo_pl - ib_pl:+.0f}")
