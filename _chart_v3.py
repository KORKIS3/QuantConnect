"""Frozen ray v3 chart: waiting behavior, profit protection lines."""
import pandas as pd, pytz, os, numpy as np
import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

_EST = pytz.timezone('US/Eastern')
fpath = os.path.expanduser('~/Desktop/2YearsData/full_day/CBOT_MINI_YM1_2026-02-11.csv')
df = pd.read_csv(fpath, index_col=0, parse_dates=True)
df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
data = df[(df.index >= pd.Timestamp('2026-02-11 09:30', tz=_EST)) &
          (df.index <= pd.Timestamp('2026-02-11 10:30', tz=_EST))].reset_index()

n = len(data)
highs = data['High'].values
lows = data['Low'].values
closes = data['Close'].values
opens = data['Open'].values

# --- FROZEN RAYS (v3 waiting behavior) ---
pts_per_bar = 0.73 * 2.5  # 2.5 degrees

# Track all oranges/yellows
oranges = [(highs[0], 0)]
yellows = [(lows[0], 0)]
curr_high = highs[0]; curr_low = lows[0]
for i in range(1, n):
    if highs[i] > curr_high:
        curr_high = highs[i]; oranges.append((highs[i], i))
    if lows[i] < curr_low:
        curr_low = lows[i]; yellows.append((lows[i], i))

# Blue: P1=50459(bar0), P2=50484(bar2), slope=+12.5
blue_p1 = 50459; blue_p1_bar = 0; blue_p2 = 50484; blue_p2_bar = 2
blue_slope = (blue_p2 - blue_p1) / (blue_p2_bar - blue_p1_bar)

# Profit protection purple: P1=50544(bar16), P2=50452(bar23), created at bar 32
pp_p1 = 50544; pp_p1_bar = 16; pp_p2 = 50452; pp_p2_bar = 23
pp_slope = (pp_p2 - pp_p1) / (pp_p2_bar - pp_p1_bar)
pp_created_bar = 32  # only visible from bar 32 onward

# --- PLOT ---
fig, ax = plt.subplots(figsize=(18, 10))
fig.suptitle('FROZEN RAY v3 — 2026-02-11 (Waiting Behavior + Profit Protection)', fontsize=13, fontweight='bold')

# Candlesticks
for i in range(n):
    color = 'green' if closes[i] >= opens[i] else 'red'
    ax.plot([i, i], [lows[i], highs[i]], color='black', linewidth=0.5)
    body_lo = min(opens[i], closes[i]); body_hi = max(opens[i], closes[i])
    rect = Rectangle((i-0.3, body_lo), 0.6, max(body_hi - body_lo, 1),
                     facecolor=color, edgecolor='black', linewidth=0.5)
    ax.add_patch(rect)

# Orange rays (each frozen, dashed=retired)
for idx, (p1, bar) in enumerate(oranges):
    xs = list(range(bar, n))
    ys = [p1 - pts_per_bar * (x - bar) for x in xs]
    latest = (idx == len(oranges) - 1)
    ax.plot(xs, ys, color='orange', linewidth=2 if latest else 1,
            linestyle='-' if latest else '--', alpha=1.0 if latest else 0.4)
    ax.annotate(f'O#{idx+1}\n{p1:.0f}', xy=(bar, p1), fontsize=7, color='orange', ha='center', va='bottom')

# Yellow rays (each frozen, dashed=retired/broken)
for idx, (p1, bar) in enumerate(yellows):
    xs = list(range(bar, n))
    ys = [p1 + pts_per_bar * (x - bar) for x in xs]
    latest = (idx == len(yellows) - 1)
    ax.plot(xs, ys, color='goldenrod', linewidth=2 if latest else 1,
            linestyle='-' if latest else '--', alpha=1.0 if latest else 0.35)
    ax.annotate(f'Y#{idx+1}\n{p1:.0f}', xy=(bar, p1), fontsize=7, color='goldenrod', ha='center', va='top')

# Blue ray (frozen, broken at bar 6)
xs = list(range(blue_p1_bar, min(n, 20)))  # show until shortly after break
ys = [blue_p1 + blue_slope * (x - blue_p1_bar) for x in xs]
ax.plot(xs, ys, color='deepskyblue', linewidth=2, linestyle='-', label='Blue (broken bar 6)')
ax.scatter([blue_p1_bar, blue_p2_bar], [blue_p1, blue_p2], color='blue', s=80, zorder=5, marker='^')

# Profit protection purple (only visible from bar 32)
xs = list(range(pp_p1_bar, n))
ys = [pp_p1 + pp_slope * (x - pp_p1_bar) for x in xs]
# Draw full line faintly, bold from creation bar
ax.plot(xs[:pp_created_bar - pp_p1_bar], ys[:pp_created_bar - pp_p1_bar],
        color='purple', linewidth=1, linestyle=':', alpha=0.3)
ax.plot(xs[pp_created_bar - pp_p1_bar:], ys[pp_created_bar - pp_p1_bar:],
        color='purple', linewidth=2.5, linestyle='-', label='Profit Protection Purple (created bar 32)')
ax.scatter([pp_p1_bar, pp_p2_bar], [pp_p1, pp_p2], color='purple', s=100, zorder=5, marker='v')
ax.annotate(f'P1: bounce peak\n{pp_p1:.0f}', xy=(pp_p1_bar, pp_p1), xytext=(pp_p1_bar-3, pp_p1+30),
            fontsize=8, color='purple', arrowprops=dict(arrowstyle='->', color='purple'))
ax.annotate(f'P2: 2nd bounce\n{pp_p2:.0f}', xy=(pp_p2_bar, pp_p2), xytext=(pp_p2_bar+2, pp_p2+40),
            fontsize=8, color='purple', arrowprops=dict(arrowstyle='->', color='purple'))

# Signal markers
signals = [
    (6, closes[6], 'BLUE BREAK\n(SELL)', 'red'),
    (14, closes[14], 'YELLOW#1 BREAK\n(MAX CONVICTION)', 'darkred'),
]
for bar, price, label, color in signals:
    ax.scatter([bar], [price], color=color, s=200, zorder=10, marker='v', edgecolors='black')
    ax.annotate(label, xy=(bar, price), xytext=(bar+1, price+40),
                fontsize=8, color=color, fontweight='bold',
                arrowprops=dict(arrowstyle='->', color=color))

# "WAITING" annotation
ax.annotate('WAITING\n(no steeper line yet)', xy=(19, 50480), fontsize=10, color='gray',
            ha='center', style='italic',
            bbox=dict(boxstyle='round,pad=0.3', facecolor='lightyellow', alpha=0.8))

# "STRUCTURE PROVEN" annotation
ax.annotate('STRUCTURE PROVEN\n→ create profit protection', xy=(32, 50370), fontsize=9, color='purple',
            ha='center', fontweight='bold',
            bbox=dict(boxstyle='round,pad=0.3', facecolor='lavender', alpha=0.8))

# X-axis
ticks = list(range(0, n, 5))
labels = [data.iloc[i]['time'].strftime('%H:%M') for i in ticks]
ax.set_xticks(ticks); ax.set_xticklabels(labels, rotation=45, fontsize=8)
ax.set_ylabel('Price'); ax.set_xlabel('Time')
ax.legend(loc='upper right', fontsize=9)
ax.grid(True, alpha=0.2)
ax.set_xlim(-1, n+1)

plt.tight_layout()
plt.show()
