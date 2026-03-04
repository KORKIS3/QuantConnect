from data_extraction import get_ym_intraday
from plotFigure import plot_intraday_data
import os

if __name__ == '__main__':
    target_date = '2026-01-28'
    start_time = '09:30'
    end_time = '10:00'

    csv_filename = f"YM_intraday_{target_date}_{start_time.replace(':','')}-{end_time.replace(':','')}.csv"
    use_csv = os.path.exists(csv_filename)
    if use_csv:
        print(f"Loading local CSV: {csv_filename}")

    data = get_ym_intraday(target_date=target_date, start_time=start_time, end_time=end_time, use_csv=use_csv)

    if data is None or data.empty:
        print(f"No data to plot for {target_date}")
    else:
        plot_intraday_data(data, target_date, start_time, end_time)
