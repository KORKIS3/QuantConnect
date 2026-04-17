import pandas as pd, pytz, os
from TradingAlgo import run_trading_algo, AlgoConfig
from Backtest2Year import run_variant

est = pytz.timezone("US/Eastern")
data_root = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "930_1000")

# Pick a day with multiple signals
for f in sorted(os.listdir(data_root)):
    fpath = os.path.join(data_root, f)
    target_date = f.replace("CBOT_MINI_YM1_","").replace(".csv","")
    df = pd.read_csv(fpath, index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index, utc=True).tz_convert(est)
    if len(df) < 10:
        continue
    config = AlgoConfig(warmup_minutes=7, steep_angle_threshold=65.0, proximity_points=15.0)
    try:
        algo_df = run_trading_algo(df, target_date, "09:30", "10:30", config=config)
    except Exception:
        continue
    signals = algo_df[algo_df["signal"].isin(["BUY","SELL"])]
    if len(signals) >= 3:
        print(f"Date: {target_date}  Signals: {len(signals)}")
        for ts, row in signals.iterrows():
            sig = row["signal"]
            price = float(row["buy_price"] if sig=="BUY" else row["sell_price"])
            pl = float(row["pl"])
            print(f"  {ts.strftime('%H:%M')}  {sig}  @ {int(price)}  pl={pl:+.0f}")

        # Test filter
        b  = run_variant(algo_df, "baseline")
        p  = run_variant(algo_df, "min_profit", min_profit=30)
        t  = run_variant(algo_df, "min_time",   min_minutes=10)
        print(f"\nbaseline:   trades={b['trades']}  pl={b['pl_pts']:+.0f}")
        print(f"min_profit: trades={p['trades']}  pl={p['pl_pts']:+.0f}")
        print(f"min_time:   trades={t['trades']}  pl={t['pl_pts']:+.0f}")
        break
