#!/usr/bin/env python3
"""
Fetch 09:30-10:00 EST intraday YM data for every business day in February 2026.

Notes:
- Yahoo Finance via `yfinance` only provides 1m interval data for the last ~7 days.
  Calls for dates older than that will fail to return 1m bars. Use a paid/alternative
  data provider (Polygon/Tiingo/Quandl/IB) if you need historic 1m bars.

Usage:
    python fetch_feb_2026_intraday.py

The script calls `get_ym_intraday()` from `data_extraction.py`. That function will
save CSV files named `YM_intraday_<date>_0930-1000.csv` when successful.
"""

from data_extraction import get_ym_intraday
import datetime
import time
import calendar


def business_days_in_feb_2026():
    year = 2026
    month = 2
    num_days = calendar.monthrange(year, month)[1]
    days = []
    for d in range(1, num_days + 1):
        dt = datetime.date(year, month, d)
        # Skip weekends
        if dt.weekday() < 5:
            days.append(dt.strftime('%Y-%m-%d'))
    return days


def main():
    dates = business_days_in_feb_2026()
    print(f"Found {len(dates)} business days in Feb 2026")

    for target_date in dates:
        print('\n' + '='*60)
        print(f"Fetching {target_date} 09:30-10:00 EST")
        try:
            # get_ym_intraday will save CSV if successful
            data = get_ym_intraday(target_date=target_date, start_time='09:30', end_time='10:00', use_csv=False)
            if data is None or data.empty:
                print(f"No 1m intraday data available for {target_date} (likely outside yfinance 7-day window)")
            else:
                print(f"Saved CSV for {target_date}")
        except Exception as e:
            print(f"Error fetching {target_date}: {e}")

        # Be polite; avoid hammering any API
        time.sleep(1.0)


if __name__ == '__main__':
    main()
