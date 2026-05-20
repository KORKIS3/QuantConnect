"""Full backtest of FRED Is Alive (all 4 layers) on all available days."""
import os, time
import pandas as pd, pytz
from execution_engine import ExecutionEngine

_EST = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")


def run_day(fname):
    target_date = fname.replace("CBOT_MINI_YM1_", "").replace(".csv", "")
    fpath = os.path.join(_DATA_ROOT, fname)
    try:
        df = pd.read_csv(fpath, index_col=0, parse_dates=True)
        df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
    except:
        return None
    day_start = pd.Timestamp(f'{target_date} 09:30', tz=_EST)
    day_end = pd.Timestamp(f'{target_date} 16:59', tz=_EST)
    day_data = df[(df.index >= day_start) & (day_end >= df.index)]
    if len(day_data) < 15:
        return None
    if (day_data[["Open", "High", "Low", "Close"]] <= 0).any().any():
        return None
    if day_data["High"].max() == day_data["Low"].min():
        return None

    try:
        engine = ExecutionEngine()
        result = engine.run_session(day_data)
        return {
            'date': target_date,
            'pl': result['session_pl'],
            'trades': len(result['trades']),
            'final_state': result['final_state'],
            'trade_details': result['trades'],
        }
    except Exception as e:
        return None


def main():
    files = sorted([f for f in os.listdir(_DATA_ROOT)
                    if f.startswith('CBOT_MINI_YM1_') and f.endswith('.csv')])
    print(f"Running FRED Is Alive backtest on {len(files)} files...")

    results = []
    t0 = time.time()
    for i, fname in enumerate(files):
        r = run_day(fname)
        if r:
            results.append(r)
        if (i + 1) % 100 == 0:
            print(f"  [{i+1}/{len(files)}] {len(results)} valid, {time.time()-t0:.0f}s")

    n = len(results)
    elapsed = time.time() - t0
    print(f"\nCompleted: {n} days in {elapsed:.1f}s")

    # Results
    pls = [r['pl'] for r in results]
    total_pl = sum(pls)
    wins = sum(1 for p in pls if p > 0)
    losses = sum(1 for p in pls if p <= 0)
    all_trades = [t for r in results for t in r['trade_details']]
    trade_pls = [t['pl'] for t in all_trades]

    print(f"\n{'='*60}")
    print(f"FRED IS ALIVE — BACKTEST RESULTS ({n} days)")
    print(f"{'='*60}")
    print(f"Total P/L:      {total_pl:+.0f} pts")
    print(f"Avg/Day:        {total_pl/n:+.1f} pts")
    print(f"Win Days:       {wins} ({wins/n*100:.0f}%)")
    print(f"Lose Days:      {losses} ({losses/n*100:.0f}%)")
    print(f"Median Day:     {sorted(pls)[n//2]:+.0f}")
    print(f"Best Day:       {max(pls):+.0f}")
    print(f"Worst Day:      {min(pls):+.0f}")
    print(f"\nTotal Trades:   {len(all_trades)}")
    print(f"Avg Trades/Day: {len(all_trades)/n:.1f}")
    if trade_pls:
        print(f"Avg P/L/Trade:  {sum(trade_pls)/len(trade_pls):+.1f}")
        print(f"Win Trades:     {sum(1 for p in trade_pls if p > 0)} ({sum(1 for p in trade_pls if p > 0)/len(trade_pls)*100:.0f}%)")
        print(f"Best Trade:     {max(trade_pls):+.0f}")
        print(f"Worst Trade:    {min(trade_pls):+.0f}")

    # Exit reasons
    print(f"\nExit Reasons:")
    reasons = {}
    for t in all_trades:
        r = t['exit_reason']
        if r not in reasons:
            reasons[r] = {'count': 0, 'pl': 0}
        reasons[r]['count'] += 1
        reasons[r]['pl'] += t['pl']
    for r, stats in sorted(reasons.items(), key=lambda x: x[1]['pl']):
        print(f"  {r:<20} {stats['count']:>5} trades  {stats['pl']:>+8.0f} pts")

    # Direction
    longs = [t for t in all_trades if t['direction'] == 'LONG']
    shorts = [t for t in all_trades if t['direction'] == 'SHORT']
    print(f"\nDirection:")
    print(f"  LONG:  {len(longs)} trades, {sum(t['pl'] for t in longs):>+8.0f} pts")
    print(f"  SHORT: {len(shorts)} trades, {sum(t['pl'] for t in shorts):>+8.0f} pts")

    # Hold duration
    if all_trades:
        holds = [t['bars_held'] for t in all_trades]
        print(f"\nHold Duration:")
        print(f"  Avg: {sum(holds)/len(holds):.0f} bars")
        print(f"  Median: {sorted(holds)[len(holds)//2]} bars")


if __name__ == "__main__":
    main()
