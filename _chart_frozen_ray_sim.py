"""
Simulate frozen ray engine on 02/11 and display chart with lines and trade markers.
"""
import pandas as pd
import pytz
import os
import numpy as np
import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

_EST = pytz.timezone('US/Eastern')
data_root = os.path.expanduser('~/Desktop/2YearsData/full_day')

# Load data
target_date = '2026-02-11'
fpath = os.path.join(data_root, f'CBOT_MINI_YM1_{target_date}.csv')
df = pd.read_csv(fpath, index_col=0, parse_dates=True)
df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
day_start = pd.Timestamp(f'{target_date} 09:30', tz=_EST)
day_end = pd.Timestamp(f'{target_date} 10:30', tz=_EST)
data = df[(df.index >= day_start) & (df.index <= day_end)].copy()
data = data.reset_index()

n = len(data)
highs = data['High'].values
lows = data['Low'].values
closes = data['Close'].values
opens = data['Open'].values

# --- SIMULATE FROZEN RAY ENGINE ---

# Orange: from session high, fixed -2.5 degree slope
# Yellow: from session low, fixed +2.5 degree slope
# Blue: P1=session low, P2=first confirmed higher swing low
# Purple: P1=session high, P2=first confirmed lower swing high

# Track session extremes
session_high = highs[0]
session_high_bar = 0
session_low = lows[0]
session_low_bar = 0

# Find session high
for i in range(n):
    if highs[i] > session_high:
        session_high = highs[i]
        session_high_bar = i

# Orange/Yellow: fixed slope from extremes
# Convert 2.5 degrees to pts/bar (approximate: 1 degree ~ 0.73 pts/bar for YM at this scale)
pts_per_degree = 0.73
orange_slope = -2.5 * pts_per_degree  # descending
yellow_slope = +2.5 * pts_per_degree  # ascending

# Compute orange/yellow values
orange_vals = np.zeros(n)
yellow_vals = np.zeros(n)
curr_high = highs[0]; curr_high_bar = 0
curr_low = lows[0]; curr_low_bar = 0

for i in range(n):
    if highs[i] > curr_high:
        curr_high = highs[i]; curr_high_bar = i
    if lows[i] < curr_low:
        curr_low = lows[i]; curr_low_bar = i
    orange_vals[i] = curr_high + orange_slope * (i - curr_high_bar)
    yellow_vals[i] = curr_low + yellow_slope * (i - curr_low_bar)

# Blue: P1 = session low (bar 0 low = 50459), find P2 = first confirmed higher swing low
blue_p1 = lows[0]; blue_p1_bar = 0
blue_p2 = None; blue_p2_bar = None; blue_slope = None
blue_vals = np.full(n, np.nan)

for i in range(2, n):
    if blue_p2 is not None:
        break
    j = i - 1
    # Swing low: lower than both neighbors by >= 10 pts, higher than P1
    if (lows[j-1] - lows[j] >= 10 and lows[i] - lows[j] >= 10 and lows[j] > blue_p1):
        # Check containment: line from P1 to P2 must be below all lows
        candidate_slope = (lows[j] - blue_p1) / (j - blue_p1_bar)
        valid = True
        for k in range(blue_p1_bar, j + 1):
            line_val = blue_p1 + candidate_slope * (k - blue_p1_bar)
            if lows[k] < line_val - 1:  # 1pt tolerance
                valid = False; break
        if valid:
            blue_p2 = lows[j]; blue_p2_bar = j
            blue_slope = candidate_slope

if blue_slope is not None:
    for i in range(n):
        blue_vals[i] = blue_p1 + blue_slope * (i - blue_p1_bar)

# Purple: P1 = session high, find P2 = first confirmed lower swing high
purple_p1 = session_high; purple_p1_bar = session_high_bar
purple_p2 = None; purple_p2_bar = None; purple_slope = None
purple_vals = np.full(n, np.nan)

for i in range(session_high_bar + 2, n):
    if purple_p2 is not None:
        break
    j = i - 1
    # Swing high: higher than both neighbors by >= 10 pts, lower than P1
    if (highs[j] - highs[j-1] >= 10 and highs[j] - highs[i] >= 10 and highs[j] < purple_p1):
        candidate_slope = (highs[j] - purple_p1) / (j - purple_p1_bar)
        valid = True
        for k in range(purple_p1_bar, j + 1):
            line_val = purple_p1 + candidate_slope * (k - purple_p1_bar)
            if highs[k] > line_val + 1:
                valid = False; break
        if valid:
            purple_p2 = highs[j]; purple_p2_bar = j
            purple_slope = candidate_slope

if purple_slope is not None:
    for i in range(n):
        purple_vals[i] = purple_p1 + purple_slope * (i - purple_p1_bar)

# --- DETECT SIGNALS ---
signals = []

# Blue break: first bar where close < blue line
if blue_slope is not None:
    for i in range(1, n):
        if not np.isnan(blue_vals[i]) and closes[i] < blue_vals[i]:
            signals.append({'bar': i, 'type': 'SELL', 'reason': 'BLUE_BREAK', 'price': closes[i]})
            break

# Yellow break: first bar where close < yellow line
for i in range(1, n):
    if closes[i] < yellow_vals[i]:
        signals.append({'bar': i, 'type': 'SELL_CONFIRM', 'reason': 'YELLOW_BREAK', 'price': closes[i]})
        break

# --- PLOT ---
fig, ax = plt.subplots(1, 1, figsize=(16, 9))
fig.suptitle(f'FROZEN RAY SIMULATION — {target_date} (09:30-10:30)', fontsize=14, fontweight='bold')

# Candlesticks
for i in range(n):
    color = 'green' if closes[i] >= opens[i] else 'red'
    # Wick
    ax.plot([i, i], [lows[i], highs[i]], color='black', linewidth=0.5)
    # Body
    body_low = min(opens[i], closes[i])
    body_high = max(opens[i], closes[i])
    rect = Rectangle((i - 0.3, body_low), 0.6, max(body_high - body_low, 1), 
                     facecolor=color, edgecolor='black', linewidth=0.5)
    ax.add_patch(rect)

# Orange line
ax.plot(range(n), orange_vals, color='orange', linewidth=2, label='Orange (rank 1)', linestyle='-')

# Yellow line
ax.plot(range(n), yellow_vals, color='gold', linewidth=2, label='Yellow (rank 1)', linestyle='-')

# Blue line
if blue_slope is not None:
    ax.plot(range(n), blue_vals, color='deepskyblue', linewidth=2, label=f'Blue (rank 2) P1={blue_p1:.0f} P2={blue_p2:.0f}')
    ax.scatter([blue_p1_bar], [blue_p1], color='blue', s=100, zorder=5, marker='^')
    ax.scatter([blue_p2_bar], [blue_p2], color='blue', s=100, zorder=5, marker='^')

# Purple line
if purple_slope is not None:
    ax.plot(range(n), purple_vals, color='purple', linewidth=2, label=f'Purple (rank 2) P1={purple_p1:.0f} P2={purple_p2:.0f}')
    ax.scatter([purple_p1_bar], [purple_p1], color='purple', s=100, zorder=5, marker='v')
    ax.scatter([purple_p2_bar], [purple_p2], color='purple', s=100, zorder=5, marker='v')
else:
    ax.text(n * 0.7, session_high - 20, 'PURPLE: PROVISIONAL\n(no valid P2 found)', 
            color='purple', fontsize=10, ha='center')

# Signal markers
for sig in signals:
    marker = 'v' if 'SELL' in sig['type'] else '^'
    color = 'red' if 'SELL' in sig['type'] else 'green'
    ax.scatter([sig['bar']], [sig['price']], color=color, s=200, zorder=10, marker=marker, edgecolors='black')
    ax.annotate(f"{sig['reason']}\n{sig['price']:.0f}", 
                xy=(sig['bar'], sig['price']), xytext=(sig['bar'] + 2, sig['price'] + 30),
                fontsize=8, color=color, fontweight='bold',
                arrowprops=dict(arrowstyle='->', color=color))

# X-axis labels (time)
tick_positions = list(range(0, n, 5))
tick_labels = [data.iloc[i]['time'].strftime('%H:%M') if i < n else '' for i in tick_positions]
ax.set_xticks(tick_positions)
ax.set_xticklabels(tick_labels, rotation=45, fontsize=8)

ax.set_ylabel('Price')
ax.set_xlabel('Time')
ax.legend(loc='upper right', fontsize=9)
ax.grid(True, alpha=0.3)
ax.set_xlim(-1, n + 1)

# Add text box with line state
info = f"SESSION HIGH: {session_high:.0f} (bar {session_high_bar})\n"
info += f"SESSION LOW: {curr_low:.0f} (bar {curr_low_bar})\n"
if blue_slope:
    p2_str = f"{blue_p2:.0f}" if blue_p2 else "NONE"
    info += f"BLUE: P1={blue_p1:.0f} P2={p2_str} slope={blue_slope:.1f}/bar\n"
else:
    info += "BLUE: PROVISIONAL\n"
info += f"PURPLE: {'FROZEN' if purple_slope else 'PROVISIONAL (no valid P2)'}\n"
info += f"SIGNALS: {len(signals)}"
ax.text(0.02, 0.02, info, transform=ax.transAxes, fontsize=9, verticalalignment='bottom',
        bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))

plt.tight_layout()
plt.show()
