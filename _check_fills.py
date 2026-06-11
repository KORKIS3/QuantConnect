import pandas as pd
import os

# Use the raw data file for June 10
data_path = os.path.expanduser(r"~\Desktop\2YearsData\full_day\CBOT_MINI_YM1_2026-06-10.csv")
if not os.path.exists(data_path):
    # Try the xlsx tracking file
    data_path = os.path.expanduser(r"~\Desktop\IB_Live\tracking\YM_raw_DUO158495_2026-06-10.xlsx")
    df = pd.read_excel(data_path, index_col=0, parse_dates=True)
else:
    df = pd.read_csv(data_path, index_col=0, parse_dates=True)

print(f"Loaded {len(df)} bars from {data_path}")
print(f"Columns: {list(df.columns[:6])}")
print(f"Index range: {df.index[0]} to {df.index[-1]}")

# Resample to 1-min if needed
if len(df) > 500:
    # Already minute data
    pass

signal_times = ['10:01','10:07','10:16','10:34','10:45','11:02','11:06','11:21','11:30','12:38','12:42','13:21','13:36','13:47','13:53','14:01','14:08','15:04','15:05','15:32','15:49']
ib_fills =     [50734, 50754, 50709, 50663, 50586, 50504, 50467, 50367, 50399, 50391, 50337, 50219, 50169, 50223, 50195, 50309, 50311, 50145, 50116, 50073, 50061]
algo_sigs =    [50707, 50763, 50682, 50666, 50580, 50495, 50468, 50372, 50391, 50400, 50345, 50228, 50175, 50246, 50193, 50310, 50317, 50155, 50111, 50071, 50063]

print(f"\n{'TIME':<7} {'CLOSE':<8} {'NEXT_O':<8} {'ALGO':<8} {'IB':<8} {'|Cl-IB|':<8} {'|Nx-IB|':<8} {'BETTER'}")
print("-" * 72)

total_close_diff = 0
total_next_diff = 0
count = 0

for i, t in enumerate(signal_times):
    hour, minute = int(t.split(':')[0]), int(t.split(':')[1])
    matches = df[(df.index.hour == hour) & (df.index.minute == minute)]
    if matches.empty:
        print(f"{t:<7} -- NO DATA --")
        continue
    bar_idx = df.index.get_loc(matches.index[0])
    bar_close = float(df.iloc[bar_idx]['Close'])
    next_open = float(df.iloc[bar_idx + 1]['Open']) if bar_idx + 1 < len(df) else None
    ib_price = ib_fills[i]
    
    diff_close = abs(bar_close - ib_price)
    diff_next = abs(next_open - ib_price) if next_open else 999
    
    total_close_diff += diff_close
    if next_open:
        total_next_diff += diff_next
    count += 1
    
    better = "<-- next" if diff_next < diff_close else ""
    no = f"{next_open:.0f}" if next_open else "N/A"
    print(f"{t:<7} {bar_close:<8.0f} {no:<8} {algo_sigs[i]:<8} {ib_price:<8} {diff_close:<8.0f} {diff_next:<8.0f} {better}")

print("-" * 72)
if count:
    print(f"AVG |BarClose - IB fill|:  {total_close_diff/count:.1f} pts")
    print(f"AVG |NextOpen - IB fill|:  {total_next_diff/count:.1f} pts")
    gap = total_close_diff/count - total_next_diff/count
    if gap > 0:
        print(f"\n--> Next bar open is {gap:.1f} pts closer to IB fill on average. YES it would help.")
    else:
        print(f"\n--> Bar close is already closer. Next open would NOT help.")
