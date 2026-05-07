import pandas as pd, pytz
_EST = pytz.timezone("US/Eastern")
df = pd.read_csv(r'C:\Users\Administrator\Desktop\IB_Live\tracking\YM_tracking_2026-05-04.csv', index_col=0, parse_dates=True)
df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)

mask = (df.index >= pd.Timestamp("2026-05-04 10:37", tz=_EST)) & (df.index <= pd.Timestamp("2026-05-04 10:43", tz=_EST))
sub = df.loc[mask, ["Close", "blue_steep_0_vals"]].copy()

# slope per bar from the 10:40 line
val_1039 = sub["blue_steep_0_vals"].iloc[2]  # 10:39
val_1040 = sub["blue_steep_0_vals"].iloc[3]  # 10:40
slope_per_bar = val_1040 - val_1039

# project the 10:40 line forward one bar to 10:41
projected_1041 = val_1040 + slope_per_bar
close_1041 = sub["Close"].iloc[4]  # 10:41
actual_ray_1041 = sub["blue_steep_0_vals"].iloc[4]  # what algo actually used

print(f"blue_steep_0 at 10:39 = {val_1039:.2f}")
print(f"blue_steep_0 at 10:40 = {val_1040:.2f}")
print(f"slope per bar         = {slope_per_bar:.2f}")
print()
print(f"Projected line at 10:41 (extending 10:40 equation) = {projected_1041:.2f}")
print(f"Actual ray value used at 10:41                     = {actual_ray_1041:.2f}  <-- algo used this (refit)")
print(f"Close at 10:41                                     = {close_1041:.2f}")
print()
print(f"Cross using PROJECTED (correct): close {close_1041} < {projected_1041:.2f} = {close_1041 < projected_1041}")
print(f"Cross using REFIT    (bug):      close {close_1041} < {actual_ray_1041:.2f} = {close_1041 < actual_ray_1041}")
