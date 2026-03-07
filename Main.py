"""
YM Futures Trading Analysis - Main Script (Refactored with OOP)
"""


# Import data extraction functions
from data_extraction import get_ym_intraday
# Import plotting function
from plotFigure import plot_intraday_data
import os


if __name__ == "__main__":
    target_date = "2026-02-11"
    start_time = "09:30"
    end_time = "10:00"

    # Load directly from CBOT_MINI_YM1_ByDate_930_1000 folder
    import pytz
    from RunFullDataSet import _load_csv_as_df

    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    csv_path = os.path.join(desktop, "CBOT_MINI_YM1_ByDate_930_1000", f"CBOT_MINI_YM1_{target_date}.csv")

    print(f"Loading: {csv_path}")
    data = _load_csv_as_df(csv_path)

    if data is not None and not data.empty:
        plot_intraday_data(data, target_date, start_time, end_time)

    print("\n" + "="*60)
    print("Completed!")
    print("="*60)
