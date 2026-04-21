"""Check which trading days are missing from the full_day data folder."""
import os
from datetime import date, timedelta

DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")

# Get all files we have
files = sorted([f for f in os.listdir(DATA_ROOT) if f.startswith("CBOT_MINI_YM1_") and f.endswith(".csv")])
have = set(f.replace("CBOT_MINI_YM1_","").replace(".csv","") for f in files)

# Generate all expected trading days (Mon-Fri, no weekends)
first = date(2024, 3, 15)  # earliest file
last  = date(2026, 4, 17)  # last Friday

missing = []
d = first
while d <= last:
    if d.weekday() < 5:  # Mon-Fri
        ds = d.strftime("%Y-%m-%d")
        if ds not in have:
            missing.append(ds)
    d += timedelta(days=1)

print(f"Files we have: {len(have)}")
print(f"Expected trading days: {len(have) + len(missing)}")
print(f"Missing days: {len(missing)}")
print()

# Group by month for readability
from collections import defaultdict
by_month = defaultdict(list)
for ds in missing:
    by_month[ds[:7]].append(ds)

for month, days in sorted(by_month.items()):
    print(f"  {month}: {len(days)} missing — {', '.join(d[8:] for d in days)}")
