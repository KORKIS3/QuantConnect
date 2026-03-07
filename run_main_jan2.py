"""
Extract Jan 2, 2026 data and run Main.py
"""
import pandas as pd
import pytz
import os
import datetime

# Load parsed data
csv_file = os.path.join(os.path.expanduser('~'), 'Desktop', 'YM_1m_Jan26_parsed.csv')
print(f"Loading {csv_file}...")

df = pd.read_csv(csv_file, parse_dates=['Timestamp'])
df = df.set_index('Timestamp')

# Ensure EST timezone
est = pytz.timezone('US/Eastern')
if df.index.tz is None:
    df.index = df.index.tz_localize(est)
else:
    df.index = df.index.tz_convert(est)

# Filter for January 2, 2026
target_date_obj = datetime.date(2026, 1, 2)
df_jan2 = df[df.index.date == target_date_obj]

print(f"Found {len(df_jan2)} rows for 2026-01-02")

# Filter to 10:00-11:00 window
start_time_obj = datetime.time(10, 0)
end_time_obj = datetime.time(11, 0)
df_window = df_jan2[(df_jan2.index.time >= start_time_obj) & (df_jan2.index.time <= end_time_obj)]

print(f"10:00-11:00 window: {len(df_window)} rows")
print(f"Time range: {df_window.index[0]} to {df_window.index[-1]}")

# Save in Main.py expected format
target_date = "2026-01-02"
start_time = "10:00"
end_time = "11:00"
output_csv = f"YM_intraday_{target_date}_{start_time.replace(':', '')}-{end_time.replace(':', '')}.csv"

df_window.to_csv(output_csv)
print(f"\nSaved to: {output_csv}")

print("\nFirst 5 rows:")
print(df_window.head())

# Now run Main.py
print("\n" + "="*60)
print("Running Main.py...")
print("="*60)

from data_extraction import get_ym_intraday
from plotFigure import plot_intraday_data

# Load data using Main.py's data loader
data = get_ym_intraday(target_date=target_date, start_time=start_time, end_time=end_time, use_csv=True)

if data is not None and not data.empty:
    print("\nData loaded successfully, generating interactive plot...")
    plot_intraday_data(data, target_date, start_time, end_time)
    print("\n" + "="*60)
    print("✓ Main.py completed successfully!")
    print("="*60)
else:
    print("\n✗ Failed to load data in Main.py")
