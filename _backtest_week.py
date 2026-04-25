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

days = ["2026-04-20", "2026-04-21", "2026-04-22", "2026-04-23", "2026-04-24"]

print(f"\n{'='*70}")
print(f"  Week of Apr 20-24, 2026 — Day Session Backtest (9:30-17:00)")
print(f"{'='*70}")
print(f"{'Date':<14} {'Day':<12} {'Signals':>8} {'P/L pts':>9} {'P/L $':>10}")
print(f"{'-'*70}")

week_pl = 0.0
for d in days:
    fpath = os.path.join(_DATA_ROOT, f"CBOT_MINI_YM1_{d}.csv")
    if not os.path.exists(fpath):
        dow = pd.Timestamp(d).day_name()
        print(f"{d:<14} {dow:<12} {'No data':>8}")
        continue
    try:
        df = pd.read_csv(fpath, index_col=0, parse_dates=True)
        df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
        start_ts = pd.Timestamp(f"{d} 09:30", tz=_EST)
        end_ts   = pd.Timestamp(f"{d} 17:00", tz=_EST)
        day_data = df[(df.index >= start_ts) & (df.index <= end_ts)]
        if len(day_data) < 15:
            print(f"{d:<14} {'No data':>8}")
            continue
        algo_df = run_trading_algo_fast(day_data, d, "09:30", "17:00", config=config)
        pl = _apply_trailing(algo_df, start_ts, end_ts, **trail) or 0.0
        week_pl += pl
        sigs = len(algo_df[algo_df["signal"].isin(["BUY","SELL"])])
        dow = pd.Timestamp(d).day_name()
        result = "WIN" if pl > 0 else ("LOSS" if pl < 0 else "FLAT")
        print(f"{d:<14} {dow:<12} {sigs:>8} {pl:>+9.0f} {pl*5:>+10.0f}   {result}")

        trades = algo_df[algo_df["signal"].isin(["BUY","SELL"])]
        for ts, row in trades.iterrows():
            liq = " (liq)" if row.get("is_liquidation") else ""
            print(f"               {ts.strftime('%H:%M')}  {row['signal']}  @{row['Close']:.0f}  pl={row['pl']:+.0f}{liq}")

    except Exception as e:
        print(f"{d}: ERROR {e}")

print(f"{'-'*70}")
print(f"{'WEEK TOTAL':<14} {'':12} {'':>8} {week_pl:>+9.0f} {week_pl*5:>+10.0f}")
print(f"{'='*70}")
