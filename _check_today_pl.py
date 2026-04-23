import pandas as pd
import pytz

_EST = pytz.timezone("US/Eastern")
df = pd.read_csv(r"C:\Users\Administrator\Desktop\IB_Live\tracking\YM_tracking_2026-04-22.csv", index_col=0, parse_dates=True)
df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)

last = df.iloc[-1]
trades = df[df["signal"].isin(["BUY", "SELL"])]

print(f"Last bar:  {df.index[-1].strftime('%H:%M')}")
print(f"Total P/L: {last['pl']:.1f} pts  /  ${last['pl']*5:.0f}")
print(f"Position:  {last['position']}")
print(f"Signals:   {len(trades)}")
print()
print("--- Trades ---")
for ts, row in trades.iterrows():
    liq = " (liq)" if row.get("is_liquidation") else ""
    print(f"  {ts.strftime('%H:%M')}  {row['signal']}  @{row['Close']:.0f}  pl={row['pl']:.0f}{liq}")
