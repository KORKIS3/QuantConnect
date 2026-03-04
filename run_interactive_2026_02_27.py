from data_extraction import get_ym_intraday
from plotFigure import plot_intraday_data

if __name__ == '__main__':
    target_date = '2026-02-27'
    start_time = '09:30'
    end_time = '10:00'

    data = get_ym_intraday(target_date=target_date, start_time=start_time, end_time=end_time, use_csv=True)

    if data is None or data.empty:
        print(f"No data available for {target_date}")
    else:
        plot_intraday_data(data, target_date, start_time, end_time)
