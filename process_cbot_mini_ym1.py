"""
Read CBOT_MINI_YM1!, 1 (2).csv from Desktop.
Adjust timestamps for the UTC offset -> US/Eastern wall-clock time.
Filter to 09:30-10:00 Eastern only.
Split by date and save each day as a CSV in Desktop/CBOT_MINI_YM1_ByDate_930_1000.
"""
import datetime
import pandas as pd
import pytz
import os

# ── config ─────────────────────────────────────────────────
START_TIME = datetime.time(9, 30)
END_TIME   = datetime.time(10, 0)

# ── paths ──────────────────────────────────────────────────
desktop = os.path.join(os.path.expanduser("~"), "Desktop")
source_csv = os.path.join(desktop, "CBOT_MINI_YM1!, 1 (2).csv")
out_dir = os.path.join(desktop, "CBOT_MINI_YM1_ByDate_930_1000")
os.makedirs(out_dir, exist_ok=True)

print("=" * 60)
print("CBOT_MINI_YM1  -  Offset-adjust, filter 09:30-10:00, split by date")
print("=" * 60)
print(f"Source : {source_csv}")
print(f"Window : {START_TIME.strftime('%H:%M')} - {END_TIME.strftime('%H:%M')} Eastern")
print(f"Output : {out_dir}")

if not os.path.exists(source_csv):
    print("ERROR: source CSV not found on Desktop.")
    raise SystemExit(1)

# ── load ───────────────────────────────────────────────────
print("\nLoading data...")
df = pd.read_csv(source_csv)
print(f"Rows   : {len(df):,}")
print(f"Columns: {df.columns.tolist()}")

# ── adjust timezone offset ─────────────────────────────────
print("\nParsing timestamps (UTC) and converting to US/Eastern...")
df["time"] = pd.to_datetime(df["time"], utc=True, errors="coerce")

before = len(df)
df = df.dropna(subset=["time"]).copy()
if len(df) != before:
    print(f"Dropped {before - len(df)} rows with invalid timestamps")

est = pytz.timezone("US/Eastern")
df["time"] = df["time"].dt.tz_convert(est).dt.tz_localize(None)

# ── sort & dedup ───────────────────────────────────────────
df = df.sort_values("time")
before_dedup = len(df)
df = df.drop_duplicates(subset=["time"], keep="first")
if before_dedup != len(df):
    print(f"Removed {before_dedup - len(df)} duplicate(s)")

# ── filter 09:30 - 10:00 ──────────────────────────────────
df["_time_only"] = df["time"].dt.time
df = df[(df["_time_only"] >= START_TIME) & (df["_time_only"] <= END_TIME)].copy()
print(f"Rows after 09:30-10:00 filter: {len(df):,}")

# ── split by date & save ──────────────────────────────────
df["_date"] = df["time"].dt.date
unique_dates = sorted(df["_date"].unique())
print(f"Unique dates: {len(unique_dates)}")

files_written = 0
for d in unique_dates:
    day_df = df[df["_date"] == d].copy()
    if day_df.empty:
        continue

    day_df["time"] = day_df["time"].dt.strftime("%Y-%m-%d %H:%M:%S")
    day_df = day_df[["time", "open", "high", "low", "close"]]

    fname = f"CBOT_MINI_YM1_{d.isoformat()}.csv"
    day_df.to_csv(os.path.join(out_dir, fname), index=False)
    files_written += 1
    print(f"  {len(day_df):3d} rows -> {fname}")

# ── summary ────────────────────────────────────────────────
print("\n" + "=" * 60)
print("DONE")
print("=" * 60)
print(f"Total rows   : {len(df):,}")
print(f"Date range   : {unique_dates[0].isoformat()} to {unique_dates[-1].isoformat()}")
print(f"Files written: {files_written}")
print(f"Output folder: {out_dir}")
print("=" * 60)
