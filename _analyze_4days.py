import os
import pandas as pd
import pytz
from TradingAlgoFast import run_trading_algo_fast, AlgoConfig

_EST = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.expanduser("~/Desktop/2YearsData/full_day")

config = AlgoConfig(
    warmup_minutes=12,
    steep_angle_threshold=70.0,
    proximity_points=15.0,
    min_reversal_minutes=10,
    min_entry_angle=30.0,
    partial_tp_pts=50.0,
)

days = ['2026-02-24', '2026-02-25', '2026-02-26', '2026-02-27']

for d in days:
    fname = f"CBOT_MINI_YM1_{d}.csv"
    fpath = os.path.join(_DATA_ROOT, fname)
    try:
        df = pd.read_csv(fpath, index_col=0, parse_dates=True)
        df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)

        start_ts = pd.Timestamp(f"{d} 09:30", tz=_EST)
        end_ts   = pd.Timestamp(f"{d} 10:30", tz=_EST)
        day_data = df[(df.index >= start_ts) & (df.index <= end_ts)]

        result = run_trading_algo_fast(day_data, d, "09:30", "10:30", config=config)

        trades = result[result['signal'].isin(['BUY', 'SELL'])]
        pl = result['pl'].iloc[-1]

        print(f"\n=== {d}  algo pl={pl:.0f}pts  signals={len(trades)} ===")
        for ts, row in trades.iterrows():
            t = ts.strftime('%H:%M')
            liq = row.get('is_liquidation', False)
            partial = row.get('partial_tp', False)
            print(f"  {t}  {row['signal']}  @{row['Close']:.0f}  liq={liq}  partial_tp={partial}")

    except Exception as e:
        print(f"\n=== {d}: ERROR {e} ===")
        import traceback; traceback.print_exc()
