"""
Understand what angle actually makes sense for the trailing stop.
The trailing line should be BELOW price for a long, rising at an angle
that gives the trade room to breathe but exits on a real reversal.

For 4/23 10:11-10:20:
- Entry: 49,576
- Anchor (swing low): 49,559
- Peak: 49,640 (+64 pts in 9 bars)
- We want the line to be BELOW 49,640 at bar 9

Let's find what angle keeps the line below price throughout the move.
"""
import numpy as np

# Aspect ratio from the algo
_ax_w_in = 16.0 * (0.85 - 0.125)
_ax_h_in = 9.0  * (0.88 - 0.11)
_x_range = 75 / (24 * 60)

# Approximate y_range for this day
_y_range = 300.0  # typical daily range + padding
x_per_unit = _x_range / _ax_w_in
y_per_unit = _y_range / _ax_h_in

anchor_p = 49559.0
# 9 bars of 1-min = 9 minutes
bars = 9
t_diff_per_bar = (1.0 / (24 * 60)) / x_per_unit  # 1 minute in plot units

print("Trailing line value at bar 9 (10:20) for different angles:")
print(f"Anchor: {anchor_p:.0f}  |  Close at 10:20: 49,640")
print(f"{'Angle':>8} {'Trail@bar9':>12} {'Below close?':>14} {'Gap':>8}")
print("-" * 50)

for angle in [5, 10, 15, 20, 25, 30, 35, 40, 45, 50]:
    slope = np.tan(np.deg2rad(angle)) * (y_per_unit / x_per_unit)
    trail_val = anchor_p + slope * (bars * t_diff_per_bar)
    below = trail_val < 49640
    gap = 49640 - trail_val
    print(f"{angle:>7}°  {trail_val:>12.0f}  {'YES' if below else 'NO':>14}  {gap:>+8.0f}")

print("\nFor the trailing stop to work correctly on this trade,")
print("the line must be BELOW 49,640 at bar 9.")
print("Angles above ~35° will be above price and fire incorrectly.")
