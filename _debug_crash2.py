import pandas as pd, os, pytz
EST = pytz.timezone("US/Eastern")
DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")
fname = "CBOT_MINI_YM1_2023-10-31.csv"
df = pd.read_csv(os.path.join(DATA_ROOT, fname), index_col=0, parse_dates=True)
df.index = pd.to_datetime(df.index, utc=True).tz_convert(EST)
day_start = pd.Timestamp("2023-10-31 09:30", tz=EST)
day_end = pd.Timestamp("2023-10-31 16:59", tz=EST)
day_data = df[(df.index >= day_start) & (df.index <= day_end)]
print(f"High max: {day_data['High'].max()}, Low min: {day_data['Low'].min()}")
print(f"Range: {day_data['High'].max() - day_data['Low'].min()}")
print(f"Total volume: {day_data['Volume'].sum()}")
print(f"Bars with volume > 0: {(day_data['Volume'] > 0).sum()} / {len(day_data)}")
