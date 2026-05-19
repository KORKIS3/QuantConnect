"""
visualize_target_output.py — MOCKUP of correct output for 02/11

This shows what the engine SHOULD produce — manually placed lines
matching Scott's methodology. The engine must be built to produce this.

Active lines at any moment: 4-6 (not 34)
Zones visible between lines
Price moves between regions
"""
import pandas as pd, pytz, os, numpy as np
import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, FancyBboxPatch
from matplotlib.collections import PolyCollection

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
times = [data.iloc[i]['time'].strftime('%H:%M') for i in range(n)]

# ============================================================
# MANUALLY PLACED LINES — What Scott would draw
# ============================================================

# ORANGE: From session high 50585 (bar 2), shallow descent ~1.8 pts/bar
orange = {'anchor': 50585, 'bar': 2, 'slope': -1.8, 'label': 'ORANGE (strategic ceiling)'}

# YELLOW: From session open low 50459 (bar 0), shallow ascent ~1.8 pts/bar
# NOT from every new low — only the MEANINGFUL session low
yellow = {'anchor': 50459, 'bar': 0, 'slope': +1.8, 'label': 'YELLOW (strategic floor)'}

# BLUE (original): From session low 50459, ascending through bar 2 low (50484)
# Containment slope: must stay below ALL lows
# Minimum legal slope from 50459 at bar 0 that stays below all lows up to break
blue = {'anchor': 50459, 'bar': 0, 'slope': +9.0, 'label': 'BLUE (original support)',
        'break_bar': 6, 'break_note': 'BROKEN: close 50489 < blue 50513'}

# PURPLE (profit protection): Created LATE (bar ~32) after bounces proved structure
# From first failed bounce peak (bar 16, high 50544)
# Containment slope: -8.8 pts/bar (stays above all highs)
purple_pp = {'anchor': 50544, 'bar': 16, 'slope': -8.8,
             'label': 'PURPLE (profit protection)', 'visible_from': 32}

# ============================================================
# ZONES — Regions between active lines
# ============================================================

fig, ax = plt.subplots(figsize=(18, 10))
fig.suptitle("TARGET OUTPUT — What the engine SHOULD produce\n2026-02-11 (Scott's methodology)",
             fontsize=12, fontweight='bold')

# --- Draw candlesticks ---
for i in range(n):
    color = '#26a69a' if closes[i] >= opens[i] else '#ef5350'
    ax.plot([i, i], [lows[i], highs[i]], color='#555', linewidth=0.6)
    body_lo = min(opens[i], closes[i]); body_hi = max(opens[i], closes[i])
    rect = Rectangle((i - 0.35, body_lo), 0.7, max(body_hi - body_lo, 2),
                     facecolor=color, edgecolor='#333', linewidth=0.4)
    ax.add_patch(rect)

# --- Draw ZONES (shaded regions) ---

# Zone 1: Above Orange = "Breakout zone" (empty on this day)
# Zone 2: Between Orange and Blue/Purple = "Compression zone" (early session)
# Zone 3: Below Yellow = "Resolve zone" (where price goes on this day)

# Compression zone (between orange and blue, bars 0-6)
for i in range(0, 7):
    o_val = orange['anchor'] + orange['slope'] * (i - orange['bar'])
    b_val = blue['anchor'] + blue['slope'] * (i - blue['bar'])
    ax.fill_between([i-0.5, i+0.5], [b_val, b_val], [o_val, o_val],
                    color='lightblue', alpha=0.08)

# Resolve zone (below yellow, bars 14+)
for i in range(14, n):
    y_val = yellow['anchor'] + yellow['slope'] * (i - yellow['bar'])
    ax.fill_between([i-0.5, i+0.5], [y_val - 200, y_val - 200], [y_val, y_val],
                    color='#ffcdd2', alpha=0.08)

# --- Draw ACTIVE LINES ---

# Orange (full session, strategic)
xs = list(range(orange['bar'], n))
ys = [orange['anchor'] + orange['slope'] * (x - orange['bar']) for x in xs]
ax.plot(xs, ys, color='orange', linewidth=3, alpha=0.9, label=orange['label'])

# Yellow (full session, strategic)
xs = list(range(yellow['bar'], n))
ys = [yellow['anchor'] + yellow['slope'] * (x - yellow['bar']) for x in xs]
ax.plot(xs, ys, color='#FFD700', linewidth=3, alpha=0.9, label=yellow['label'])

# Blue (active until break at bar 6, then faded)
xs_active = list(range(blue['bar'], blue['break_bar'] + 1))
ys_active = [blue['anchor'] + blue['slope'] * (x - blue['bar']) for x in xs_active]
ax.plot(xs_active, ys_active, color='deepskyblue', linewidth=2.5, alpha=0.9, label=blue['label'])
# After break: faded extension
xs_faded = list(range(blue['break_bar'], min(n, blue['break_bar'] + 15)))
ys_faded = [blue['anchor'] + blue['slope'] * (x - blue['bar']) for x in xs_faded]
ax.plot(xs_faded, ys_faded, color='deepskyblue', linewidth=1, alpha=0.25, linestyle='--')

# Purple profit protection (only visible from bar 32)
xs_pp = list(range(purple_pp['visible_from'], n))
ys_pp = [purple_pp['anchor'] + purple_pp['slope'] * (x - purple_pp['bar']) for x in xs_pp]
ax.plot(xs_pp, ys_pp, color='purple', linewidth=2, alpha=0.85, label=purple_pp['label'])
# Dotted extension showing where it came from
xs_origin = list(range(purple_pp['bar'], purple_pp['visible_from']))
ys_origin = [purple_pp['anchor'] + purple_pp['slope'] * (x - purple_pp['bar']) for x in xs_origin]
ax.plot(xs_origin, ys_origin, color='purple', linewidth=1, alpha=0.2, linestyle=':')

# --- ANNOTATIONS ---

# Blue break event
ax.annotate('BLUE BREAK\n(resolve begins)', xy=(6, closes[6]),
            xytext=(8, closes[6] + 60), fontsize=9, color='deepskyblue', fontweight='bold',
            arrowprops=dict(arrowstyle='->', color='deepskyblue'))

# Yellow break event
ax.annotate('YELLOW BREAK\n(max conviction)', xy=(14, closes[14]),
            xytext=(16, closes[14] + 50), fontsize=9, color='#B8860B', fontweight='bold',
            arrowprops=dict(arrowstyle='->', color='#B8860B'))

# Profit protection creation
ax.annotate('PROFIT PROTECTION\ncreated here\n(structure proven)', xy=(32, ys_pp[0]),
            xytext=(35, ys_pp[0] + 60), fontsize=8, color='purple',
            arrowprops=dict(arrowstyle='->', color='purple'))

# Zone labels
ax.text(3, orange['anchor'] + 20, 'CEILING ZONE', fontsize=9, color='orange', alpha=0.7, ha='center')
ax.text(3, (orange['anchor'] + blue['anchor'] + blue['slope']*3) / 2,
        'COMPRESSION\nZONE', fontsize=10, color='steelblue', alpha=0.6, ha='center', va='center')
ax.text(40, yellow['anchor'] + yellow['slope'] * 40 - 80,
        'RESOLVE ZONE\n(bearish)', fontsize=10, color='red', alpha=0.5, ha='center')

# Active line count
ax.text(0.98, 0.98, 'ACTIVE LINES: 4\n'
        'Orange (strategic)\n'
        'Yellow (strategic)\n'
        'Blue (broken → faded)\n'
        'Purple PP (from bar 32)',
        transform=ax.transAxes, fontsize=9, va='top', ha='right',
        bbox=dict(boxstyle='round', facecolor='white', alpha=0.9))

# --- AXIS ---
ticks = list(range(0, n, 5))
labels = [times[t] for t in ticks]
ax.set_xticks(ticks); ax.set_xticklabels(labels, rotation=45, fontsize=8)
ax.set_ylabel('Price', fontsize=10)
ax.set_xlabel('Time', fontsize=10)
ax.legend(loc='upper left', fontsize=9)
ax.grid(True, alpha=0.1)
ax.set_xlim(-2, n + 2)

plt.tight_layout()
plt.show()
