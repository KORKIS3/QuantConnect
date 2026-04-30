import os, pandas as pd, pytz
from TradingAlgoFast import run_trading_algo_fast, AlgoConfig

_EST = pytz.timezone("US/Eastern")
date    = "2026-04-29"
start_t = "09:30"
end_t   = "17:00"

track_path = os.path.expanduser("~/Desktop/IB_Live/tracking/YM_tracking_2026-04-29.csv")
df = pd.read_csv(track_path, index_col=0, parse_dates=True)
df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)

ds = pd.Timestamp(f"{date} {start_t}", tz=_EST)
de = pd.Timestamp(f"{date} {end_t}",   tz=_EST)
df = df[(df.index >= ds) & (df.index <= de)]

config = AlgoConfig(warmup_minutes=12, steep_angle_threshold=70.0,
                    proximity_points=15.0, min_reversal_minutes=0,
                    min_entry_angle=30.0)
algo_df = run_trading_algo_fast(df, date, start_t, end_t, config=config)

# Print bars 10:08 to 10:35 with ray values and signals
window = algo_df.between_time("10:08", "10:35")
cols = ["Close", "purple_ray", "blue_ray", "purple_angle", "blue_angle", "signal", "position", "session_pl"]
print(f"\n{'Time':<8} {'Close':>7} {'Purple':>7} {'Blue':>7} {'P_ang':>6} {'B_ang':>6} {'Signal':<8} {'Pos':<6} {'PL':>6}")
print("-" * 75)
for ts, row in window.iterrows():
    sig = row.get("signal", "") or ""
    print(f"{ts.strftime('%H:%M'):<8} {row['Close']:>7.0f} {row['purple_ray']:>7.0f} {row['blue_ray']:>7.0f} "
          f"{row['purple_angle']:>6.1f} {row['blue_angle']:>6.1f} {sig:<8} {str(row['position']):<6} {row['session_pl']:>6.0f}")
