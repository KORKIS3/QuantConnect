import pandas as pd, pytz, numpy as np
_EST = pytz.timezone("US/Eastern")

df = pd.read_csv(r"C:\Users\Administrator\Desktop\IB_Live\tracking\YM_tracking_2026-04-21.csv",
                 index_col=0, parse_dates=True)
df.index = pd.to_datetime(df.index, utc=False)
if df.index.tz is None:
    df.index = df.index.tz_localize(_EST)
else:
    df.index = df.index.tz_convert(_EST)

signals = df[df["signal"].isin(["BUY","SELL"])]
final_pl = float(df["pl"].iloc[-1])
max_pl   = float(df["pl"].max())
min_pl   = float(df["pl"].min())

print(f"=== TODAY'S SESSION  2026-04-21 ===")
print(f"Session:    {df.index[0].strftime('%H:%M')} - {df.index[-1].strftime('%H:%M')} ET")
print(f"Bars:       {len(df)}")
print(f"Signals:    {len(signals)}")
print(f"Final P/L:  {final_pl:+.1f} pts  /  ${final_pl*5*2:+,.0f}  (2 contracts)")
print(f"Peak P/L:   {max_pl:+.1f} pts")
print(f"Trough P/L: {min_pl:+.1f} pts")
print()

# Trade breakdown
buys  = signals[signals["signal"] == "BUY"]
sells = signals[signals["signal"] == "SELL"]
liqs  = signals[signals["is_liquidation"] == True]
print(f"BUY signals:  {len(buys)}  (of which {len(liqs[liqs['signal']=='BUY'])} liquidations)")
print(f"SELL signals: {len(sells)}  (of which {len(liqs[liqs['signal']=='SELL'])} liquidations)")
print()

print("Signal detail:")
for ts, row in signals.iterrows():
    sig   = row["signal"]
    price = row["buy_price"] if sig == "BUY" else row["sell_price"]
    liq   = " [LIQ]" if row["is_liquidation"] else ""
    pos   = row["position"]
    print(f"  {ts.strftime('%H:%M')}  {sig:4s} @ {int(price)}   P/L: {row['pl']:+.1f} pts  pos={pos}{liq}")

print()
# Hourly P/L breakdown
print("Hourly P/L:")
for hour in range(9, 18):
    hour_bars = df[(df.index.hour == hour)]
    if hour_bars.empty: continue
    start_pl = float(df[df.index < hour_bars.index[0]]["pl"].iloc[-1]) if len(df[df.index < hour_bars.index[0]]) > 0 else 0.0
    end_pl   = float(hour_bars["pl"].iloc[-1])
    hour_gain = end_pl - start_pl
    print(f"  {hour:02d}:00-{hour+1:02d}:00  {hour_gain:+.1f} pts")
