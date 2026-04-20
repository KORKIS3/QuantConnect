"""validate_sim_days.py — compare sim trades vs algo on the same days."""
import os
import pandas as pd
import pytz
from TradingAlgoFast import run_trading_algo_fast, AlgoConfig

_EST = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "930_1000")
_SIM_CSV   = os.path.join("SIM", "sim_trade_analysis.csv")

CONFIG = AlgoConfig(warmup_minutes=12, steep_angle_threshold=70.0,
                    proximity_points=15.0, min_reversal_minutes=10)

def run_algo_day(date_str):
    fname = os.path.join(_DATA_ROOT, f"CBOT_MINI_YM1_{date_str}.csv")
    if not os.path.exists(fname): return {"error": "no data"}
    df = pd.read_csv(fname, index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
    try:
        result = run_trading_algo_fast(df, date_str, "09:30", "10:30", config=CONFIG)
    except Exception as e:
        return {"error": str(e)}
    signals = result[result["signal"].isin(["BUY", "SELL"])]
    final_pl = float(result["pl"].iloc[-1])
    trades = []
    for ts, row in signals.iterrows():
        sig = row["signal"]; price = float(row["buy_price"] if sig == "BUY" else row["sell_price"])
        liq = " [LIQ]" if row["is_liquidation"] else ""
        trades.append(f"{ts.strftime('%H:%M')} {sig} @{int(price)}{liq}")
    return {"algo_pl_pts": round(final_pl, 1), "algo_pl_usd": round(final_pl*5*2, 0),
            "algo_trades": len(signals), "algo_signals": trades}

def main():
    sim = pd.read_csv(_SIM_CSV)
    print(f"\n{'='*85}")
    print(f"{'DATE':<12} {'SIM PTS':>8} {'ALGO PTS':>9} {'GAP':>7} {'SIM T':>6} {'ALGO T':>7}")
    print(f"{'='*85}")
    rows = []; total_sim = 0; total_algo = 0
    for _, row in sim.iterrows():
        date_str = str(row["date"])
        sim_pts  = int(str(row["total_pl_pts"]).replace("+","").replace(",",""))
        sim_trades = int(row["num_trades"])
        algo = run_algo_day(date_str)
        if "error" in algo:
            print(f"{date_str:<12} {sim_pts:>+8} {'N/A':>9} {'N/A':>7} {sim_trades:>6} {'N/A':>7}  ← {algo['error']}")
            continue
        algo_pts = algo["algo_pl_pts"]; algo_trades = algo["algo_trades"]
        gap = algo_pts - sim_pts
        total_sim += sim_pts; total_algo += algo_pts
        print(f"{date_str:<12} {sim_pts:>+8} {algo_pts:>+9.0f} {gap:>+7.0f} {sim_trades:>6} {algo_trades:>7}")
        print(f"  ALGO: {' → '.join(algo['algo_signals']) if algo['algo_signals'] else 'no signals'}")
        rows.append({"date": date_str, "sim_pts": sim_pts, "algo_pts": algo_pts, "gap_pts": gap})
    print(f"{'='*85}")
    n = len(rows)
    print(f"{'TOTAL':<12} {total_sim:>+8} {total_algo:>+9.0f} {total_algo-total_sim:>+7.0f}")
    print(f"Avg sim: {total_sim/n:>+.1f}  Avg algo: {total_algo/n:>+.1f}  Avg gap: {(total_algo-total_sim)/n:>+.1f} pts/day")
    pd.DataFrame(rows).to_csv("SIM/validation_results.csv", index=False)
    print(f"\nSaved to SIM/validation_results.csv")

if __name__ == "__main__":
    main()
