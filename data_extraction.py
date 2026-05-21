"""
Yahoo Finance Data Retrieval for YM (Micro E-mini Dow)
"""

import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta


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

    ticker = "YM=F"

    try:
        ym = yf.Ticker(ticker)

        print(f"\nTicker: {ticker}")
        print(f"Period: {period}")
        print(f"Interval: {interval}")
        print("\nFetching data...")

        data = ym.history(period=period, interval=interval)

        if data.empty:
            print("\nNo data returned. Trying alternative ticker...")
            ticker = "YM"
            ym = yf.Ticker(ticker)
            data = ym.history(period=period, interval=interval)

        if not data.empty:
            print(f"\nSuccessfully retrieved {len(data)} data points")
            print(f"\nDate Range: {data.index[0]} to {data.index[-1]}")
            print("\n" + "="*60)
            print("Latest Data:")
            print("="*60)
            print(data.tail(10))

            print("\n" + "="*60)
            print("Summary Statistics:")
            print("="*60)
            print(data.describe())

            filename = f"YM_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            data.to_csv(filename)
            print(f"\nData saved to: {filename}")

            return data
        else:
            print("\nNo data available for YM")
            return None

    except Exception as e:
        print(f"\nError fetching data: {str(e)}")
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


def get_ym_intraday(target_date="2026-01-14", start_time="09:30", end_time="10:00", use_csv=False):
    """
    Fetch intraday YM data for a specific date and time range

    Parameters:
    - target_date: Date in YYYY-MM-DD format
    - start_time: Start time in HH:MM format (EST)
    - end_time: End time in HH:MM format (EST)
    - use_csv: If True, load data from existing CSV file instead of fetching from API
    """

    print("="*60)
    print("Fetching Intraday YM Data from Yahoo Finance" if not use_csv else "Loading Intraday YM Data from CSV")
    print("="*60)

    ticker = "YM=F"

    if use_csv:
        filename = f"YM_intraday_{target_date}_{start_time.replace(':', '')}-{end_time.replace(':', '')}.csv"
        try:
            print(f"\nLoading data from: {filename}")
            data = pd.read_csv(filename, index_col=0, parse_dates=True)

            import pytz
            est = pytz.timezone('US/Eastern')
            if data.index.tz is None:
                data.index = pd.to_datetime(data.index).tz_localize(est)
            else:
                data.index = pd.to_datetime(data.index).tz_convert(est)

            print(f"\nSuccessfully loaded {len(data)} data points from CSV")
            print(f"\nTime Range: {data.index[0]} to {data.index[-1]}")

            return data

        except FileNotFoundError:
            print(f"\nCSV file not found: {filename}")
            print("Falling back to API fetch...")
        except Exception as e:
            print(f"\nError loading CSV: {str(e)}")
            print("Falling back to API fetch...")

    try:
        ym = yf.Ticker(ticker)

        print(f"\nTicker: {ticker}")
        print(f"Target Date: {target_date}")
        print(f"Time Range: {start_time} - {end_time} EST")
        print("\nFetching intraday data...")

        data = ym.history(period="7d", interval="1m")

        if data.empty:
            print("\nNo intraday data available")
            return None

        import pytz
        est = pytz.timezone('US/Eastern')

        target_start = pd.Timestamp(f"{target_date} {start_time}:00", tz=est)
        target_end = pd.Timestamp(f"{target_date} {end_time}:00", tz=est)

        filtered_data = data[(data.index >= target_start) & (data.index <= target_end)]

        if filtered_data.empty:
            print(f"\nNo data found for {target_date} between {start_time} and {end_time} EST")
            date_data = data[data.index.date == pd.Timestamp(target_date).date()]
            if not date_data.empty:
                print(f"\nFound {len(date_data)} data points for {target_date}")
                return date_data
            return None

        print(f"\nSuccessfully retrieved {len(filtered_data)} data points")

        filename = f"YM_intraday_{target_date}_{start_time.replace(':', '')}-{end_time.replace(':', '')}.csv"
        filtered_data.to_csv(filename)
        print(f"\nData saved to: {filename}")

        return filtered_data

    except Exception as e:
        print(f"\nError fetching intraday data: {str(e)}")
        import traceback
        traceback.print_exc()
        return None
