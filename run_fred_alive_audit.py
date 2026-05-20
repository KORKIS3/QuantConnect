"""FRED Is Alive — Verification Audit. No optimization. Audit only."""
import os, time, random
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
    except: return None
    day_start = pd.Timestamp(f'{target_date} 09:30', tz=_EST)
    day_end = pd.Timestamp(f'{target_date} 16:59', tz=_EST)
    day_data = df[(df.index >= day_start) & (day_end >= df.index)]
    if len(day_data) < 15: return None
    if (day_data[["Open","High","Low","Close"]] <= 0).any().any(): return None
    if day_data["High"].max() == day_data["Low"].min(): return None
    try:
        engine = ExecutionEngine()
        result = engine.run_session(day_data)
        trades = result['trades']
        long_pl = sum(t['pl'] for t in trades if t['direction'] == 'LONG')
        short_pl = sum(t['pl'] for t in trades if t['direction'] == 'SHORT')
        largest_win = max((t['pl'] for t in trades), default=0)
        largest_loss = min((t['pl'] for t in trades), default=0)
        return {
            'date': target_date,
            'trades': len(trades),
            'day_pl': result['session_pl'],
            'win_loss': 'WIN' if result['session_pl'] > 0 else 'LOSS',
            'entry_count': len(trades),
            'exit_count': len(trades),
            'long_pl': long_pl,
            'short_pl': short_pl,
            'largest_win': largest_win,
            'largest_loss': largest_loss,
            'trade_details': trades,
        }
    except: return None

def main():
    files = sorted([f for f in os.listdir(_DATA_ROOT) if f.startswith('CBOT_MINI_YM1_') and f.endswith('.csv')])
    print(f"Running audit on {len(files)} files...")
    results = []; t0 = time.time()
    for i, fname in enumerate(files):
        r = run_day(fname)
        if r: results.append(r)
        if (i+1) % 100 == 0: print(f"  [{i+1}/{len(files)}] {len(results)} valid, {time.time()-t0:.0f}s")

    n = len(results)
    print(f"\nCompleted: {n} days in {time.time()-t0:.1f}s")

    # Export CSV
    csv_rows = [{k: v for k, v in r.items() if k != 'trade_details'} for r in results]
    pd.DataFrame(csv_rows).to_csv('fred_is_alive_daily_results.csv', index=False)

    # === RECONCILIATION ===
    total_daily_pl = sum(r['day_pl'] for r in results)
    total_trade_pl = sum(t['pl'] for r in results for t in r['trade_details'])
    total_trade_count = sum(r['trades'] for r in results)
    all_trades = [t for r in results for t in r['trade_details']]

    print(f"\n{'='*60}")
    print(f"RECONCILIATION")
    print(f"{'='*60}")
    print(f"  sum(daily P/L):    {total_daily_pl:+.1f}")
    print(f"  sum(trade P/L):    {total_trade_pl:+.1f}")
    print(f"  MATCH: {'YES' if abs(total_daily_pl - total_trade_pl) < 1.0 else 'NO — DISCREPANCY'}")
    print(f"  Total trades:      {total_trade_count}")
    print(f"  All trades list:   {len(all_trades)}")
    print(f"  MATCH: {'YES' if total_trade_count == len(all_trades) else 'NO'}")

    # Check for overlapping positions
    overlap_count = 0
    for r in results:
        trades = r['trade_details']
        for i in range(1, len(trades)):
            if trades[i]['entry_bar'] < trades[i-1]['exit_bar']:
                overlap_count += 1
    print(f"  Overlapping positions: {overlap_count}")

    # Check for orphan trades (entry without exit)
    orphan_count = sum(1 for t in all_trades if t['exit_bar'] <= t['entry_bar'])
    print(f"  Orphan trades (exit <= entry): {orphan_count}")

    # === 20-DAY RANDOM AUDIT ===
    sorted_by_pl = sorted(results, key=lambda r: r['day_pl'])
    best5 = sorted_by_pl[-5:]
    worst5 = sorted_by_pl[:5]
    breakeven = [r for r in sorted_by_pl if abs(r['day_pl']) < 20][:5]
    remaining = [r for r in results if r not in best5 and r not in worst5 and r not in breakeven]
    random.seed(42)
    random5 = random.sample(remaining, min(5, len(remaining)))

    audit_days = worst5 + breakeven + random5 + best5
    print(f"\n{'='*60}")
    print(f"20-DAY AUDIT (5 worst, 5 breakeven, 5 random, 5 best)")
    print(f"{'='*60}")

    for r in audit_days:
        print(f"\n  {r['date']} | P/L: {r['day_pl']:+.0f} | Trades: {r['trades']}")
        for t in r['trade_details']:
            print(f"    {t['direction']:<6} entry_bar={t['entry_bar']:<4} exit_bar={t['exit_bar']:<4} "
                  f"entry={t['entry_price']:.0f} exit={t['exit_price']:.0f} "
                  f"P/L={t['pl']:+.0f} held={t['bars_held']} reason={t['exit_reason']}")

    print(f"\n{'='*60}")
    print(f"SUMMARY")
    print(f"{'='*60}")
    print(f"  Days: {n}")
    print(f"  Total P/L: {total_daily_pl:+.0f}")
    print(f"  Avg/Day: {total_daily_pl/n:+.1f}")
    print(f"  Reconciliation: {'PASS' if abs(total_daily_pl - total_trade_pl) < 1.0 and overlap_count == 0 and orphan_count == 0 else 'FAIL'}")

if __name__ == "__main__":
    main()
