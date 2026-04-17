"""Debug the 2 mismatched days."""
import pandas as pd, pytz, os, numpy as np
from TradingAlgo import run_trading_algo, AlgoConfig
from TradingAlgoFast import run_trading_algo_fast

est = pytz.timezone("US/Eastern")
data_root = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "930_1130")
config = AlgoConfig(warmup_minutes=12, steep_angle_threshold=70.0,
                    proximity_points=15.0, min_reversal_minutes=0, max_loss_per_trade=0)

for target_date in ["2024-11-22", "2025-03-27"]:
    fname = f"CBOT_MINI_YM1_{target_date}.csv"
    fpath = os.path.join(data_root, fname)
    if not os.path.exists(fpath):
        print(f"File not found: {fname}"); continue

    df = pd.read_csv(fpath, index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index, utc=True).tz_convert(est)

    orig = run_trading_algo(df, target_date, "09:30", "10:30", config=config)
    fast = run_trading_algo_fast(df, target_date, "09:30", "10:30", config=config)

    print(f"\n=== {target_date} ===")

    # Find mismatched signals
    orig_sigs = [(ts, row["signal"], bool(row.get("is_liquidation", False)))
                 for ts, row in orig.iterrows() if row.get("signal") in ("BUY","SELL")]
    fast_sigs = [(ts, row["signal"], bool(row.get("is_liquidation", False)))
                 for ts, row in fast.iterrows() if row.get("signal") in ("BUY","SELL")]

    print("Original:")
    for ts, sig, liq in orig_sigs:
        print(f"  {ts.strftime('%H:%M')} {sig} liq={liq}")
    print("Fast:")
    for ts, sig, liq in fast_sigs:
        print(f"  {ts.strftime('%H:%M')} {sig} liq={liq}")

    # Compare ray values around mismatch times
    if target_date == "2024-11-22":
        check_times = ["04:47", "04:48", "04:49", "04:50"]
    else:
        check_times = ["05:59", "06:00", "06:01", "06:02"]

    print("\nRay comparison at mismatch bars:")
    for i in range(len(orig)):
        ts = orig.index[i].strftime("%H:%M")
        if ts in check_times:
            po = float(orig.iloc[i]["purple_ray"]); pf = float(fast.iloc[i]["purple_ray"])
            bo = float(orig.iloc[i]["blue_ray"]);   bf = float(fast.iloc[i]["blue_ray"])
            co = float(orig.iloc[i]["Close"])
            so = orig.iloc[i].get("signal", ""); sf = fast.iloc[i].get("signal", "")
            print(f"  {ts}: close={co:.0f} P_orig={po:.1f} P_fast={pf:.1f} diff={abs(po-pf):.1f} "
                  f"B_orig={bo:.1f} B_fast={bf:.1f} diff={abs(bo-bf):.1f} "
                  f"sig_o={so} sig_f={sf}")
