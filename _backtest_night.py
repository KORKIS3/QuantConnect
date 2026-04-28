"""Focused overnight backtest: 04:00-09:00 and 03:00-09:00 ET.
Same config and rules as day session — fresh start each window."""
import os, time
import pandas as pd, pytz, numpy as np
from TradingAlgoFast import run_trading_algo_fast, AlgoConfig

_EST       = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")

config = AlgoConfig(
    warmup_minutes=12,
    steep_angle_threshold=70.0,
    proximity_points=15.0,
    min_reversal_minutes=0,
    min_entry_angle=30.0,
    partial_tp_pts=50.0,
    spike_profit_pts=100.0,
    spike_profit_bars=5,
    wm_shield_distance=12.0,
)

csv_files = sorted([f for f in os.listdir(_DATA_ROOT)
                    if f.startswith("CBOT_MINI_YM1_") and f.endswith(".csv")])

WINDOWS = [("04:00", "09:00"), ("03:00", "09:00")]

t_start = time.time()
print(f"Running {len(csv_files)} nights across {len(WINDOWS)} windows...\n")

for (start_t, end_t) in WINDOWS:
    pl_total = 0.0; winners = 0; losers = 0; days = 0; daily_pls = []

    for i, fname in enumerate(csv_files[:-1]):
        date_str      = fname.replace("CBOT_MINI_YM1_", "").replace(".csv", "")
        next_fname    = csv_files[i + 1]
        next_date_str = next_fname.replace("CBOT_MINI_YM1_", "").replace(".csv", "")
        try:
            df_cur  = pd.read_csv(os.path.join(_DATA_ROOT, fname),      index_col=0, parse_dates=True)
            df_next = pd.read_csv(os.path.join(_DATA_ROOT, next_fname), index_col=0, parse_dates=True)
            df_cur.index  = pd.to_datetime(df_cur.index,  utc=True).tz_convert(_EST)
            df_next.index = pd.to_datetime(df_next.index, utc=True).tz_convert(_EST)

            # Window is entirely on the next calendar day
            win_start = pd.Timestamp(f"{next_date_str} {start_t}", tz=_EST)
            win_end   = pd.Timestamp(f"{next_date_str} {end_t}",   tz=_EST)

            df_w = pd.concat([df_cur, df_next]).sort_index()
            df_w = df_w[(df_w.index >= win_start) & (df_w.index <= win_end)]
            df_w = df_w[~df_w.index.duplicated(keep="first")]

            if len(df_w) < 20:
                continue

            algo_df = run_trading_algo_fast(df_w, next_date_str, start_t, end_t, config=config)
            pl = float(algo_df["session_pl"].iloc[-1])

            pl_total += pl; days += 1
            winners  += 1 if pl > 0 else 0
            losers   += 1 if pl <= 0 else 0
            daily_pls.append(pl)

        except Exception:
            continue

    wr  = winners / days * 100 if days else 0
    avg = np.mean(daily_pls) if daily_pls else 0
    usd = pl_total * 5
    print(f"=== {start_t} - {end_t} ET  ({days} sessions) ===")
    print(f"  Win: {winners}  Lose: {losers}  Win%: {wr:.1f}%")
    print(f"  Total Pts: {pl_total:+.0f}  P/L USD: ${usd:+,.0f}  Avg/Session: {avg:+.1f}")
    print()

print(f"Done in {time.time()-t_start:.1f}s")
