import pandas as pd, pytz, os
_EST = pytz.timezone("US/Eastern")
df = pd.read_csv(os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day", "CBOT_MINI_YM1_2026-02-23.csv"), index_col=0, parse_dates=True)
df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
dd = df[(df.index >= pd.Timestamp("2026-02-23 09:30", tz=_EST)) & (df.index <= pd.Timestamp("2026-02-23 09:45", tz=_EST))]
for ts, row in dd.iterrows():
    t = ts.strftime("%H:%M")
    print(f"  {t}  O={row['Open']:.0f}  H={row['High']:.0f}  L={row['Low']:.0f}  C={row['Close']:.0f}")
running_high = float("-inf")
print("\nRunning session high:")
for ts, row in dd.iterrows():
    h = row["High"]
    new = ""
    if h > running_high:
        running_high = h
        new = " <-- NEW HIGH"
    print(f"  {ts.strftime('%H:%M')}  High={h:.0f}  SessionHigh={running_high:.0f}{new}")
