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
    ray_max, = ax.plot([], [], 'b--', linewidth=2, label='Max Ray (-5°)', alpha=0.7)
    ray_min, = ax.plot([], [], 'm--', linewidth=2, label='Min Ray (+5°)', alpha=0.7)
    
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
    stats_box = ax.text(0.02, 0.98, '', transform=ax.transAxes, fontsize=10, 
                       verticalalignment='top', bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
    
    # Current time display
    current_time_text = ax.text(0.5, 0.02, '', transform=ax.transAxes, fontsize=11, 
                               ha='center', bbox=dict(boxstyle='round', facecolor='lightblue', alpha=0.8))
    
    # State variable for current frame
    class State:
        current_frame = 0
        is_playing = False
        timer = None
    
    state = State()
    
    def update_plot(frame):
        """Update the plot to show data up to specified frame"""
        state.current_frame = max(0, min(frame, len(data) - 1))
        
        # Get data up to current frame
        current_data = data.iloc[:state.current_frame + 1]
        
        if len(current_data) == 0:
            return
        
        # Update line data
        
        # Draw rays at 9:38 (frame 8, since 9:30 is frame 0)
        if state.current_frame >= 8:
            # Get data up to 9:38 (first 9 minutes)
            data_to_938 = data.iloc[:9]
            
            # Find max and min up to 9:38
            max_high = data_to_938['High'].max()
            min_low = data_to_938['Low'].min()
            max_idx = data_to_938['High'].idxmax()
            min_idx = data_to_938['Low'].idxmin()
            
            # Calculate slope for -5 degrees (max ray)
            angle_deg_max = -5
            angle_rad_max = np.deg2rad(angle_deg_max)
            tan_angle_max = np.tan(angle_rad_max)  # ≈ -0.0875
            
            # Calculate slope for +5 degrees (min ray)
            angle_deg_min = 5
            angle_rad_min = np.deg2rad(angle_deg_min)
            tan_angle_min = np.tan(angle_rad_min)  # ≈ +0.0875
            
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
            
            # Calculate ray endpoints for max (downward at -5 degrees)
            time_diff_max = end_time_num - max_time_num
            max_ray_end_price = max_high + slope_data_units_max * time_diff_max
            ray_max.set_data([max_idx, end_time], [max_high, max_ray_end_price])
            
            # Calculate ray endpoints for min (upward at +5 degrees)
            time_diff_min = end_time_num - min_time_num
            min_ray_end_price = min_low + slope_data_units_min * time_diff_min
            ray_min.set_data([min_idx, end_time], [min_low, min_ray_end_price])
        else:
            # Clear rays if before 9:38
            ray_max.set_data([], [])
            ray_min.set_data([], [])
        times = current_data.index
        line_high.set_data(times, current_data['High'])
        line_low.set_data(times, current_data['Low'])
        line_close.set_data(times, current_data['Close'])
        
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
    stats_text += f"Change: {price_change:+.0f} points"
    
    ax2.text(0.02, 0.98, stats_text, transform=ax2.transAxes, fontsize=10, 
            verticalalignment='top', bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
    
    plt.tight_layout()
    
    filename = f"YM_chart_{target_date}_{start_time.replace(':', '')}-{end_time.replace(':', '')}.png"
    plt.savefig(filename, dpi=300, bbox_inches='tight')
    plt.close(fig2)
    
    print(f"\n✓ Chart saved to: {filename}")
    print("✓ Interactive session completed")


if __name__ == "__main__":
    # Fetch YM intraday data for specific date and time
    target_date = "2026-01-14"
    start_time = "09:30"
    end_time = "10:00"
    
    data = get_ym_intraday(target_date=target_date, start_time=start_time, end_time=end_time)
    
    # Create graphs
    if data is not None and not data.empty:
        plot_intraday_data(data, target_date, start_time, end_time)
    
    print("\n" + "="*60)
    print("Completed!")
    print("="*60)