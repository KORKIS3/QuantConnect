import pandas as pd
import pytz
from datetime import date

_EST = pytz.timezone("US/Eastern")
today = date.today().strftime("%Y-%m-%d")

path = f"C:\\Users\\Administrator\\Desktop\\IB_Live\\tracking\\YM_tracking_{today}.csv"
try:
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)

    # Day session only (9:30-17:00)
    day = df[(df.index.hour >= 9) & (df.index.hour < 17)]
    day = day[day.index >= pd.Timestamp(f"{today} 09:30", tz=_EST)]

    if not day.empty:
        last = day.iloc[-1]
        trades = day[day["signal"].isin(["BUY", "SELL"])]
        print(f"=== DAY SESSION {today} ===")
        print(f"Last bar:  {day.index[-1].strftime('%H:%M')}")
        print(f"Total P/L: {last['pl']:.1f} pts  /  ${last['pl']*5:.0f}")
        print(f"Position:  {last['position']}")
        print(f"Signals:   {len(trades)}")
        print()
        for ts, row in trades.iterrows():
            liq = " (liq)" if row.get("is_liquidation") else ""
            print(f"  {ts.strftime('%H:%M')}  {row['signal']}  @{row['Close']:.0f}  pl={row['pl']:.0f}{liq}")
    else:
        print("No day session data found")
except Exception as e:
    print(f"Error: {e}")
