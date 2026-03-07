"""
Ensure YM_Jan26_HLC.csv is properly in Eastern timezone and save as UpdatedJanData
"""
import pandas as pd
import pytz
import os

# Load the data
input_csv = os.path.join(os.path.expanduser('~'), 'Desktop', 'YM_Jan26_HLC.csv')
output_csv = os.path.join(os.path.expanduser('~'), 'Desktop', 'UpdatedJanData.csv')

print("="*60)
print("Converting to Eastern Timezone")
print("="*60)
print(f"\nReading: {input_csv}")

df = pd.read_csv(input_csv, parse_dates=['Timestamp'])

print(f"Loaded {len(df):,} rows")
print(f"\nOriginal timezone info:")
print(f"  First timestamp: {df['Timestamp'].iloc[0]}")
print(f"  Last timestamp: {df['Timestamp'].iloc[-1]}")

# Ensure proper Eastern timezone
est = pytz.timezone('US/Eastern')

# Check current timezone status
if df['Timestamp'].dt.tz is None:
    print("\nNo timezone detected, localizing to EST...")
    df['Timestamp'] = pd.to_datetime(df['Timestamp']).dt.tz_localize(est, ambiguous='NaT', nonexistent='shift_forward')
else:
    current_tz = str(df['Timestamp'].dt.tz)
    print(f"\nCurrent timezone: {current_tz}")
    print("Converting to EST...")
    df['Timestamp'] = pd.to_datetime(df['Timestamp']).dt.tz_convert(est)

print(f"\nAfter Eastern conversion:")
print(f"  First timestamp: {df['Timestamp'].iloc[0]}")
print(f"  Last timestamp: {df['Timestamp'].iloc[-1]}")

# Sort by timestamp
df = df.sort_values('Timestamp')

# Verify no duplicates
before_dedup = len(df)
df = df.drop_duplicates(subset=['Timestamp'], keep='first')
after_dedup = len(df)
if before_dedup != after_dedup:
    print(f"\nRemoved {before_dedup - after_dedup} duplicate(s)")

# Save to desktop
df.to_csv(output_csv, index=False)

print("\n" + "="*60)
print("VERIFICATION - Sample Data")
print("="*60)

# Show morning trading hours (9:30-10:00)
print("\nMorning trading hours (09:30-10:00):")
df['Time'] = pd.to_datetime(df['Timestamp']).dt.time
morning_trades = df[(df['Time'] >= pd.Timestamp('09:30:00').time()) & 
                    (df['Time'] <= pd.Timestamp('10:00:00').time())]

# Get first trading day with morning data
if not morning_trades.empty:
    first_trading_day = morning_trades.iloc[0]['Timestamp'].date()
    day_morning = morning_trades[pd.to_datetime(morning_trades['Timestamp']).dt.date == first_trading_day].head(10)
    
    for idx, row in day_morning.iterrows():
        ts = row['Timestamp']
        print(f"  {ts.strftime('%Y-%m-%d %H:%M:%S')} EST -> H:{row['High']:.0f} L:{row['Low']:.0f} C:{row['Close']:.0f}")
else:
    print("  (No 9:30-10:00 data found)")

# Show 10:00-11:00 sample
print("\nPrimary window (10:00-11:00):")
primary_trades = df[(df['Time'] >= pd.Timestamp('10:00:00').time()) & 
                     (df['Time'] <= pd.Timestamp('11:00:00').time())]
if not primary_trades.empty:
    first_day_10am = primary_trades.iloc[0]['Timestamp'].date()
    day_10am = primary_trades[pd.to_datetime(primary_trades['Timestamp']).dt.date == first_day_10am].head(10)
    
    for idx, row in day_10am.iterrows():
        ts = row['Timestamp']
        print(f"  {ts.strftime('%Y-%m-%d %H:%M:%S')} EST -> H:{row['High']:.0f} L:{row['Low']:.0f} C:{row['Close']:.0f}")

print("\n" + "="*60)
print("SUMMARY")
print("="*60)
print(f"Total rows: {len(df):,}")
print(f"Timezone: US/Eastern (EST)")
print(f"Date range: {df['Timestamp'].iloc[0].strftime('%Y-%m-%d')} to {df['Timestamp'].iloc[-1].strftime('%Y-%m-%d')}")
print(f"Columns: {df.drop('Time', axis=1).columns.tolist()}")
print(f"\n✓ File saved: {output_csv}")
print("="*60)
