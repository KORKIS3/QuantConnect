"""
Split 'Updated SpreadSheet - UpdatedJanData.csv' into per-day CSVs
Output folder: Desktop/UpdatedJanData_ByDate
Each file: UpdatedJanData_YYYY-MM-DD.csv
"""
import os
import pandas as pd

home = os.path.expanduser("~")
desktop = os.path.join(home, "Desktop")

# Source file (found in Downloads)
source_csv = os.path.join(home, "Downloads", "Updated SpreadSheet - UpdatedJanData.csv")

# Output folder on Desktop
out_dir = os.path.join(desktop, "UpdatedJanData_ByDate")
os.makedirs(out_dir, exist_ok=True)

print("=" * 60)
print("Splitting UpdatedJanData by Date")
print("=" * 60)
print(f"Source:  {source_csv}")
print(f"Output:  {out_dir}")

if not os.path.exists(source_csv):
    print("ERROR: Source CSV not found.")
    raise SystemExit(1)

# Load CSV
print("\nLoading data...")
df = pd.read_csv(source_csv, parse_dates=["Timestamp"])  # Date column is already YYYY-MM-DD string
print(f"Rows: {len(df):,}")
print(f"Columns: {df.columns.tolist()}")

# Ensure Date column exists and is in YYYY-MM-DD format
if "Date" not in df.columns:
    df["Date"] = df["Timestamp"].dt.date.astype(str)
else:
    # Normalize to string YYYY-MM-DD
    df["Date"] = pd.to_datetime(df["Date"]).dt.date.astype(str)

unique_dates = sorted(df["Date"].unique())
print(f"Unique trading days: {len(unique_dates)}")

files_written = 0

for d in unique_dates:
    day_df = df[df["Date"] == d].copy()
    if day_df.empty:
        continue

    # Build filename: UpdatedJanData_2026-01-02.csv
    fname = f"UpdatedJanData_{d}.csv"
    out_path = os.path.join(out_dir, fname)

    # Save with same columns as source
    day_df.to_csv(out_path, index=False)
    files_written += 1
    print(f"  Wrote {len(day_df):4d} rows -> {fname}")

print("\n" + "=" * 60)
print("Done")
print("=" * 60)
print(f"Total days:   {len(unique_dates)}")
print(f"Files written: {files_written}")
print(f"Output folder: {out_dir}")
