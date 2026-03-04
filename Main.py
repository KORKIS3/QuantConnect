"""
YM Futures Trading Analysis - Main Script (Refactored with OOP)
"""


# Import data extraction functions
from data_extraction import get_ym_intraday
# Import plotting function
from plotFigure import plot_intraday_data
import os


if __name__ == "__main__":
    target_date = "2026-02-20"  # Set to the date you want to analyze
    start_time = "09:30"
    end_time = "10:00"

    # Check if local CSV exists for the date
    local_csv = f"YM_intraday_{target_date}_{start_time.replace(':', '')}-{end_time.replace(':', '')}.csv"
    use_csv = os.path.exists(local_csv)

    data = get_ym_intraday(target_date=target_date, start_time=start_time, end_time=end_time, use_csv=use_csv)

    if data is not None and not data.empty:
        plot_intraday_data(data, target_date, start_time, end_time)

    print("\n" + "="*60)
    print("Completed!")
    print("="*60)
