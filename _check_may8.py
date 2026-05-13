"""Check May 8 data"""
import pandas as pd
from pathlib import Path

csv_path = Path.home() / "Desktop" / "2YearsData" / "full_day" / "CBOT_MINI_YM1_2026-05-08.csv"

df = pd.read_csv(csv_path)
print(f"Total bars: {len(df)}")
print(f"\nFirst 5 bars:")
print(df.head())
print(f"\nLast 5 bars:")
print(df.tail())
print(f"\nColumns: {df.columns.tolist()}")
print(f"\nPrice range: {df['Low'].min():.0f} - {df['High'].max():.0f}")
