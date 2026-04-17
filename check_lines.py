import pandas as pd, pytz, numpy as np
import matplotlib.dates as mdates

est = pytz.timezone("US/Eastern")
df = pd.read_csv(r"C:\Users\Administrator\Desktop\IB_Live\historical\YM_2026-02-05_0930_1030.csv",
                 index_col=0, parse_dates=True)
df.index = pd.to_datetime(df.index, utc=True).tz_convert(est)

print("Bars 9:30-9:55:")
print(df.loc["2026-02-05 09:30":"2026-02-05 09:55", ["High","Low","Close"]].to_string())

# Purple line: 9:31 high -> 9:35 high
t0 = pd.Timestamp("2026-02-05 09:31", tz=est)
t1 = pd.Timestamp("2026-02-05 09:35", tz=est)
p0 = float(df.loc[t0, "High"])
p1 = float(df.loc[t1, "High"])
slope_p = (p1 - p0) / (mdates.date2num(t1) - mdates.date2num(t0))

print(f"\nPurple line: 9:31 @ {p0:.0f}  ->  9:35 @ {p1:.0f}")
for t_str in ["09:36","09:37","09:38","09:39","09:40"]:
    t = pd.Timestamp(f"2026-02-05 {t_str}", tz=est)
    val = p0 + slope_p * (mdates.date2num(t) - mdates.date2num(t0))
    close = float(df.loc[t, "Close"])
    crossed = close > val
    print(f"  {t_str}: line={val:.1f}  close={close:.0f}  crossed_above={crossed}")

# Blue line: 9:41 low -> 9:50 low
t2 = pd.Timestamp("2026-02-05 09:41", tz=est)
t3 = pd.Timestamp("2026-02-05 09:50", tz=est)
b0 = float(df.loc[t2, "Low"])
b1 = float(df.loc[t3, "Low"])
slope_b = (b1 - b0) / (mdates.date2num(t3) - mdates.date2num(t2))

print(f"\nBlue line: 9:41 @ {b0:.0f}  ->  9:50 @ {b1:.0f}")
for t_str in ["09:50","09:51","09:52","09:53","09:54"]:
    t = pd.Timestamp(f"2026-02-05 {t_str}", tz=est)
    val = b0 + slope_b * (mdates.date2num(t) - mdates.date2num(t2))
    close = float(df.loc[t, "Close"])
    crossed = close < val
    print(f"  {t_str}: line={val:.1f}  close={close:.0f}  crossed_below={crossed}")

# Angles
_WINDOW_MINUTES = 75
x_range = _WINDOW_MINUTES / (24 * 60)
ax_w_in = 16 * (0.85 - 0.125)
ax_h_in = 9 * (0.88 - 0.11)
y_range = float(df["High"].max()) + 20 - (float(df["Low"].min()) - 20)
x_per_unit = x_range / ax_w_in
y_per_unit = y_range / ax_h_in

angle_p = np.degrees(np.arctan(abs(slope_p) * x_per_unit / y_per_unit))
angle_b = np.degrees(np.arctan(abs(slope_b) * x_per_unit / y_per_unit))
print(f"\nPurple line angle: {angle_p:.1f} degrees")
print(f"Blue line angle:   {angle_b:.1f} degrees")
print(f"Threshold: 70 degrees")
print(f"Purple passes threshold: {angle_p < 70}")
print(f"Blue passes threshold:   {angle_b < 70}")
