"""Debug May 14 10:54am 6-contract buy"""
import pandas as pd
from pathlib import Path

# Load tracking CSV
csv_path = Path.home() / "Desktop" / "IB_Live" / "tracking" / "YM_tracking_DUO158495_2026-05-14_0930.csv"
df = pd.read_csv(csv_path, index_col=0, parse_dates=True)

# Focus on 10:50-11:00
window = df[(df.index >= '2026-05-14 10:50') & (df.index <= '2026-05-14 11:00')]

print("=== May 14, 2026 10:50-11:00 ===\n")
print(window[['Close', 'signal', 'position', 'session_pl']].to_string())

print("\n=== Signal Details ===")
signals = window[window['signal'].notna()]
for ts, row in signals.iterrows():
    print(f"\n{ts}: {row['signal']} @ {row['Close']:.0f}")
    print(f"  Position after: {row['position']}")
    print(f"  Session P/L: {row['session_pl']:.0f} pts")

print("\n=== Analysis ===")
print("Algo shows:")
print("  10:50am: SELL → flat")
print("  10:53am: BUY @ 50088 → long (should be 2 contracts)")
print("  10:58am: SELL → flat")
print("\nIB account shows:")
print("  10:54am: BUY 6 contracts @ 50098")
print("\nDiscrepancy:")
print("  - Algo: 2 contracts at 10:53am")
print("  - IB: 6 contracts at 10:54am (1 minute later, 10 pts higher)")
print("  - Extra 4 contracts = $200 loss (4 * 10 pts * $5)")
