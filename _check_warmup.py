import os, pandas as pd, pytz
_EST = pytz.timezone("US/Eastern")
DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "930_1000")

dates = {
    "2026-02-03": "BAD - algo BUY, should SELL",
    "2026-02-04": "BAD - algo BUY, should SELL",
    "2026-02-05": "OK  - algo BUY, should BUY",
    "2026-02-09": "OK  - algo SELL correctly",
    "2026-02-11": "OK  - algo SELL correctly",
    "2026-02-18": "BAD - algo BUY, should SELL first",
}

for date, label in dates.items():
    df = pd.read_csv(os.path.join(DATA_ROOT, f"CBOT_MINI_YM1_{date}.csv"), index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
    w = df.iloc[:12]
    open_p  = float(w["Close"].iloc[0])
    close_p = float(w["Close"].iloc[-1])
    high    = float(w["High"].max())
    low     = float(w["Low"].min())
    change  = close_p - open_p
    # Trend strength: close vs open as % of range
    rng = high - low
    trend_pct = change / rng * 100 if rng > 0 else 0
    direction = "DOWN" if change < 0 else "UP"
    print(f"{date} [{label}]")
    print(f"  Change={change:+.0f}  Range={rng:.0f}  Trend%={trend_pct:+.0f}%  Direction={direction}")
    print(f"  First bar close={open_p:.0f}  Bar12 close={close_p:.0f}")
    print()
