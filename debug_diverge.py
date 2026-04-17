"""Trace purple/blue values bar by bar around the divergence."""
import pandas as pd, pytz, numpy as np, os
from TradingAlgo import run_trading_algo, AlgoConfig
from TradingAlgoFast import run_trading_algo_fast

est = pytz.timezone("US/Eastern")
data_root = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "930_1130")
files = sorted([f for f in os.listdir(data_root) if f.endswith(".csv")])
fname = files[-10]
target_date = fname.replace("CBOT_MINI_YM1_","").replace(".csv","")
df = pd.read_csv(os.path.join(data_root, fname), index_col=0, parse_dates=True)
df.index = pd.to_datetime(df.index, utc=True).tz_convert(est)

config = AlgoConfig(warmup_minutes=12, steep_angle_threshold=70.0,
                    proximity_points=15.0, min_reversal_minutes=0, max_loss_per_trade=0)
orig = run_trading_algo(df, target_date, "09:30", "10:30", config=config)
fast = run_trading_algo_fast(df, target_date, "09:30", "10:30", config=config)

# Print every bar from 0 to 30 with purple and blue values
print(f"{'Bar':>3} {'Time':>6} {'High':>7} {'Low':>7} {'Close':>7} | "
      f"{'P_orig':>8} {'P_fast':>8} {'P_diff':>7} | "
      f"{'B_orig':>8} {'B_fast':>8} {'B_diff':>7} | Sig_O  Sig_F")
print("-" * 120)
for i in range(min(30, len(orig))):
    ts = orig.index[i].strftime("%H:%M")
    h = df.iloc[i]["High"]; l = df.iloc[i]["Low"]; c = df.iloc[i]["Close"]
    po = float(orig.iloc[i]["purple_ray"]); pf = float(fast.iloc[i]["purple_ray"])
    bo = float(orig.iloc[i]["blue_ray"]);   bf = float(fast.iloc[i]["blue_ray"])
    so = orig.iloc[i].get("signal", "")
    sf = fast.iloc[i].get("signal", "")
    pd_ = abs(po-pf); bd_ = abs(bo-bf)
    mark_p = " ***" if pd_ > 1 else ""
    mark_b = " ***" if bd_ > 1 else ""
    print(f"{i:>3} {ts:>6} {h:>7.0f} {l:>7.0f} {c:>7.0f} | "
          f"{po:>8.1f} {pf:>8.1f} {pd_:>7.1f}{mark_p} | "
          f"{bo:>8.1f} {bf:>8.1f} {bd_:>7.1f}{mark_b} | {so:>5}  {sf:>5}")
