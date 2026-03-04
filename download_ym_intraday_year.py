import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import os

# Settings
ticker = 'YM=F'  # Dow Futures (change as needed)
today = datetime.now()
# Get last 30 business days (excluding today if not a business day)
all_days = pd.bdate_range(end=today, periods=30)
output_dir = os.path.expanduser('~/Desktop')
output_file = os.path.join(output_dir, f'YM_intraday_last30_0930-1000.csv')

all_data = []
for day in all_days:
    day_str = day.strftime('%Y-%m-%d')
    # Download 1-minute data for this day
    df = yf.download(ticker, start=day_str, end=(day + timedelta(days=1)).strftime('%Y-%m-%d'), interval='1m', progress=False)
    if df.empty:
        continue
    # Filter for 9:30 to 10:00 AM (US/Eastern)
    df = df.between_time('09:30', '10:00')
    df['Date'] = day_str
    all_data.append(df)

if all_data:
    result = pd.concat(all_data)
    result.to_csv(output_file)
    print(f"Saved {len(result)} rows to {output_file}")
else:
    print("No data downloaded for the last 30 business days.")
