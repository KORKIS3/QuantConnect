"""
Run Main.py with 1_1.csv data from desktop
"""
import os
import pandas as pd
import pytz

# Read the 1_1.csv from desktop
desktop_file = os.path.join(os.path.expanduser('~'), 'Desktop', '1_1.csv')
print(f"Reading {desktop_file}...")

df = pd.read_csv(desktop_file, parse_dates=['Timestamp'])
df = df.set_index('Timestamp')

print(f"Loaded {len(df)} rows")
print(f"Time range: {df.index[0]} to {df.index[-1]}")

# The data is from Jan 1, 2026, 23:01 to 23:59
# Set up parameters for Main.py
target_date = "2026-01-01"
start_time = "23:01"
end_time = "23:59"

# Create the expected filename format for Main.py
target_csv = f"YM_intraday_{target_date}_{start_time.replace(':', '')}-{end_time.replace(':', '')}.csv"

# Ensure index is timezone-aware
est = pytz.timezone('US/Eastern')
if df.index.tz is None:
    df.index = df.index.tz_localize(est)

print(f"\nSaving to: {target_csv}")
df.to_csv(target_csv)
print(f"✓ Saved")

print(f"\nFirst 5 rows:")
print(df.head())

# Now run Main.py with the data
print("\n" + "="*60)
print("Running Main.py with 1_1.csv data...")
print("="*60)

from data_extraction import get_ym_intraday
from plotFigure import plot_intraday_data

# Get data using the CSV
data = get_ym_intraday(target_date=target_date, start_time=start_time, end_time=end_time, use_csv=True)

if data is not None and not data.empty:
    print("\n✓ Data loaded successfully")
    plot_intraday_data(data, target_date, start_time, end_time)
    print("\n" + "="*60)
    print("✓ Completed successfully!")
    print("="*60)
else:
    print("\n✗ Failed to load data")
