import pandas as pd, pytz, os
est = pytz.timezone("US/Eastern")
data_root = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "930_1130")
files = sorted([f for f in os.listdir(data_root) if f.endswith(".csv")])
fname = files[-10]
df = pd.read_csv(os.path.join(data_root, fname), index_col=0, parse_dates=True)
df.index = pd.to_datetime(df.index, utc=True).tz_convert(est)
for i in range(15):
    ts = df.index[i].strftime("%H:%M")
    h = df.iloc[i]["High"]; l = df.iloc[i]["Low"]
    print(f"Bar {i} ({ts}): H={h:.0f} L={l:.0f}")

# Check: at bar 9, what is the min low of bars 0-9?
print(f"\nMin low bars 0-9: {df.iloc[:10]['Low'].min():.0f}")
print(f"Min low bars 0-8: {df.iloc[:9]['Low'].min():.0f}")

# Blue anchor at bar 8: what was the min low?
print(f"\nBlue anchor before bar 9: min_low of bars 0-8 = {df.iloc[:9]['Low'].min():.0f}")
idx = df.iloc[:9]["Low"].idxmin()
print(f"  at bar index: {df.index.get_loc(idx)}, time: {idx}")
