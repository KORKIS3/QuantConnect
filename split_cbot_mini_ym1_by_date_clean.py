"""Split 'CBOT_MINI_YM1!, 1 (2).csv' into per-day CSVs on Desktop.
- Parse `time` with timezone offset.
- Convert to naive local time (drop `-05:00`).
- Add `Date` (YYYY-MM-DD) and `Time` (HH:MM:SS) columns.
- Save per-day files under Desktop/CBOT_MINI_YM1_ByDate_Clean.
"""

import os

import pandas as pd
import pytz


home = os.path.expanduser("~")
desktop = os.path.join(home, "Desktop")

source_csv = os.path.join(desktop, "CBOT_MINI_YM1!, 1 (2).csv")
out_dir = os.path.join(desktop, "CBOT_MINI_YM1_ByDate_Clean")
os.makedirs(out_dir, exist_ok=True)

print("=" * 60)
print("Splitting CBOT_MINI_YM1!, 1 (2).csv by Date (clean time)")
print("=" * 60)
print(f"Source:  {source_csv}")
print(f"Output:  {out_dir}")

if not os.path.exists(source_csv):
    print("ERROR: source CSV not found.")
    raise SystemExit(1)

print("\nLoading data...")
df = pd.read_csv(source_csv)
print(f"Rows: {len(df):,}")
print(f"Columns: {df.columns.tolist()}")

if "time" not in df.columns:
    print("ERROR: expected 'time' column not found.")
    raise SystemExit(1)

# Parse time column with timezone, then drop tz so we have plain local time
print("Parsing time column and normalizing to local (no offset)...")
df["time"] = pd.to_datetime(df["time"], errors="coerce")
before = len(df)
df = df.dropna(subset=["time"]).copy()
after = len(df)
if after != before:
    print(f"Dropped {before - after} rows with invalid timestamps")

# If timezone-aware, convert to US/Eastern then drop tz
if df["time"].dt.tz is not None:
    est = pytz.timezone("US/Eastern")
    df["time"] = df["time"].dt.tz_convert(est).dt.tz_localize(None)
else:
    # Already naive; just ensure it's datetime
    df["time"] = pd.to_datetime(df["time"])

# Build helper date/time columns
df["Date"] = df["time"].dt.date.astype(str)
df["Time"] = df["time"].dt.strftime("%H:%M:%S")

unique_dates = sorted(df["Date"].unique())
print(f"Unique dates: {len(unique_dates)}")

files_written = 0
for d in unique_dates:
    day_df = df[df["Date"] == d].copy()
    if day_df.empty:
        continue

    # Reorder/rename columns to a clean schema
    day_df = day_df.rename(columns={
        "time": "Timestamp",
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close",
    })

    day_df = day_df[["Timestamp", "Date", "Time", "Open", "High", "Low", "Close"]]

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