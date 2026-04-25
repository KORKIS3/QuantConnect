import os
import pandas as pd
import pytz
from TradingAlgoFast import run_trading_algo_fast, AlgoConfig
from _sweep_trailing import _apply_trailing

_EST = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.expanduser("~/Desktop/2YearsData/full_day")

config = AlgoConfig(
    warmup_minutes=12, steep_angle_threshold=70.0, proximity_points=15.0,
    min_reversal_minutes=0, min_entry_angle=30.0, partial_tp_pts=50.0,
    spike_profit_pts=99999.0,
)
trail = dict(threshold=50, base_angle=50, mid_angle=60, high_angle=70,
             mid_profit=100, high_profit=150, lock_anchor=True, progressive=False)

# This week: Mon Apr 21 - Fri Apr 25
days = ["2026-04-21", "2026-04-22", "2026-04-23", "2026-04-24", "2026-04-25"]

print(f"\n{'='*65}")
print(f"{'Date':<12} {'Session':<10} {'Signals':>8} {'P/L pts':>9} {'P/L $':>10}")
print(f"{'='*65}")

week_day_pl = 0.0
week_night_pl = 0.0

for d in days:
    fpath = os.path.join(_DATA_ROOT, f"CBOT_MINI_YM1_{d}.csv")
    if not os.path.exists(fpath):
        print(f"{d:<12} {'N/A':<10} (no data)")
        continue
    try:
        df = pd.read_csv(fpath, index_col=0, parse_dates=True)
        df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)

        # Day session
        start_ts = pd.Timestamp(f"{d} 09:30", tz=_EST)
        end_ts   = pd.Timestamp(f"{d} 17:00", tz=_EST)
        day_data = df[(df.index >= start_ts) & (df.index <= end_ts)]
        if len(day_data) >= 15:
            algo_df = run_trading_algo_fast(day_data, d, "09:30", "17:00", config=config)
            pl = _apply_trailing(algo_df, start_ts, end_ts, **trail) or 0.0
            sigs = len(algo_df[algo_df["signal"].isin(["BUY","SELL"])])
            week_day_pl += pl
            print(f"{d:<12} {'Day':10} {sigs:>8} {pl:>+9.0f} {pl*5:>+10.0f}")

        # Night session (previous evening 18:00 to this morning 09:00)
        prev_d = (pd.Timestamp(d) - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        prev_path = os.path.join(_DATA_ROOT, f"CBOT_MINI_YM1_{prev_d}.csv")
        if os.path.exists(prev_path):
            prev_df = pd.read_csv(prev_path, index_col=0, parse_dates=True)
            prev_df.index = pd.to_datetime(prev_df.index, utc=True).tz_convert(_EST)
            night_start = pd.Timestamp(f"{prev_d} 18:00", tz=_EST)
            night_end   = pd.Timestamp(f"{d} 09:00", tz=_EST)
            night_data  = pd.concat([
                prev_df[prev_df.index >= night_start],
                df[df.index <= night_end]
            ])
            if len(night_data) >= 15:
                algo_df = run_trading_algo_fast(night_data, d, "18:00", "09:00", config=config)
                pl = _apply_trailing(algo_df, night_start, night_end, **trail) or 0.0
                sigs = len(algo_df[algo_df["signal"].isin(["BUY","SELL"])])
                week_night_pl += pl
                print(f"{d:<12} {'Night':10} {sigs:>8} {pl:>+9.0f} {pl*5:>+10.0f}")

    except Exception as e:
        print(f"{d}: ERROR {e}")

print(f"{'='*65}")
print(f"{'WEEK TOTAL':<12} {'Day':10} {'':>8} {week_day_pl:>+9.0f} {week_day_pl*5:>+10.0f}")
print(f"{'WEEK TOTAL':<12} {'Night':10} {'':>8} {week_night_pl:>+9.0f} {week_night_pl*5:>+10.0f}")
print(f"{'COMBINED':<12} {'':10} {'':>8} {week_day_pl+week_night_pl:>+9.0f} {(week_day_pl+week_night_pl)*5:>+10.0f}")
