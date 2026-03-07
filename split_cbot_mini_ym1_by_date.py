"""
Split 'CBOT_MINI_YM1!, 1 (2).csv' into per-day CSVs.
Source: Desktop/CBOT_MINI_YM1!, 1 (2).csv
Output folder: Desktop/CBOT_MINI_YM1_ByDate
Each file: CBOT_MINI_YM1_YYYY-MM-DD.csv
"""
import os
import pandas as pd

home = os.path.expanduser("~")
desktop = os.path.join(home, "Desktop")

source_csv = os.path.join(desktop, "CBOT_MINI_YM1!, 1 (2).csv")
out_dir = os.path.join(desktop, "CBOT_MINI_YM1_ByDate")
os.makedirs(out_dir, exist_ok=True)

print("=" * 60)
print("Splitting CBOT_MINI_YM1!, 1 (2).csv by Date")
print("=" * 60)
print(f"Source:  {source_csv}")
print(f"Output:  {out_dir}")

if not os.path.exists(source_csv):
    print("ERROR: source CSV not found.")
    raise SystemExit(1)

print("\nLoading data...")
# time,open,high,low,close
df = pd.read_csv(source_csv)
print(f"Rows: {len(df):,}")
print(f"Columns: {df.columns.tolist()}")

if "time" not in df.columns:
    print("ERROR: expected 'time' column not found.")
    raise SystemExit(1)

# Parse time column to datetime and extract date
print("Parsing time column...")
df["time"] = pd.to_datetime(df["time"], errors="coerce")
# Drop any rows that failed to parse
before = len(df)
df = df.dropna(subset=["time"]).copy()
after = len(df)
if after != before:
    print(f"Dropped {before - after} rows with invalid timestamps")

df["Date"] = df["time"].dt.date.astype(str)

unique_dates = sorted(df["Date"].unique())
print(f"Unique dates: {len(unique_dates)}")

files_written = 0
for d in unique_dates:
    day_df = df[df["Date"] == d].copy()
    if day_df.empty:
        continue

    # Drop helper Date column in output, keep original structure
    day_df = day_df.drop(columns=["Date"])

    fname = f"CBOT_MINI_YM1_{d}.csv"
    out_path = os.path.join(out_dir, fname)
    day_df.to_csv(out_path, index=False)
    files_written += 1
    print(f"  Wrote {len(day_df):5d} rows -> {fname}")

print("\n" + "=" * 60)
print("Done")
print("=" * 60)
print(f"Total days:   {len(unique_dates)}")
print(f"Files written: {files_written}")
print(f"Output folder: {out_dir}")
