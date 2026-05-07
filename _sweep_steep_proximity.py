"""_sweep_steep_proximity.py
Tests steep_line_proximity (0, 5, 10, 15, 20 pts) crossed with
steep_line_reentry (False, True).

proximity  — suppress steep line reversal AND trailing stop liquidation
             when close is within N pts of the original primary ray
reentry    — allow steep line cross to trigger a fresh entry when flat
             (only after first_trade_done, respects proximity filter too)

Scenarios tested:
  baseline          : proximity=0, reentry=False
  prox=5..20        : proximity=N, reentry=False
  reentry only      : proximity=0, reentry=True
  prox=5..20+reentry: proximity=N, reentry=True

Run: python _sweep_steep_proximity.py --skip-download
"""
import argparse, os, time
from concurrent.futures import ProcessPoolExecutor, as_completed
import pandas as pd, pytz
from TradingAlgoFast import AlgoConfig, run_trading_algo_fast

_EST        = pytz.timezone("US/Eastern")
_DATA_ROOT  = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")
_START_TIME = "09:30"
_END_TIME   = "17:00"

PROXIMITIES = [0.0, 5.0, 10.0, 15.0, 20.0]
REENTRIES   = [False, True]


def _base_config(proximity: float, reentry: bool) -> AlgoConfig:
    return AlgoConfig(
        warmup_minutes=12,
        steep_angle_threshold=70.0,
        proximity_points=15.0,
        min_reversal_minutes=0,
        min_entry_angle=30.0,
        partial_tp_pts=50.0,
        spike_profit_pts=100.0,
        spike_profit_bars=5,
        wm_shield_distance=12.0,
        steep_line_proximity=proximity,
        steep_line_reentry=reentry,
    )


def _run_day(args):
    fname, proximity, reentry = args
    target_date = fname.replace("CBOT_MINI_YM1_", "").replace(".csv", "")
    fpath = os.path.join(_DATA_ROOT, fname)
    try:
        df = pd.read_csv(fpath, index_col=0, parse_dates=True)
        df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
        ds = pd.Timestamp(f"{target_date} {_START_TIME}", tz=_EST)
        de = pd.Timestamp(f"{target_date} {_END_TIME}",   tz=_EST)
        day_data = df[(df.index >= ds) & (df.index <= de)]
        if len(day_data) < 15:
            return proximity, reentry, target_date, None
        config = _base_config(proximity, reentry)
        algo_df = run_trading_algo_fast(day_data, target_date, _START_TIME, _END_TIME, config=config)
        sliced = algo_df[(algo_df.index >= ds) & (algo_df.index <= de)]
        if len(sliced) < 2:
            return proximity, reentry, target_date, None
        pl = float(sliced["session_pl"].iloc[-1])
        return proximity, reentry, target_date, pl if pl != 0.0 else None
    except Exception:
        return proximity, reentry, target_date, None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-download", action="store_true")
    args = parser.parse_args()

    csv_files = sorted([f for f in os.listdir(_DATA_ROOT)
                        if f.startswith("CBOT_MINI_YM1_") and f.endswith(".csv")])
    total = len(csv_files)
    print(f"\nSweeping steep_line_proximity x reentry over {total} days ...\n")

    tasks = [(f, p, r) for r in REENTRIES for p in PROXIMITIES for f in csv_files]
    results = {(p, r): [] for r in REENTRIES for p in PROXIMITIES}

    t0 = time.time()
    with ProcessPoolExecutor() as ex:
        futures = {ex.submit(_run_day, t): t for t in tasks}
        done = 0
        for fut in as_completed(futures):
            proximity, reentry, date_str, pl = fut.result()
            if pl is not None:
                results[(proximity, reentry)].append(pl)
            done += 1
            if done % 1000 == 0:
                print(f"  {done}/{len(tasks)} done ...")

    elapsed = time.time() - t0
    print(f"\nCompleted in {elapsed:.1f}s\n")

    hdr = f"{'Scenario':<26}  {'Days':>5}  {'Total Pts':>10}  {'Avg/Day':>8}  {'vs Base':>8}  {'Win%':>6}  {'Win Days':>9}  {'Lose Days':>9}"
    print(hdr)
    print("-" * len(hdr))

    baseline_avg = None
    for r in REENTRIES:
        for p in PROXIMITIES:
            pls = results[(p, r)]
            if not pls:
                continue
            total_pts = sum(pls) * 2
            avg_day   = total_pts / len(pls)
            win_days  = sum(1 for x in pls if x > 0)
            lose_days = sum(1 for x in pls if x <= 0)
            win_pct   = 100.0 * win_days / len(pls)
            reentry_tag = "+reentry" if r else "        "
            prox_tag    = f"prox={p:.0f}" if p > 0 else "base    "
            label = f"{prox_tag} {reentry_tag}"
            delta = f"{avg_day - baseline_avg:+.1f}" if baseline_avg is not None else "  ---  "
            if baseline_avg is None:
                baseline_avg = avg_day
            print(f"{label:<26}  {len(pls):>5}  {total_pts:>10.0f}  {avg_day:>8.1f}  {delta:>8}  {win_pct:>5.1f}%  {win_days:>9}  {lose_days:>9}")
        print()


if __name__ == "__main__":
    main()
