"""Debug the 2023-10-31 crash."""
import pandas as pd, os, pytz
EST = pytz.timezone("US/Eastern")
fpath = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day", "CBOT_MINI_YM1_2023-10-31.csv")
df = pd.read_csv(fpath, index_col=0, parse_dates=True)
df.index = pd.to_datetime(df.index, utc=True).tz_convert(EST)
day_start = pd.Timestamp("2023-10-31 09:30", tz=EST)
day_end = pd.Timestamp("2023-10-31 16:59", tz=EST)
day_data = df[(df.index >= day_start) & (df.index <= day_end)]
print(f"Day bars: {len(day_data)}")
print(f"Volume zeros: {(day_data['Volume']==0).sum()}")
print(f"Any zero OHLC: {(day_data[['Open','High','Low','Close']] == 0).any().any()}")
print(f"Min values: Open={day_data['Open'].min()}, High={day_data['High'].min()}, Low={day_data['Low'].min()}, Close={day_data['Close'].min()}")
print(f"Max values: Open={day_data['Open'].max()}, High={day_data['High'].max()}, Low={day_data['Low'].max()}, Close={day_data['Close'].max()}")
print(f"\nFirst 5 bars:")
print(day_data.head())
print(f"\nLast 5 bars:")
print(day_data.tail())

# Check if it's the number of bars that's the issue
# 2023-10-31 has 1054 total bars, 450 day bars
# Compare with a working file that also has many bars
fpath2 = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day", "CBOT_MINI_YM1_2023-10-30.csv")
df2 = pd.read_csv(fpath2, index_col=0, parse_dates=True)
print(f"\n2023-10-30 total bars: {len(df2)}")
print(f"2023-10-31 total bars: {len(df)}")
