"""
Run RunFullDataSet with split time.xlsx data for 10:00 AM - 11:00 AM
"""
import pandas as pd
import pytz
import os
from plotFigure import ChartPlotter

# Load Excel data
excel_file = "split time.xlsx"
est = pytz.timezone('US/Eastern')

print(f"Loading {excel_file}...")
df = pd.read_excel(excel_file)
df.columns = df.columns.str.strip()
df = df.dropna(subset=['Date', 'Hour', 'Min'])

# Create datetime
df['Date'] = df['Date'].astype('Int64').astype(str).str.zfill(8)
df['Hour'] = df['Hour'].astype('Int64').astype(str).str.zfill(2)
df['Min'] = df['Min'].astype('Int64').astype(str).str.zfill(2)

df['datetime'] = pd.to_datetime(
    df['Date'] + ' ' + df['Hour'] + ':' + df['Min'], 
    format='%Y%m%d %H:%M',
    errors='coerce'
)

df = df.dropna(subset=['datetime'])
df = df.drop_duplicates(subset=['datetime'], keep='first')

# Set as index and localize to EST
df = df.set_index('datetime')
df.index = df.index.tz_localize(est, ambiguous='NaT', nonexistent='shift_forward')

# Keep only High, Low, Close
df = df[['High', 'Low', 'Close']].copy()
for col in df.columns:
    df[col] = pd.to_numeric(df[col], errors='coerce')
df = df[df.index.notna()]

print(f"Loaded {len(df)} total rows")

# Group by date
df['date'] = df.index.date
dates = sorted(df['date'].unique())
print(f"Found {len(dates)} trading days\n")

# Process each day with 10:00-11:00 window
output_dir = os.path.join(os.path.expanduser('~'), 'Desktop', 'Trading', 'Temp')
os.makedirs(output_dir, exist_ok=True)

import datetime
start_time = "10:00"
end_time = "11:00"

for date in dates:  # Process ALL days
    date_str = date.strftime('%Y-%m-%d')
    print(f"\n{'='*60}")
    print(f"Processing: {date_str}")
    
    # Filter data for this date
    df_day = df[df['date'] == date].copy()
    df_day = df_day.drop('date', axis=1)
    
    # Filter to 10:00-11:00 window
    chart_start = datetime.time(10, 0)
    chart_end = datetime.time(11, 0)
    df_window = df_day[(df_day.index.time >= chart_start) & (df_day.index.time <= chart_end)]
    
    if len(df_window) < 10:
        print(f"  Skipped: only {len(df_window)} minutes of data")
        continue
    
    print(f"  Window: {len(df_window)} minutes from {df_window.index[0].strftime('%H:%M')} to {df_window.index[-1].strftime('%H:%M')}")
    
    # Create chart
    try:
        plotter = ChartPlotter(df_window, date_str, start_time, end_time, output_dir)
        plotter.create_figure()
        plotter.detect_all_signals_once()
        
        # Save image
        image_dir = os.path.join(os.path.expanduser('~'), 'Desktop', 'TradingPics_10-11')
        os.makedirs(image_dir, exist_ok=True)
        img_path = os.path.join(image_dir, f"{date_str}.jpg")
        
        if hasattr(plotter, 'fig'):
            final_frame = max(0, len(df_window) - 1)
            plotter.state.current_frame = final_frame
            plotter.update_plot(final_frame)
            plotter.fig.savefig(img_path, dpi=150, bbox_inches='tight')
            print(f"  ✓ Saved: {img_path}")
            
            import matplotlib.pyplot as plt
            plt.close(plotter.fig)
    except Exception as e:
        print(f"  ✗ Error: {e}")

print(f"\n{'='*60}")
print("✓ Complete! Charts saved to Desktop/TradingPics_10-11/")
print(f"{'='*60}")
