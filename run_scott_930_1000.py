"""
Process ScottDataTry2_3_5 CSV with RunFullDataSet
Time window: 9:30-10:00 AM
Note: This is 30-minute bar data, so there will be limited data points
"""
import pandas as pd
import pytz
import os
import datetime
from plotFigure import ChartPlotter
from RunFullDataSet import _compute_trade_stats

# Load the data
csv_file = os.path.join(os.path.expanduser('~'), 'Desktop', 'ScottDataTry2_3_5 - CBOT_MINI_YM1!, 30.csv')
print("="*60)
print("Loading ScottDataTry2_3_5 CSV")
print("="*60)
print(f"\nFile: {csv_file}")

# Read CSV with time column
df = pd.read_csv(csv_file)
print(f"Loaded {len(df):,} rows")
print(f"Columns: {df.columns.tolist()}")

# Parse the time column
df['time'] = pd.to_datetime(df['time'])
df = df.set_index('time')

# Rename columns to match expected format
df = df.rename(columns={
    'open': 'Open',
    'high': 'High',
    'low': 'Low',
    'close': 'Close'
})

print(f"\nData info:")
print(f"  Date: {df.index[0].date()}")
print(f"  Time range: {df.index[0].strftime('%H:%M')} to {df.index[-1].strftime('%H:%M')}")
print(f"  Interval: 30-minute bars")
print(f"  Total bars: {len(df)}")

# Ensure timezone
est = pytz.timezone('US/Eastern')
if df.index.tz is None:
    df.index = df.index.tz_localize(est, ambiguous='NaT', nonexistent='shift_forward')
else:
    df.index = df.index.tz_convert(est)

# Filter to 9:30-10:00 window
print("\n" + "="*60)
print("Filtering to 9:30-10:00 AM window")
print("="*60)

start_time_obj = datetime.time(9, 30)
end_time_obj = datetime.time(10, 0)
df_window = df[(df.index.time >= start_time_obj) & (df.index.time <= end_time_obj)]

print(f"\nWindow data:")
print(f"  Bars in window: {len(df_window)}")
if not df_window.empty:
    print(f"  Time range: {df_window.index[0].strftime('%Y-%m-%d %H:%M')} to {df_window.index[-1].strftime('%Y-%m-%d %H:%M')}")
    print(f"\n  Data:")
    for idx, row in df_window.iterrows():
        print(f"    {idx.strftime('%Y-%m-%d %H:%M')}: O={row['Open']:.0f} H={row['High']:.0f} L={row['Low']:.0f} C={row['Close']:.0f}")

# Check if we have enough data
if len(df_window) < 1:
    print("\n✗ No data in 9:30-10:00 window!")
    exit(1)

print(f"\n⚠ NOTE: This is 30-minute bar data, so chart will have limited granularity")
print(f"  For better results, use 1-minute data instead")

# Process with ChartPlotter
date_str = df_window.index[0].strftime('%Y-%m-%d')
start_time = "09:30"
end_time = "10:00"

output_dir = os.path.join(os.path.expanduser('~'), 'Desktop', 'Trading', 'Temp')
os.makedirs(output_dir, exist_ok=True)

print("\n" + "="*60)
print("Creating Chart")
print("="*60)

try:
    # Use only High, Low, Close for the plotter
    df_hlc = df_window[['High', 'Low', 'Close']].copy()
    
    plotter = ChartPlotter(df_hlc, date_str, start_time, end_time, output_dir)
    plotter.create_figure()
    plotter.detect_all_signals_once()
    
    # Save image
    image_dir = os.path.join(os.path.expanduser('~'), 'Desktop', 'TradingPics_Scott_930-1000')
    os.makedirs(image_dir, exist_ok=True)
    img_path = os.path.join(image_dir, f"{date_str}_30min.jpg")
    
    if hasattr(plotter, 'fig'):
        final_frame = max(0, len(df_hlc) - 1)
        plotter.state.current_frame = final_frame
        plotter.update_plot(final_frame)
        
        try:
            plotter.fig.canvas.draw()
            plotter.fig.canvas.flush_events()
        except:
            pass
        
        plotter.fig.savefig(img_path, dpi=150, bbox_inches='tight')
        print(f"\n✓ Chart saved: {img_path}")
        
        import matplotlib.pyplot as plt
        plt.close(plotter.fig)
    
    # Collect stats
    stats = _compute_trade_stats(plotter)
    
    print("\n" + "="*60)
    print("TRADING STATISTICS")
    print("="*60)
    print(f"Date: {date_str}")
    print(f"Window: {start_time} - {end_time}")
    print(f"Data Points: {len(df_hlc)} (30-minute bars)")
    print(f"\nSignals:")
    print(f"  Buy Signals: {len(plotter.state.detected_buy_signals)}")
    print(f"  Sell Signals: {len(plotter.state.detected_sell_signals)}")
    print(f"\nTrades:")
    print(f"  Total Trades: {stats['total_trades']}")
    print(f"  Winning Trades: {stats['winning_trades']}")
    print(f"  Losing Trades: {stats['losing_trades']}")
    print(f"  Win %: {stats['win_pct']:.1f}%")
    print(f"\nP/L:")
    print(f"  Final P/L: {stats['final_pl']:.2f} points")
    print(f"  P/L High: {stats['pl_high']:.2f} points")
    print(f"  Captured 100 pts: {stats['captured_100']}")
    if stats.get('liquidation_trade_pl'):
        print(f"  Liquidation P/L: {stats['liquidation_trade_pl']:.2f} points")
    
    print("\n" + "="*60)
    print("✓ Complete!")
    print("="*60)
    
except Exception as e:
    print(f"\n✗ Error: {e}")
    import traceback
    traceback.print_exc()
