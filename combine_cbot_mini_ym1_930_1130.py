"""
Combine per-day CSVs from four time-period folders into a single
9:30-11:30am file per day.

Source folders (Desktop/data/):
  CBOT_MINI_YM1_ByDate_930_1000
  CBOT_MINI_YM1_ByDate_1000_1030
  CBOT_MINI_YM1_ByDate_1030_1100
  CBOT_MINI_YM1_ByDate_1100_1130

Output folder: Desktop/data/CBOT_MINI_YM1_ByDate_930_1130
Each file: CBOT_MINI_YM1_YYYY-MM-DD.csv
"""
import os
import glob
import pandas as pd

home = os.path.expanduser("~")
desktop = os.path.join(home, "Desktop")
data_root = os.path.join(desktop, "data")

source_folders = [
    "CBOT_MINI_YM1_ByDate_930_1000",
    "CBOT_MINI_YM1_ByDate_1000_1030",
    "CBOT_MINI_YM1_ByDate_1030_1100",
    "CBOT_MINI_YM1_ByDate_1100_1130",
]

out_dir = os.path.join(data_root, "CBOT_MINI_YM1_ByDate_930_1130")
os.makedirs(out_dir, exist_ok=True)

print("=" * 60)
print("Combining per-day CSVs for 9:30-11:30am")
print("=" * 60)
print(f"Output: {out_dir}\n")

# Collect all unique dates across all source folders
all_dates = set()
for folder in source_folders:
    folder_path = os.path.join(data_root, folder)
    for fp in glob.glob(os.path.join(folder_path, "*.csv")):
        fname = os.path.basename(fp)
        # Extract date from filename CBOT_MINI_YM1_YYYY-MM-DD.csv
        parts = fname.replace(".csv", "").split("_")
        date_str = parts[-1]
        all_dates.add(date_str)

all_dates = sorted(all_dates)
print(f"Unique dates found: {len(all_dates)}")

files_written = 0
for date_str in all_dates:
    frames = []
    for folder in source_folders:
        fp = os.path.join(data_root, folder, f"CBOT_MINI_YM1_{date_str}.csv")
        if os.path.exists(fp):
            df = pd.read_csv(fp)
            frames.append(df)

    if not frames:
        print(f"  No data found for {date_str}, skipping.")
        continue

    combined = pd.concat(frames, ignore_index=True)

    # Sort by time column, handling mixed tz-aware and tz-naive timestamps
    if "time" in combined.columns:
        import pytz
        eastern = pytz.timezone("US/Eastern")

        def normalize_ts(ts):
            try:
                t = pd.to_datetime(ts, errors="coerce")
                if pd.isnull(t):
                    return pd.NaT
                if t.tzinfo is None:
                    t = eastern.localize(t)
                return t.astimezone(pytz.utc)
            except Exception:
                return pd.NaT

        combined["time"] = combined["time"].apply(normalize_ts)
        combined = combined.dropna(subset=["time"])
        combined = combined.sort_values("time").drop_duplicates(subset=["time"]).reset_index(drop=True)
        # Convert back to Eastern time for output
        combined["time"] = combined["time"].apply(lambda t: t.astimezone(eastern))

    out_path = os.path.join(out_dir, f"CBOT_MINI_YM1_{date_str}.csv")
    combined.to_csv(out_path, index=False)
    files_written += 1

    first_ts = combined["time"].iloc[0] if "time" in combined.columns and len(combined) > 0 else "N/A"
    last_ts = combined["time"].iloc[-1] if "time" in combined.columns and len(combined) > 0 else "N/A"
    print(f"  Wrote {len(combined):5d} rows -> CBOT_MINI_YM1_{date_str}.csv | First: {first_ts} Last: {last_ts}")

print("\n" + "=" * 60)
print("Done")
print("=" * 60)
print(f"Files written: {files_written}")
print(f"Output folder: {out_dir}")
