"""
Compare the historical CSV bars vs the live tracking CSV bars for 4/23
to see if there are any price differences that could cause different ray calculations.
"""
import pandas as pd
import pytz

_EST = pytz.timezone("US/Eastern")
d = "2026-04-23"

# Historical CSV
hist = pd.read_csv(
    f"C:/Users/Administrator/Desktop/2YearsData/full_day/CBOT_MINI_YM1_{d}.csv",
    index_col=0, parse_dates=True)
hist.index = pd.to_datetime(hist.index, utc=True).tz_convert(_EST)
hist = hist[hist.index >= pd.Timestamp(f"{d} 09:30", tz=_EST)]
hist = hist[hist.index <= pd.Timestamp(f"{d} 10:30", tz=_EST)]

# Live tracking CSV
live = pd.read_csv(
    f"C:/Users/Administrator/Desktop/IB_Live/tracking/YM_tracking_{d}.csv",
    index_col=0, parse_dates=True)
live.index = pd.to_datetime(live.index, utc=True).tz_convert(_EST)
live = live[live.index >= pd.Timestamp(f"{d} 09:30", tz=_EST)]
live = live[live.index <= pd.Timestamp(f"{d} 10:30", tz=_EST)]

print(f"Historical bars: {len(hist)}  |  Live bars: {len(live)}")
print(f"\n{'Time':<8} {'Hist Close':>11} {'Live Close':>11} {'Diff':>6}")
print("-" * 40)

common = hist.index.intersection(live.index)
diffs = 0
for ts in common:
    hc = hist.loc[ts, "Close"]
    lc = live.loc[ts, "Close"]
    diff = hc - lc
    if abs(diff) > 0:
        diffs += 1
        print(f"{ts.strftime('%H:%M'):<8} {hc:>11.0f} {lc:>11.0f} {diff:>+6.0f}")

if diffs == 0:
    print("All bars match exactly — no price differences")
print(f"\nTotal differing bars: {diffs} out of {len(common)}")
print(f"Bars only in hist: {len(hist.index.difference(live.index))}")
print(f"Bars only in live: {len(live.index.difference(hist.index))}")
