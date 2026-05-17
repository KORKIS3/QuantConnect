import os
import csv
import time

from Backtest2Year import _process_day

data_root = os.path.expanduser('~/Desktop/2YearsData/full_day')
files = sorted([
    f for f in os.listdir(data_root)
    if f.startswith('CBOT_MINI_YM1_') and f.endswith('.csv')
])

total_files = len(files)
output_csv = "full_backtest_results.csv"

with open(output_csv, mode='w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['Index', 'Filename', 'Date', 'Total_Pts', 'Trades', 'Win', 'Loss'])

processed = 0
skipped = 0
failed = 0
start_time = time.time()

for i, fname in enumerate(files):
    try:
        t0 = time.time()
        target_date, result = _process_day(fname)
        elapsed = time.time() - t0

        # Sum P/L across the full day (17:00 end time)
        day_pl_list = result.get("17:00")
        if day_pl_list is None:
            skipped += 1
            status = "SKIP"
        else:
            processed += 1
            total_pts = sum(day_pl_list)
            num_trades = len(day_pl_list)
            wins = sum(1 for p in day_pl_list if p > 0)
            losses = sum(1 for p in day_pl_list if p <= 0)
            status = "OK"

            with open(output_csv, mode='a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([i+1, fname, target_date, total_pts, num_trades, wins, losses])

    except Exception as e:
        elapsed = time.time() - t0
        failed += 1
        status = f"ERROR: {e}"

    print(f"[{i+1}/{total_files}] {fname} -> {status} ({elapsed:.2f}s)")

end_time = time.time()
print("\nBacktest Complete!")
print(f"Total files: {total_files}")
print(f"Processed: {processed}")
print(f"Skipped: {skipped}")
print(f"Failed: {failed}")
print(f"Elapsed time: {end_time - start_time:.2f}s")
print(f"Daily results logged to {output_csv}")
