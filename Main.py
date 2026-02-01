"""
YM Futures Trading Analysis - Main Script (Refactored with OOP)
"""

# Import data extraction functions
from data_extraction import get_ym_intraday
# Import plotting function
from plotFigure import plot_intraday_data


if __name__ == "__main__":
    target_date = "2026-01-23"
    start_time = "09:30"
    end_time = "10:00"
    
    data = get_ym_intraday(target_date=target_date, start_time=start_time, end_time=end_time, use_csv=True)
    
    if data is not None and not data.empty:
        plot_intraday_data(data, target_date, start_time, end_time)
    
    print("\n" + "="*60)
    print("Completed!")
    print("="*60)
