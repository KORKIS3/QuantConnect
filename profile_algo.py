"""Profile the original algo to find the bottleneck."""
import cProfile, pstats, os
import pandas as pd, pytz
from TradingAlgoFast import run_trading_algo_fast as run_trading_algo, AlgoConfig

est = pytz.timezone("US/Eastern")
data_root = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")
files = sorted([f for f in os.listdir(data_root) if f.endswith(".csv")])
fname = files[-5]
target_date = fname.replace("CBOT_MINI_YM1_","").replace(".csv","")

df = pd.read_csv(os.path.join(data_root, fname), index_col=0, parse_dates=True)
df.index = pd.to_datetime(df.index, utc=True).tz_convert(est)
t0 = pd.Timestamp(f"{target_date} 09:30", tz=est)
t1 = pd.Timestamp(f"{target_date} 16:00", tz=est)
df = df[(df.index >= t0) & (df.index <= t1)]
print(f"Bars: {len(df)}")

config = AlgoConfig(warmup_minutes=12, steep_angle_threshold=70.0,
                    proximity_points=15.0, min_reversal_minutes=0, max_loss_per_trade=0)

profiler = cProfile.Profile()
profiler.enable()
algo_df = run_trading_algo(df, target_date, "09:30", "16:00", config=config)
profiler.disable()

stats = pstats.Stats(profiler)
stats.sort_stats("cumulative")
stats.print_stats(20)
