"""
Yahoo Finance Data Retrieval for YM (Micro E-mini Dow)
"""

import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.animation import FuncAnimation
from matplotlib.widgets import Button
import time
import numpy as np

def get_ym_data(period="1mo", interval="1d"):
    """
    Fetch data for YM (Micro E-mini Dow) from Yahoo Finance
    
    Parameters:
    - period: Data period (1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max)
    - interval: Data interval (1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo, 3mo)
    
    Returns:
    - DataFrame with OHLCV data
    """
    
    print("="*60)
    print("Fetching YM Data from Yahoo Finance")
    print("="*60)
    
    # YM ticker symbol for Yahoo Finance
    ticker = "YM=F"  # YM futures
    
    try:
        # Create ticker object
        ym = yf.Ticker(ticker)
        
        # Get historical data
        print(f"\nTicker: {ticker}")
        print(f"Period: {period}")
        print(f"Interval: {interval}")
        print("\nFetching data...")
        
        data = ym.history(period=period, interval=interval)
        
        if data.empty:
            print("\n⚠ No data returned. Trying alternative ticker...")
            # Try alternative ticker
            ticker = "YM"
            ym = yf.Ticker(ticker)
            data = ym.history(period=period, interval=interval)
        
        if not data.empty:
            print(f"\n✓ Successfully retrieved {len(data)} data points")
            print(f"\nDate Range: {data.index[0]} to {data.index[-1]}")
            print("\n" + "="*60)
            print("Latest Data:")
            print("="*60)
            print(data.tail(10))
            
            print("\n" + "="*60)
            print("Summary Statistics:")
            print("="*60)
            print(data.describe())
            
            # Save to CSV
            filename = f"YM_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            data.to_csv(filename)
            print(f"\n✓ Data saved to: {filename}")
            
            return data
        else:
            print("\n✗ No data available for YM")
            print("Note: YM futures data may not be available on Yahoo Finance")
            print("Try using 'YMH26.CBT' for specific contract months or '^DJI' for Dow Jones Index")
            return None
            
    except Exception as e:
        print(f"\n✗ Error fetching data: {str(e)}")
        return None


def get_ticker_info(ticker="YM=F"):
    """Get detailed information about the ticker"""
    try:
        print("\n" + "="*60)
        print("Ticker Information:")
        print("="*60)
        
        ym = yf.Ticker(ticker)
        info = ym.info
        
        if info:
            print(f"Symbol: {info.get('symbol', 'N/A')}")
            print(f"Name: {info.get('longName', info.get('shortName', 'N/A'))}")
            print(f"Exchange: {info.get('exchange', 'N/A')}")
            print(f"Quote Type: {info.get('quoteType', 'N/A')}")
            print(f"Currency: {info.get('currency', 'N/A')}")
        else:
            print("No ticker information available")
            
    except Exception as e:
        print(f"Could not retrieve ticker info: {str(e)}")


def get_ym_intraday(target_date="2026-01-14", start_time="09:30", end_time="10:00"):
    """
    Fetch intraday YM data for a specific date and time range
    
    Parameters:
    - target_date: Date in YYYY-MM-DD format
    - start_time: Start time in HH:MM format (EST)
    - end_time: End time in HH:MM format (EST)
    """
    
    print("="*60)
    print("Fetching Intraday YM Data from Yahoo Finance")
    print("="*60)
    
    ticker = "YM=F"
    
    try:
        ym = yf.Ticker(ticker)
        
        # For intraday data, we need to fetch a wider range and then filter
        # Yahoo Finance allows intraday data for last 7 days with 1m interval
        print(f"\nTicker: {ticker}")
        print(f"Target Date: {target_date}")
        print(f"Time Range: {start_time} - {end_time} EST")
        print("\nFetching intraday data...")
        
        # Fetch 1-minute interval data for the last 7 days
        data = ym.history(period="7d", interval="1m")
        
        if data.empty:
            print("\n✗ No intraday data available")
            return None
        
        # Convert target date and times to datetime objects with EST timezone
        import pytz
        est = pytz.timezone('US/Eastern')
        
        # Create start and end datetime for filtering
        target_start = pd.Timestamp(f"{target_date} {start_time}:00", tz=est)
        target_end = pd.Timestamp(f"{target_date} {end_time}:00", tz=est)
        
        # Filter data for the specific time range
        filtered_data = data[(data.index >= target_start) & (data.index <= target_end)]
        
        if filtered_data.empty:
            print(f"\n⚠ No data found for {target_date} between {start_time} and {end_time} EST")
            print(f"\nAvailable date range in fetched data:")
            print(f"  Start: {data.index[0]}")
            print(f"  End: {data.index[-1]}")
            
            # Show what data exists for that date
            date_data = data[data.index.date == pd.Timestamp(target_date).date()]
            if not date_data.empty:
                print(f"\n✓ Found {len(date_data)} data points for {target_date}")
                print(f"  Time range: {date_data.index[0].strftime('%H:%M')} - {date_data.index[-1].strftime('%H:%M')} EST")
                print("\nShowing all data for that date:")
                print(date_data)
                return date_data
            else:
                print(f"\n✗ No data available for {target_date}")
            return None
        
        print(f"\n✓ Successfully retrieved {len(filtered_data)} data points")
        print(f"\nTime Range: {filtered_data.index[0]} to {filtered_data.index[-1]}")
        print("\n" + "="*60)
        print(f"YM Data for {target_date} ({start_time} - {end_time} EST):")
        print("="*60)
        print(filtered_data)
        
        print("\n" + "="*60)
        print("Summary Statistics:")
        print("="*60)
        print(filtered_data.describe())
        
        # Price movement analysis
        print("\n" + "="*60)
        print("Price Movement Analysis:")
        print("="*60)
        print(f"Opening Price: {filtered_data['Open'].iloc[0]:,.2f}")
        print(f"Closing Price: {filtered_data['Close'].iloc[-1]:,.2f}")
        print(f"High: {filtered_data['High'].max():,.2f}")
        print(f"Low: {filtered_data['Low'].min():,.2f}")
        print(f"Price Change: {filtered_data['Close'].iloc[-1] - filtered_data['Open'].iloc[0]:,.2f}")
        print(f"Total Volume: {filtered_data['Volume'].sum():,.0f}")
        
        # Save to CSV
        filename = f"YM_intraday_{target_date}_{start_time.replace(':', '')}-{end_time.replace(':', '')}.csv"
        filtered_data.to_csv(filename)
        print(f"\n✓ Data saved to: {filename}")
        
        return filtered_data
        
    except Exception as e:
        print(f"\n✗ Error fetching intraday data: {str(e)}")
        import traceback
        traceback.print_exc()
        return None


def plot_intraday_data(data, target_date, start_time, end_time):
    """
    Create interactive visualization for intraday YM data with navigation buttons
    Use buttons to move forward and backward through time
    """
    if data is None or data.empty:
        print("\n✗ No data to plot")
        return
    
    print("\n" + "="*60)
    print("Creating Interactive Graph...")
    print("="*60)
    print("Use buttons to navigate through time:")
    print("  - '<< Start' - Jump to beginning")
    print("  - '< Back' - Go back one minute")
    print("  - 'Forward >' - Go forward one minute")
    print("  - 'End >>' - Jump to end")
    print("  - 'Play' - Auto-play animation")
    print("\nClose the window when finished.")
    
    # Create output directory for saved images
    import os
    output_dir = "/Users/orkiskevin/Desktop/Trading/Temp"
    os.makedirs(output_dir, exist_ok=True)
    
    # Create figure with extra space for buttons
    fig = plt.figure(figsize=(14, 9))
    ax = plt.subplot2grid((10, 1), (0, 0), rowspan=9)
    fig.suptitle(f'YM Futures - {target_date} ({start_time} - {end_time} EST) - INTERACTIVE', 
                 fontsize=16, fontweight='bold')
    
    # Initialize lines
    line_high, = ax.plot([], [], label='High', color='green', linewidth=2, marker='o', markersize=5)
    line_low, = ax.plot([], [], label='Low', color='red', linewidth=2, marker='o', markersize=5)
    line_close, = ax.plot([], [], label='Close', color='black', linewidth=2.5, marker='s', markersize=5)
    
    # Initialize ray lines (will be drawn at 9:38)
    ray_max, = ax.plot([], [], 'orange', linewidth=2.5, label='Max Ray (-5°)', alpha=0.9)
    ray_min, = ax.plot([], [], 'yellow', linewidth=2.5, label='Min Ray (+5°)', alpha=0.9)
    ray_max_steep, = ax.plot([], [], color='darkviolet', linewidth=2.5, label='Max Ray (-65°)', alpha=0.9)
    ray_min_steep, = ax.plot([], [], color='blue', linewidth=2.5, label='Min Ray (+65°)', alpha=0.9)
    
    # Store annotations for labels
    annotations = []
    
    # Store sell signal markers
    sell_signal_markers = []
    sell_signal_annotations = []
    
    # Store buy signal markers
    buy_signal_markers = []
    buy_signal_annotations = []
    
    # Set up plot formatting
    ax.set_ylabel('Price', fontsize=13, fontweight='bold')
    ax.set_xlabel('Time (EST)', fontsize=13, fontweight='bold')
    ax.set_title('Price Movement by Minute', fontsize=14, fontweight='bold', pad=20)
    ax.legend(loc='best', fontsize=11)
    ax.grid(True, alpha=0.3, linestyle='--')
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')
    
    # Set axis limits
    y_min = data['Low'].min() - 20
    y_max = data['High'].max() + 20
    ax.set_ylim(y_min, y_max)
    ax.set_xlim(data.index[0], data.index[-1])
    
    # Statistics box
    stats_box = ax.text(0.98, 0.98, '', transform=ax.transAxes, fontsize=10, 
                       verticalalignment='top', horizontalalignment='right', bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
    
    # Current time display
    current_time_text = ax.text(0.5, 0.02, '', transform=ax.transAxes, fontsize=11, 
                               ha='center', bbox=dict(boxstyle='round', facecolor='lightblue', alpha=0.8))
    
    # State variable for current frame
    class State:
        current_frame = 0
        is_playing = False
        timer = None
        light_purple_crossed = False  # Track if light purple line has been crossed by close price
        snapshots_taken = set()  # Track which snapshots have been taken (e.g., '09:30', '09:45', '10:00')
        detected_sell_signals = {}  # Store detected sell signals permanently: {timestamp: price}
        detected_buy_signals = {}  # Store detected buy signals permanently: {timestamp: price}
        position = None  # Track current position: None (can buy or sell), 'long' (can only sell), 'short' (can only buy)
    
    state = State()
    
    def update_plot(frame):
        """Update the plot to show data up to specified frame"""
        state.current_frame = max(0, min(frame, len(data) - 1))
        
        # Define cutoff time for signal detection (9:38 AM)
        import pytz
        est = pytz.timezone('US/Eastern')
        cutoff_time = pd.Timestamp(f"{target_date} 09:38:00", tz=est)
        
        # Get data up to current frame
        current_data = data.iloc[:state.current_frame + 1]
        
        if len(current_data) == 0:
            return
        
        # Update line data
        
        # Draw rays starting from 9:30 (frame 0)
        if state.current_frame >= 0:
            # Find max and min from data so far (up to current frame)
            max_high = current_data['High'].max()
            min_low = current_data['Low'].min()
            max_idx = current_data['High'].idxmax()
            min_idx = current_data['Low'].idxmin()
            
            # Calculate slope for -5 degrees (max ray)
            angle_deg_max = -5
            angle_rad_max = np.deg2rad(angle_deg_max)
            tan_angle_max = np.tan(angle_rad_max)  # ≈ -0.0875
            
            # Calculate slope for +5 degrees (min ray)
            angle_deg_min = 5
            angle_rad_min = np.deg2rad(angle_deg_min)
            tan_angle_min = np.tan(angle_rad_min)  # ≈ +0.0875
            
            # Calculate slope for -65 degrees (steep ray from max - dark purple)
            angle_deg_max_steep = -65
            angle_rad_max_steep = np.deg2rad(angle_deg_max_steep)
            tan_angle_max_steep = np.tan(angle_rad_max_steep)  # ≈ -2.145
            
            # Calculate slope for +65 degrees (steep ray from min - light purple)
            angle_deg_min_steep = 65
            angle_rad_min_steep = np.deg2rad(angle_deg_min_steep)
            tan_angle_min_steep = np.tan(angle_rad_min_steep)  # ≈ +2.145
            
            # Get the last time in the data for the ray endpoint
            end_time = data.index[-1]
            
            # Convert times to matplotlib date numbers
            max_time_num = mdates.date2num(max_idx)
            min_time_num = mdates.date2num(min_idx)
            end_time_num = mdates.date2num(end_time)
            
            # Get axis limits to calculate proper aspect ratio
            xlim = ax.get_xlim()
            ylim = ax.get_ylim()
            
            # Calculate the aspect ratio (data units)
            x_range = xlim[1] - xlim[0]  # in days (matplotlib date numbers)
            y_range = ylim[1] - ylim[0]  # in price points
            
            # Get figure size in inches
            fig_width, fig_height = fig.get_size_inches()
            ax_bbox = ax.get_position()
            ax_width_inches = fig_width * ax_bbox.width
            ax_height_inches = fig_height * ax_bbox.height
            
            # Calculate data units per inch
            x_per_inch = x_range / ax_width_inches
            y_per_inch = y_range / ax_height_inches
            
            # For a true angle, we need: dy/dx in screen coordinates = tan(angle)
            slope_data_units_max = tan_angle_max * (y_per_inch / x_per_inch)
            slope_data_units_min = tan_angle_min * (y_per_inch / x_per_inch)
            slope_data_units_max_steep = tan_angle_max_steep * (y_per_inch / x_per_inch)
            slope_data_units_min_steep = tan_angle_min_steep * (y_per_inch / x_per_inch)
            
            # Calculate ray endpoints for max (downward at -5 degrees)
            time_diff_max = end_time_num - max_time_num
            max_ray_end_price = max_high + slope_data_units_max * time_diff_max
            ray_max.set_data([max_idx, end_time], [max_high, max_ray_end_price])
            
            # Calculate ray endpoints for min (upward at +5 degrees)
            time_diff_min = end_time_num - min_time_num
            min_ray_end_price = min_low + slope_data_units_min * time_diff_min
            ray_min.set_data([min_idx, end_time], [min_low, min_ray_end_price])
            
            # Calculate steep ray from max (downward at -65 degrees - dark purple)
            # Start at the first max and draw at -65 degrees
            # If new max is higher than starting max, move to new max
            # If new high crosses above the line, adjust to go through both maxes
            purple_max_high = current_data['High'].iloc[0]
            purple_max_idx = current_data.index[0]
            adjusted_max_slope = slope_data_units_max_steep
            
            # Check each subsequent point
            for i in range(1, len(current_data)):
                current_high = current_data['High'].iloc[i]
                current_close = current_data['Close'].iloc[i]
                current_idx = current_data.index[i]
                current_time_num = mdates.date2num(current_idx)
                
                # Calculate expected purple line price at this time (before potentially moving the line)
                purple_max_time_num = mdates.date2num(purple_max_idx)
                time_diff = current_time_num - purple_max_time_num
                
                if time_diff > 0:
                    expected_purple_price = purple_max_high + adjusted_max_slope * time_diff
                    
                    # Check if close price crosses above the dark purple line (BUY SIGNAL)
                    # Only generate BUY if we're not currently long (i.e., we're flat or short)
                    if current_close > expected_purple_price and current_idx > cutoff_time:
                        # Store this buy signal permanently if not already stored AND we're not long
                        if current_idx not in state.detected_buy_signals and state.position != 'long':
                            state.detected_buy_signals[current_idx] = current_close
                            state.position = 'long'  # Update position to long after buy
                
                # Now check if we need to move or adjust the purple line
                # First check: if this high is higher than the starting max, move to it
                if current_high > purple_max_high:
                    # Move purple line to start from this new higher max
                    purple_max_high = current_high
                    purple_max_idx = current_idx
                    adjusted_max_slope = slope_data_units_max_steep  # Reset to -65 degrees
                else:
                    # If current high crosses above the purple line
                    if time_diff > 0 and current_high > expected_purple_price:
                        # Adjust slope to go through both the starting max and this new high
                        adjusted_max_slope = (current_high - purple_max_high) / time_diff
            
            # Draw the dark purple ray
            purple_max_time_num = mdates.date2num(purple_max_idx)
            time_diff_purple_max = end_time_num - purple_max_time_num
            max_steep_end_price = purple_max_high + adjusted_max_slope * time_diff_purple_max
            ray_max_steep.set_data([purple_max_idx, end_time], [purple_max_high, max_steep_end_price])
            
            # Calculate steep ray from min (upward at +65 degrees - blue line)
            # Start at the first min and draw at +65 degrees
            # If new min is lower than starting min, move to new min
            # If new low crosses below the line, adjust to go through both mins
            # If close crosses below, generate SELL signal before moving
            purple_min_low = current_data['Low'].iloc[0]
            purple_min_idx = current_data.index[0]
            adjusted_min_slope = slope_data_units_min_steep
            
            # Check each subsequent point
            for i in range(1, len(current_data)):
                current_low = current_data['Low'].iloc[i]
                current_close = current_data['Close'].iloc[i]
                current_idx = current_data.index[i]
                current_time_num = mdates.date2num(current_idx)
                
                # Calculate expected blue line price at this time BEFORE any adjustments
                purple_min_time_num = mdates.date2num(purple_min_idx)
                time_diff = current_time_num - purple_min_time_num
                
                if time_diff > 0:
                    expected_blue_price = purple_min_low + adjusted_min_slope * time_diff
                    
                    # CHECK: If close price crosses BELOW blue line, generate SELL signal (after 9:38 AM)
                    # Only generate SELL if we're not currently short (i.e., we're flat or long)
                    if current_close < expected_blue_price and current_idx > cutoff_time:
                        # Store this sell signal permanently if not already stored AND we're not short
                        if current_idx not in state.detected_sell_signals and state.position != 'short':
                            state.detected_sell_signals[current_idx] = current_close
                            state.position = 'short'  # Update position to short after sell
                
                # NOW check if we need to move or adjust the blue line
                # First check: if this low is lower than the starting min, move to it
                if current_low < purple_min_low:
                    # Move blue line to start from this new lower min
                    purple_min_low = current_low
                    purple_min_idx = current_idx
                    adjusted_min_slope = slope_data_units_min_steep  # Reset to +65 degrees
                else:
                    # If current low crosses below the blue line, adjust slope
                    if time_diff > 0 and current_low < expected_blue_price:
                        # Adjust slope to go through both the starting min and this new low
                        adjusted_min_slope = (current_low - purple_min_low) / time_diff
            
            # Draw the light purple ray (only if not crossed by close price)
            purple_min_time_num = mdates.date2num(purple_min_idx)
            time_diff_purple_min = end_time_num - purple_min_time_num
            min_steep_end_price = purple_min_low + adjusted_min_slope * time_diff_purple_min
            
            # Check if close price has crossed below the light purple line
            if not state.light_purple_crossed:
                for i in range(len(current_data)):
                    current_idx = current_data.index[i]
                    current_close = current_data['Close'].iloc[i]
                    current_time_num = mdates.date2num(current_idx)
                    
                    # Calculate expected light purple line price at this time
                    time_diff_check = current_time_num - purple_min_time_num
                    if time_diff_check > 0:
                        expected_light_purple_price = purple_min_low + adjusted_min_slope * time_diff_check
                        
                        # If close price goes below the light purple line, mark as crossed
                        if current_close < expected_light_purple_price:
                            state.light_purple_crossed = True
                            break
            
            # Only draw the light purple ray if it hasn't been crossed
            if not state.light_purple_crossed:
                ray_min_steep.set_data([purple_min_idx, end_time], [purple_min_low, min_steep_end_price])
            else:
                ray_min_steep.set_data([], [])
        else:
            # Clear rays if no data
            ray_max.set_data([], [])
            ray_min.set_data([], [])
            ray_max_steep.set_data([], [])
            ray_min_steep.set_data([], [])
        times = current_data.index
        line_high.set_data(times, current_data['High'])
        line_low.set_data(times, current_data['Low'])
        line_close.set_data(times, current_data['Close'])
        
        # Clear previous annotations
        for annotation in annotations:
            annotation.remove()
        annotations.clear()
        
        # Add text annotations to each data point
        for i, (time, row) in enumerate(current_data.iterrows()):
            time_str = time.strftime('%H:%M')
            
            # Annotate High point (above the point)
            high_text = f"{row['High']:.0f}\n{time_str}"
            ann_high = ax.annotate(high_text, xy=(time, row['High']), 
                                  xytext=(0, 8), textcoords='offset points',
                                  ha='center', va='bottom', fontsize=6,
                                  color='darkgreen', fontweight='bold',
                                  bbox=dict(boxstyle='round,pad=0.3', facecolor='lightgreen', alpha=0.6, edgecolor='green'))
            annotations.append(ann_high)
            
            # Annotate Low point (below the point)
            low_text = f"{row['Low']:.0f}\n{time_str}"
            ann_low = ax.annotate(low_text, xy=(time, row['Low']), 
                                 xytext=(0, -8), textcoords='offset points',
                                 ha='center', va='top', fontsize=6,
                                 color='darkred', fontweight='bold',
                                 bbox=dict(boxstyle='round,pad=0.3', facecolor='lightcoral', alpha=0.6, edgecolor='red'))
            annotations.append(ann_low)
            
            # Annotate Close point (to the right of the point)
            close_text = f"{row['Close']:.0f}\n{time_str}"
            ann_close = ax.annotate(close_text, xy=(time, row['Close']), 
                                   xytext=(5, 0), textcoords='offset points',
                                   ha='left', va='center', fontsize=6,
                                   color='black', fontweight='bold',
                                   bbox=dict(boxstyle='round,pad=0.3', facecolor='lightgray', alpha=0.6, edgecolor='black'))
            annotations.append(ann_close)
        
        # Clear previous sell signal markers
        for marker in sell_signal_markers:
            marker.remove()
        sell_signal_markers.clear()
        for annotation in sell_signal_annotations:
            annotation.remove()
        sell_signal_annotations.clear()
        
        # Clear previous buy signal markers
        for marker in buy_signal_markers:
            marker.remove()
        buy_signal_markers.clear()
        for annotation in buy_signal_annotations:
            annotation.remove()
        buy_signal_annotations.clear()
        
        # Check for sell signals after 9:38 AM (cutoff_time defined at start of function)
        # Only check if we have ray data and are past 9:38
        if state.current_frame >= 0 and len(current_data) > 0:
            # Get the min_low point and calculate yellow ray values
            min_low_val = current_data['Low'].min()
            min_idx_val = current_data['Low'].idxmin()
            min_time_num_val = mdates.date2num(min_idx_val)
            
            # Calculate slope for yellow ray (+5 degrees)
            xlim = ax.get_xlim()
            ylim = ax.get_ylim()
            x_range = xlim[1] - xlim[0]
            y_range = ylim[1] - ylim[0]
            fig_width, fig_height = fig.get_size_inches()
            ax_bbox = ax.get_position()
            ax_width_inches = fig_width * ax_bbox.width
            ax_height_inches = fig_height * ax_bbox.height
            x_per_inch = x_range / ax_width_inches
            y_per_inch = y_range / ax_height_inches
            
            angle_deg_min = 5
            angle_rad_min = np.deg2rad(angle_deg_min)
            tan_angle_min = np.tan(angle_rad_min)
            slope_data_units_min_val = tan_angle_min * (y_per_inch / x_per_inch)
            
            # Check each point after 9:38 AM
            for i, (time, row) in enumerate(current_data.iterrows()):
                if time > cutoff_time:
                    # Calculate expected yellow ray price at this time
                    current_time_num = mdates.date2num(time)
                    time_diff = current_time_num - min_time_num_val
                    yellow_ray_price = min_low_val + slope_data_units_min_val * time_diff
                    
                    # Check if close price is below yellow ray
                    if row['Close'] < yellow_ray_price:
                        # Store this sell signal permanently if not already stored
                        if time not in state.detected_sell_signals:
                            state.detected_sell_signals[time] = row['Close']
            
            # Draw all detected sell signals (they stay forever once detected)
            for sell_time, sell_price in state.detected_sell_signals.items():
                # Only draw if the time is within current data range
                if sell_time <= current_data.index[-1]:
                    marker, = ax.plot(sell_time, sell_price, marker='v', markersize=15, 
                                    color='red', markeredgecolor='darkred', markeredgewidth=2,
                                    zorder=10)
                    sell_signal_markers.append(marker)
                    
                    # Add SELL annotation
                    sell_text = f"SELL SIGNAL\n{sell_price:.0f}\n{sell_time.strftime('%H:%M')}"
                    ann_sell = ax.annotate(sell_text, xy=(sell_time, sell_price), 
                                         xytext=(0, -30), textcoords='offset points',
                                         ha='center', va='top', fontsize=8,
                                         color='white', fontweight='bold',
                                         bbox=dict(boxstyle='round,pad=0.5', facecolor='red', 
                                                  alpha=0.9, edgecolor='darkred', linewidth=2),
                                         arrowprops=dict(arrowstyle='->', color='red', lw=2))
                    sell_signal_annotations.append(ann_sell)
            
            # Draw all detected buy signals (they stay forever once detected)
            for buy_time, buy_price in state.detected_buy_signals.items():
                # Only draw if the time is within current data range
                if buy_time <= current_data.index[-1]:
                    marker, = ax.plot(buy_time, buy_price, marker='^', markersize=15, 
                                    color='green', markeredgecolor='darkgreen', markeredgewidth=2,
                                    zorder=10)
                    buy_signal_markers.append(marker)
                    
                    # Add BUY annotation
                    buy_text = f"BUY SIGNAL\n{buy_price:.0f}\n{buy_time.strftime('%H:%M')}"
                    ann_buy = ax.annotate(buy_text, xy=(buy_time, buy_price), 
                                         xytext=(0, 30), textcoords='offset points',
                                         ha='center', va='bottom', fontsize=8,
                                         color='white', fontweight='bold',
                                         bbox=dict(boxstyle='round,pad=0.5', facecolor='green', 
                                                  alpha=0.9, edgecolor='darkgreen', linewidth=2),
                                         arrowprops=dict(arrowstyle='->', color='green', lw=2))
                    buy_signal_annotations.append(ann_buy)
        
        # Update statistics
        max_high = current_data['High'].max()
        min_low = current_data['Low'].min()
        price_range = max_high - min_low
        price_change = current_data['Close'].iloc[-1] - current_data['Close'].iloc[0]
        
        # Find when max and min occurred
        max_time = current_data['High'].idxmax().strftime('%H:%M')
        min_time = current_data['Low'].idxmin().strftime('%H:%M')
        current_time_str = times[-1].strftime('%H:%M')
        
        stats_text = f"Minute: {state.current_frame + 1}/{len(data)}\n"
        stats_text += f"Current Time: {current_time_str}\n"
        stats_text += f"━━━━━━━━━━━━━━━━━━━━\n"
        stats_text += f"Opening: {current_data['Close'].iloc[0]:,.0f}\n"
        stats_text += f"Current: {current_data['Close'].iloc[-1]:,.0f}\n"
        stats_text += f"Change: {price_change:+.0f} points\n"
        stats_text += f"━━━━━━━━━━━━━━━━━━━━\n"
        stats_text += f"MAX (9:30-{current_time_str}):\n"
        stats_text += f"  High: {max_high:,.0f} @ {max_time}\n"
        stats_text += f"MIN (9:30-{current_time_str}):\n"
        stats_text += f"  Low: {min_low:,.0f} @ {min_time}\n"
        stats_text += f"Range: {price_range:.0f} points"
        
        stats_box.set_text(stats_text)
        
        # Update navigation info
        current_time_display = times[-1].strftime('%H:%M:%S')
        current_time_text.set_text(f"Viewing: {current_time_display} | Use buttons to navigate through time")
        
        fig.canvas.draw_idle()
        
        # Save snapshots at specific times (9:31, 9:38, 9:45, 9:55, 10:00)
        snapshot_times = ['09:31', '09:38', '09:45', '09:55', '10:00']
        current_time_hhmm = times[-1].strftime('%H:%M')
        
        if current_time_hhmm in snapshot_times and current_time_hhmm not in state.snapshots_taken:
            # Save the current state to file
            timestamp_filename = times[-1].strftime('%Y%m%d_%H%M')
            snapshot_filename = f"{output_dir}/YM_{target_date}_{timestamp_filename}.png"
            fig.savefig(snapshot_filename, dpi=300, bbox_inches='tight')
            state.snapshots_taken.add(current_time_hhmm)
            print(f"  📸 Snapshot saved: {snapshot_filename}")
    
    def on_start(event):
        """Jump to start"""
        state.is_playing = False
        if state.timer:
            state.timer.stop()
        update_plot(0)
    
    def on_back(event):
        """Go back one minute"""
        state.is_playing = False
        if state.timer:
            state.timer.stop()
        update_plot(state.current_frame - 1)
    
    def on_forward(event):
        """Go forward one minute"""
        state.is_playing = False
        if state.timer:
            state.timer.stop()
        update_plot(state.current_frame + 1)
    
    def on_end(event):
        """Jump to end"""
        state.is_playing = False
        if state.timer:
            state.timer.stop()
        update_plot(len(data) - 1)
    
    def on_play(event):
        """Toggle auto-play"""
        if state.is_playing:
            # Stop playing
            state.is_playing = False
            if state.timer:
                state.timer.stop()
            btn_play.label.set_text('Play')
        else:
            # Start playing
            state.is_playing = True
            btn_play.label.set_text('Pause')
            play_animation()
    
    def play_animation():
        """Auto-advance frames"""
        if state.is_playing and state.current_frame < len(data) - 1:
            update_plot(state.current_frame + 1)
            state.timer = fig.canvas.new_timer(interval=500)
            state.timer.single_shot = True
            state.timer.add_callback(play_animation)
            state.timer.start()
        else:
            state.is_playing = False
            btn_play.label.set_text('Play')
    
    # Create button axes
    ax_start = plt.axes([0.1, 0.02, 0.1, 0.04])
    ax_back = plt.axes([0.22, 0.02, 0.1, 0.04])
    ax_forward = plt.axes([0.34, 0.02, 0.1, 0.04])
    ax_end = plt.axes([0.46, 0.02, 0.1, 0.04])
    ax_play = plt.axes([0.58, 0.02, 0.1, 0.04])
    
    # Create buttons
    btn_start = Button(ax_start, '<< Start')
    btn_back = Button(ax_back, '< Back')
    btn_forward = Button(ax_forward, 'Forward >')
    btn_end = Button(ax_end, 'End >>')
    btn_play = Button(ax_play, 'Play')
    
    # Connect buttons to callbacks
    btn_start.on_clicked(on_start)
    btn_back.on_clicked(on_back)
    btn_forward.on_clicked(on_forward)
    btn_end.on_clicked(on_end)
    btn_play.on_clicked(on_play)
    
    # Initialize with first frame
    update_plot(0)
    
    print(f"\n✓ Interactive graph ready!")
    print(f"  - Total minutes: {len(data)}")
    print(f"  - Use buttons to navigate")
    
    # Display the interactive plot
    plt.show()
    
    # Save final frame after closing
    fig2, ax2 = plt.subplots(figsize=(14, 8))
    fig2.suptitle(f'YM Futures - {target_date} ({start_time} - {end_time} EST)', 
                  fontsize=16, fontweight='bold')
    
    times = data.index
    ax2.plot(times, data['High'], label='High', color='green', linewidth=2, marker='o', markersize=4)
    ax2.plot(times, data['Low'], label='Low', color='red', linewidth=2, marker='o', markersize=4)
    ax2.plot(times, data['Close'], label='Close', color='black', linewidth=2.5, marker='s', markersize=4)
    
    # Add annotations to each data point in the saved chart
    for i, (time, row) in enumerate(data.iterrows()):
        time_str = time.strftime('%H:%M')
        
        # Annotate High point (above the point)
        high_text = f"{row['High']:.0f}\n{time_str}"
        ax2.annotate(high_text, xy=(time, row['High']), 
                    xytext=(0, 8), textcoords='offset points',
                    ha='center', va='bottom', fontsize=6,
                    color='darkgreen', fontweight='bold',
                    bbox=dict(boxstyle='round,pad=0.3', facecolor='lightgreen', alpha=0.6, edgecolor='green'))
        
        # Annotate Low point (below the point)
        low_text = f"{row['Low']:.0f}\n{time_str}"
        ax2.annotate(low_text, xy=(time, row['Low']), 
                    xytext=(0, -8), textcoords='offset points',
                    ha='center', va='top', fontsize=6,
                    color='darkred', fontweight='bold',
                    bbox=dict(boxstyle='round,pad=0.3', facecolor='lightcoral', alpha=0.6, edgecolor='red'))
        
        # Annotate Close point (to the right of the point)
        close_text = f"{row['Close']:.0f}\n{time_str}"
        ax2.annotate(close_text, xy=(time, row['Close']), 
                    xytext=(5, 0), textcoords='offset points',
                    ha='left', va='center', fontsize=6,
                    color='black', fontweight='bold',
                    bbox=dict(boxstyle='round,pad=0.3', facecolor='lightgray', alpha=0.6, edgecolor='black'))
    
    # Add yellow ray (Min Ray +5°) to saved chart
    min_low_chart = data['Low'].min()
    min_idx_chart = data['Low'].idxmin()
    end_time_chart = data.index[-1]
    
    # Calculate slope for yellow ray
    xlim = ax2.get_xlim()
    ylim = ax2.get_ylim()
    x_range = xlim[1] - xlim[0]
    y_range = ylim[1] - ylim[0]
    fig_width, fig_height = fig2.get_size_inches()
    ax_bbox = ax2.get_position()
    ax_width_inches = fig_width * ax_bbox.width
    ax_height_inches = fig_height * ax_bbox.height
    x_per_inch = x_range / ax_width_inches
    y_per_inch = y_range / ax_height_inches
    
    angle_deg_min = 5
    angle_rad_min = np.deg2rad(angle_deg_min)
    tan_angle_min = np.tan(angle_rad_min)
    slope_data_units_min_chart = tan_angle_min * (y_per_inch / x_per_inch)
    
    min_time_num_chart = mdates.date2num(min_idx_chart)
    end_time_num_chart = mdates.date2num(end_time_chart)
    time_diff_chart = end_time_num_chart - min_time_num_chart
    min_ray_end_price_chart = min_low_chart + slope_data_units_min_chart * time_diff_chart
    ax2.plot([min_idx_chart, end_time_chart], [min_low_chart, min_ray_end_price_chart], 
             'yellow', linewidth=2.5, label='Min Ray (+5°)', alpha=0.9)
    
    # Check for sell signals after 9:38 AM in saved chart
    import pytz
    est = pytz.timezone('US/Eastern')
    cutoff_time = pd.Timestamp(f"{target_date} 09:38:00", tz=est)
    
    sell_signals_found = []
    for i, (time, row) in enumerate(data.iterrows()):
        if time > cutoff_time:
            # Calculate expected yellow ray price at this time
            current_time_num = mdates.date2num(time)
            time_diff = current_time_num - min_time_num_chart
            yellow_ray_price = min_low_chart + slope_data_units_min_chart * time_diff
            
            # Check if close price is below yellow ray
            if row['Close'] < yellow_ray_price:
                # Mark this as a SELL SIGNAL
                ax2.plot(time, row['Close'], marker='v', markersize=15, 
                        color='red', markeredgecolor='darkred', markeredgewidth=2,
                        zorder=10)
                
                # Add SELL annotation
                sell_text = f"SELL\n{row['Close']:.0f}\n{time.strftime('%H:%M')}"
                ax2.annotate(sell_text, xy=(time, row['Close']), 
                           xytext=(0, -30), textcoords='offset points',
                           ha='center', va='top', fontsize=8,
                           color='white', fontweight='bold',
                           bbox=dict(boxstyle='round,pad=0.5', facecolor='red', 
                                    alpha=0.9, edgecolor='darkred', linewidth=2),
                           arrowprops=dict(arrowstyle='->', color='red', lw=2))
                sell_signals_found.append((time.strftime('%H:%M'), row['Close']))
    
    # Check for buy signals after 9:38 AM in saved chart (when close crosses above dark purple line)
    # Calculate dark purple line for the chart
    angle_deg_max_steep = -65
    angle_rad_max_steep = np.deg2rad(angle_deg_max_steep)
    tan_angle_max_steep = np.tan(angle_rad_max_steep)
    slope_data_units_max_steep_chart = tan_angle_max_steep * (y_per_inch / x_per_inch)
    
    purple_max_high_chart = data['High'].iloc[0]
    purple_max_idx_chart = data.index[0]
    adjusted_max_slope_chart = slope_data_units_max_steep_chart
    
    # Replicate the dark purple line calculation for saved chart
    for i in range(1, len(data)):
        current_high_chart = data['High'].iloc[i]
        current_idx_chart = data.index[i]
        current_time_num_chart_check = mdates.date2num(current_idx_chart)
        
        if current_high_chart > purple_max_high_chart:
            purple_max_high_chart = current_high_chart
            purple_max_idx_chart = current_idx_chart
            adjusted_max_slope_chart = slope_data_units_max_steep_chart
        else:
            purple_max_time_num_chart_check = mdates.date2num(purple_max_idx_chart)
            time_diff_chart_check = current_time_num_chart_check - purple_max_time_num_chart_check
            
            if time_diff_chart_check > 0:
                expected_purple_price_chart = purple_max_high_chart + adjusted_max_slope_chart * time_diff_chart_check
                if current_high_chart > expected_purple_price_chart:
                    adjusted_max_slope_chart = (current_high_chart - purple_max_high_chart) / time_diff_chart_check
    
    # Now check for buy signals
    buy_signals_found = []
    purple_max_time_num_final_chart = mdates.date2num(purple_max_idx_chart)
    
    for i, (time, row) in enumerate(data.iterrows()):
        if time > cutoff_time:
            # Calculate expected dark purple line price at this time
            current_time_num = mdates.date2num(time)
            time_diff = current_time_num - purple_max_time_num_final_chart
            
            if time_diff > 0:
                dark_purple_price = purple_max_high_chart + adjusted_max_slope_chart * time_diff
                
                # Check if close price is above dark purple ray
                if row['Close'] > dark_purple_price:
                    # Mark this as a BUY SIGNAL
                    ax2.plot(time, row['Close'], marker='^', markersize=15, 
                            color='green', markeredgecolor='darkgreen', markeredgewidth=2,
                            zorder=10)
                    
                    # Add BUY annotation
                    buy_text = f"BUY\n{row['Close']:.0f}\n{time.strftime('%H:%M')}"
                    ax2.annotate(buy_text, xy=(time, row['Close']), 
                               xytext=(0, 30), textcoords='offset points',
                               ha='center', va='bottom', fontsize=8,
                               color='white', fontweight='bold',
                               bbox=dict(boxstyle='round,pad=0.5', facecolor='green', 
                                        alpha=0.9, edgecolor='darkgreen', linewidth=2),
                               arrowprops=dict(arrowstyle='->', color='green', lw=2))
                    buy_signals_found.append((time.strftime('%H:%M'), row['Close']))
    
    ax2.set_ylabel('Price', fontsize=13, fontweight='bold')
    ax2.set_xlabel('Time (EST)', fontsize=13, fontweight='bold')
    ax2.set_title('Price Movement by Minute', fontsize=14, fontweight='bold', pad=20)
    ax2.legend(loc='best', fontsize=11)
    ax2.grid(True, alpha=0.3, linestyle='--')
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
    plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45, ha='right')
    
    price_range = data['High'].max() - data['Low'].min()
    price_change = data['Close'].iloc[-1] - data['Close'].iloc[0]
    
    stats_text = f"Opening: {data['Close'].iloc[0]:,.0f}\n"
    stats_text += f"Closing: {data['Close'].iloc[-1]:,.0f}\n"
    stats_text += f"High: {data['High'].max():,.0f}\n"
    stats_text += f"Low: {data['Low'].min():,.0f}\n"
    stats_text += f"Range: {price_range:.0f} points\n"
    stats_text += f"Change: {price_change:+.0f} points\n"
    if buy_signals_found:
        stats_text += f"━━━━━━━━━━━━━━━━━━\n"
        stats_text += f"BUY SIGNALS: {len(buy_signals_found)}\n"
        for buy_time, buy_price in buy_signals_found:
            stats_text += f"  {buy_time}: {buy_price:.0f}\n"
    if sell_signals_found:
        stats_text += f"━━━━━━━━━━━━━━━━━━\n"
        stats_text += f"SELL SIGNALS: {len(sell_signals_found)}\n"
        for sell_time, sell_price in sell_signals_found:
            stats_text += f"  {sell_time}: {sell_price:.0f}\n"
    
    ax2.text(0.02, 0.98, stats_text, transform=ax2.transAxes, fontsize=10, 
            verticalalignment='top', bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
    
    plt.tight_layout()
    
    filename = f"YM_chart_{target_date}_{start_time.replace(':', '')}-{end_time.replace(':', '')}.png"
    plt.savefig(filename, dpi=300, bbox_inches='tight')
    plt.close(fig2)
    
    print(f"\n✓ Chart saved to: {filename}")
    
    # Report buy signals
    if buy_signals_found:
        print(f"\n🟢 BUY SIGNALS DETECTED: {len(buy_signals_found)}")
        print("="*60)
        for buy_time, buy_price in buy_signals_found:
            print(f"  Time: {buy_time} | Price: {buy_price:.0f} (Close above dark purple ray)")
        print("="*60)
    
    # Report sell signals
    if sell_signals_found:
        print(f"\n🚨 SELL SIGNALS DETECTED: {len(sell_signals_found)}")
        print("="*60)
        for sell_time, sell_price in sell_signals_found:
            print(f"  Time: {sell_time} | Price: {sell_price:.0f} (Close below yellow ray)")
        print("="*60)
    
    if not buy_signals_found and not sell_signals_found:
        print(f"\n✓ No signals detected after 9:38 AM")
    
    print("✓ Interactive session completed")


if __name__ == "__main__":
    # Fetch YM intraday data for specific date and time
    target_date = "2026-01-08"
   ## target_date = "2026-01-13" 
    start_time = "09:30"
    end_time = "10:00"
    
    data = get_ym_intraday(target_date=target_date, start_time=start_time, end_time=end_time)
    
    # Create graphs
    if data is not None and not data.empty:
        plot_intraday_data(data, target_date, start_time, end_time)
    
    print("\n" + "="*60)
    print("Completed!")
    print("="*60)