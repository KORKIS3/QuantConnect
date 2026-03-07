"""
Extract the first day of data from split time.xlsx and save to desktop
"""
import pandas as pd
import pytz
import os

# Configuration
excel_file = "split time.xlsx"
output_csv = os.path.join(os.path.expanduser('~'), 'Desktop', '1_1.csv')

print(f"Reading {excel_file}...")
df = pd.read_excel(excel_file)

# Clean column names
df.columns = df.columns.str.strip()

# Drop rows with missing Date, Hour, or Min
df = df.dropna(subset=['Date', 'Hour', 'Min'])

# Get the first date in the data
first_date = df['Date'].min()
print(f"\nFirst date in data: {first_date}")

# Filter for first date
df_day = df[df['Date'] == first_date].copy()
print(f"Found {len(df_day)} rows for date {first_date}")

# Create datetime column
df_day['DateTime'] = pd.to_datetime(
    df_day['Date'].astype('Int64').astype(str).str.zfill(8) + ' ' + 
    df_day['Hour'].astype('Int64').astype(str).str.zfill(2) + ':' + 
    df_day['Min'].astype('Int64').astype(str).str.zfill(2), 
    format='%Y%m%d %H:%M',
    errors='coerce'
)

# Drop rows where datetime parsing failed
df_day = df_day.dropna(subset=['DateTime'])

# Remove duplicates
print(f"Before deduplication: {len(df_day)} rows")
df_day = df_day.drop_duplicates(subset=['DateTime'], keep='first')
print(f"After deduplication: {len(df_day)} rows")

# Convert to EST timezone
est = pytz.timezone('US/Eastern')
df_day['DateTime'] = df_day['DateTime'].dt.tz_localize(est, ambiguous='NaT', nonexistent='shift_forward')

# Select only relevant columns (High, Low, Close - no Open)
output_df = df_day[['DateTime', 'High', 'Low', 'Close']].copy()
output_df = output_df.rename(columns={'DateTime': 'Timestamp'})

# Sort by timestamp
output_df = output_df.sort_values('Timestamp')

# Save to CSV on desktop
output_df.to_csv(output_csv, index=False)
print(f"\n✓ Saved {len(output_df)} rows to {output_csv}")

# Display sample
print(f"\nFirst 10 rows:")
print(output_df.head(10))

print(f"\nLast 10 rows:")
print(output_df.tail(10))

# Display date info
date_str = pd.Timestamp(str(first_date)).strftime('%Y-%m-%d')
print(f"\n✓ CSV file created on desktop: 1_1.csv")
print(f"  Date: {date_str}")
print(f"  Total rows: {len(output_df)}")
print(f"  Time range: {output_df['Timestamp'].iloc[0]} to {output_df['Timestamp'].iloc[-1]}")
