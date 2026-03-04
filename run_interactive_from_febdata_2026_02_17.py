import os
import pandas as pd
import pytz
from plotFigure import plot_intraday_data

if __name__ == '__main__':
    desktop = os.path.expanduser('~/Desktop/FebData')
    fname = 'feb 17 - now I want 30 minutes of data 9_30 to 10_00 am by....csv'
    fp = os.path.join(desktop, fname)
    print('Loading', fp)
    df_raw = pd.read_csv(fp)
    print('Columns detected:', list(df_raw.columns))

    # Try to find a datetime column
    datetime_cols = [c for c in df_raw.columns if c.lower() in ('datetime', 'date', 'time', 'timestamp')]
    if datetime_cols:
        dt_col = datetime_cols[0]
    else:
        dt_col = df_raw.columns[0]

    print('Using datetime column:', dt_col)
    # If the datetime column contains only times (no date), attach the target date
    target_date = '2026-02-17'
    sample = str(df_raw[dt_col].iat[0]) if len(df_raw) > 0 else ''
    if sample and (':' in sample) and not any(ch.isdigit() for ch in sample.split()[0] if ch == '/'):
        # build full datetimes from the time strings
        df_raw[dt_col] = df_raw[dt_col].astype(str).str.strip()
        df_raw[dt_col] = pd.to_datetime(target_date + ' ' + df_raw[dt_col], errors='coerce')
    else:
        df_raw[dt_col] = pd.to_datetime(df_raw[dt_col], errors='coerce')

    df_raw = df_raw.dropna(subset=[dt_col])
    df_raw = df_raw.set_index(dt_col)

    est = pytz.timezone('US/Eastern')
    if df_raw.index.tz is None:
        df_raw.index = df_raw.index.tz_localize(est)
    else:
        df_raw.index = df_raw.index.tz_convert(est)

    df = df_raw.copy()

# Ensure numeric columns are numeric
cols = ['Open', 'High', 'Low', 'Close', 'Volume']
for c in cols:
    if c in df.columns:
        # remove thousands separators then coerce
        df[c] = df[c].astype(str).str.replace(',', '').replace('', 'nan')
        df[c] = pd.to_numeric(df[c], errors='coerce')

# Drop rows missing critical numeric data
df = df.dropna(subset=['Close'])

print('Data rows after cleanup:', len(df))
plot_intraday_data(df, '2026-02-17', '09:30', '10:00')
