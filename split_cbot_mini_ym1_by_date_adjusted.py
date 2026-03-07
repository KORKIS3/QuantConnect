"""Split 'CBOT_MINI_YM1!, 1 (2).csv' into per-day CSVs on Desktop.
- Parse `time` with timezone offset.
- Adjust for the offset into local US/Eastern wall-clock time.
- Write `time` as 'YYYY-MM-DD HH:MM:SS' (no T, no offset).
- Keep original columns: time, open, high, low, close.
- Save per-day files under Desktop/CBOT_MINI_YM1_ByDate.
"""

import os

import pandas as pd
import pytz


home = os.path.expanduser("~")
desktop = os.path.join(home, "Desktop")

source_csv = os.path.join(desktop, "CBOT_MINI_YM1!, 1 (2).csv")
out_dir = os.path.join(desktop, "CBOT_MINI_YM1_ByDate")
os.makedirs(out_dir, exist_ok=True)

print("=" * 60)
print("Splitting CBOT_MINI_YM1!, 1 (2).csv by Date (offset-adjusted)")
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

# Parse time column with timezone, normalize to US/Eastern, then drop tz
print("Parsing time column and adjusting for offset to US/Eastern...")

# Read as UTC so offsets like -05:00 are handled consistently, then convert
dt = pd.to_datetime(df["time"], utc=True, errors="coerce")
orig_rows = len(df)
mask_valid = dt.notna()
if mask_valid.sum() != orig_rows:
    print(f"Dropped {orig_rows - mask_valid.sum()} rows with invalid timestamps")
    df = df[mask_valid].copy()
    dt = dt[mask_valid]

est = pytz.timezone("US/Eastern")
dt_local = dt.dt.tz_convert(est).dt.tz_localize(None)

# Store converted timestamps for grouping/output
df["time_dt"] = dt_local

# Use date from local time for grouping
unique_dates = sorted({d.date() for d in dt_local})
print(f"Unique dates: {len(unique_dates)}")

files_written = 0
for d in unique_dates:
    day_mask = df["time_dt"].dt.date == d
    day_df = df.loc[day_mask].copy()
    if day_df.empty:
        continue

    # Format time column cleanly and drop helper column
    day_df["time"] = day_df["time_dt"].dt.strftime("%Y-%m-%d %H:%M:%S")
    day_df = day_df.drop(columns=["time_dt"])

    # Ensure column order: time, open, high, low, close
    cols_order = ["time", "open", "high", "low", "close"]
    day_df = day_df[cols_order]

    fname = f"CBOT_MINI_YM1_{d.isoformat()}.csv"
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
