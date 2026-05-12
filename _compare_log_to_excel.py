"""
Compare IB log orders to Excel tracking data
"""
import pandas as pd
import re

# Read Excel file
excel_df = pd.read_excel(r'C:\Users\Administrator\Desktop\IB_Live\tracking\YM_raw_2026-05-11.xlsx')

print("=" * 80)
print("EXCEL FILE COLUMNS")
print("=" * 80)
print(excel_df.columns.tolist())
print()
print(f"Total rows: {len(excel_df)}")
print()

# Check if signal column exists
if 'signal' in excel_df.columns:
    excel_signals = excel_df[excel_df['signal'].notna() & (excel_df['signal'] != '')]
    print("=" * 80)
    print("SIGNALS IN EXCEL TRACKING FILE")
    print("=" * 80)
    print(excel_signals[['time', 'signal', 'Close', 'sell_price', 'buy_price']].to_string())
else:
    print("No 'signal' column in Excel file - showing first few rows:")
    print(excel_df.head().to_string())
print()

# Parse IB log for signals
print("=" * 80)
print("SIGNALS IN IB LOG")
print("=" * 80)

with open(r'C:\Users\Administrator\Desktop\IB_Live\logs\fred_ib_20260511_0929.log', 'r') as f:
    for line in f:
        if '[TradingAlgo] BUY' in line or '[TradingAlgo] SELL' in line:
            print(line.strip())

print()
print("=" * 80)
print("COMPARISON")
print("=" * 80)
print(f"Excel signals: {len(excel_signals)}")
print(f"Excel SELL count: {len(excel_signals[excel_signals['signal'] == 'SELL'])}")
print(f"Excel BUY count: {len(excel_signals[excel_signals['signal'] == 'BUY'])}")
