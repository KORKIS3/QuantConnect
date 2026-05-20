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

# PURPLE ORIGINAL (strategic): From session high, containment slope
# P1 = 50585 (bar 2, session high)
# Min legal slope = -2.93 (binding: bar 16 high 50544)
# Answers: "Am I still right?" (thesis line)
purple_orig = {'anchor': 50585, 'bar': 2, 'slope': -2.93,
               'label': 'PURPLE ORIGINAL (strategic thesis)'}

# PURPLE TACTICAL (profit protection): From first failed bounce
# P1 = 50544 (bar 16, bounce peak)
# Min legal slope = -8.80 (binding: bar 31 high 50412)
# Answers: "How much profit do I protect?"
purple_pp = {'anchor': 50544, 'bar': 16, 'slope': -8.80,
             'label': 'PURPLE TACTICAL (profit protection)', 'visible_from': 32}

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

# --- Draw ZONES (only meaningful structural regions) ---

# Compression zone: between Orange and Blue BEFORE break (bars 0-6)
# This represents: "price is contained between strategic boundaries"
# Scott concept: price living inside the quadrant
for i in range(0, 7):
    o_val = orange['anchor'] + orange['slope'] * (i - orange['bar'])
    b_val = blue['anchor'] + blue['slope'] * (i - blue['bar'])
    ax.fill_between([i-0.5, i+0.5], [b_val, b_val], [o_val, o_val],
                    color='lightblue', alpha=0.06)

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
# After break: faded extension (line persists in memory, authority decayed)
xs_faded = list(range(blue['break_bar'], min(n, blue['break_bar'] + 15)))
ys_faded = [blue['anchor'] + blue['slope'] * (x - blue['bar']) for x in xs_faded]
ax.plot(xs_faded, ys_faded, color='deepskyblue', linewidth=1, alpha=0.2, linestyle='--')

# --- CONTINUATION EVIDENCE BLUES ---
# Blue = support = BELOW price. Always ASCENDING rays (not flat shelves).
# Anchor at P1 low and immediately angle upward from there.
#
# RETROACTIVE RECOGNITION:
# P1 exists immediately (the low happened).
# Line does NOT become visible immediately.
# Wait: bounce → wiggle → resume → new low confirmed
# ONLY after proof: activate line
# BUT once activated: draw it beginning from ORIGINAL P1.
# "That low turned out to matter."
#
# Each continuation Blue creates a NEW QUADRANT.
# Question: "What region is price currently living inside?"

# Scott's specified continuation points for 02/11:
continuation_blues = [
    # (p1_bar, p1_low, proof_bar)
    (21, 50386, 27),   # 09:51 low → proven when new low 50364 at bar 27
    (27, 50364, 32),   # 09:57 low → proven when new low 50342 at bar 32
    (44, 50140, 48),   # 10:14 low → proven when new low 50110 at bar 48
    (51, 50078, 56),   # 10:21 low → proven when new low 50028 at bar 56
    (56, 50028, 59),   # 10:26 low → proven when price continues lower
]

# Fixed ascending slope (same geometry as yellow: +1.83 pts/bar)
blue_slope = +1.83

for idx, (p1_bar, p1_low, proof_bar) in enumerate(continuation_blues):
    if proof_bar >= n:
        continue
    # Once proven, draw the FULL ray from P1 onward (retroactive recognition)
    xs_full = list(range(p1_bar, n))
    ys_full = [p1_low + blue_slope * (x - p1_bar) for x in xs_full]

    # Verify containment: line must stay BELOW all lows from P1 onward
    # If any low is below the line, adjust slope down
    actual_slope = blue_slope
    for i in range(p1_bar + 1, n):
        line_val = p1_low + actual_slope * (i - p1_bar)
        if lows[i] < line_val:
            # Need shallower slope to stay below this low
            required = (lows[i] - p1_low) / (i - p1_bar)
            if required < actual_slope:
                actual_slope = required

    # Ensure still positive (ascending)
    actual_slope = max(0.05, actual_slope)

    # Recompute with legal slope
    ys_full = [p1_low + actual_slope * (x - p1_bar) for x in xs_full]

    label = 'CONT. BLUE (evidence, ascending)' if idx == 0 else ''
    ax.plot(xs_full, ys_full, color='cyan', linewidth=1.6, alpha=0.7, linestyle='-', label=label)

    # P1 marker (where the low happened)
    ax.scatter([p1_bar], [p1_low], color='cyan', s=35, zorder=5, marker='^', alpha=0.8)

# Annotation
ax.annotate('continuation Blues:\nascending rays from proven lows\n'
            'retroactive: drawn FROM P1\nonce structure confirmed\n'
            'each creates new quadrant',
            xy=(continuation_blues[2][0], continuation_blues[2][1]),
            xytext=(continuation_blues[2][0] + 4, continuation_blues[2][1] + 100),
            fontsize=8, color='cyan',
            arrowprops=dict(arrowstyle='->', color='cyan', lw=0.8))

# Purple ORIGINAL (strategic, full session)
xs_po = list(range(purple_orig['bar'], n))
ys_po = [purple_orig['anchor'] + purple_orig['slope'] * (x - purple_orig['bar']) for x in xs_po]
ax.plot(xs_po, ys_po, color='purple', linewidth=2.5, alpha=0.85, label=purple_orig['label'])

# Purple TACTICAL (profit protection, only visible from bar 32)
xs_pp = list(range(purple_pp['visible_from'], n))
ys_pp = [purple_pp['anchor'] + purple_pp['slope'] * (x - purple_pp['bar']) for x in xs_pp]
ax.plot(xs_pp, ys_pp, color='magenta', linewidth=2, alpha=0.8, linestyle='-', label=purple_pp['label'])
# Dotted extension showing where it came from
xs_origin = list(range(purple_pp['bar'], purple_pp['visible_from']))
ys_origin = [purple_pp['anchor'] + purple_pp['slope'] * (x - purple_pp['bar']) for x in xs_origin]
ax.plot(xs_origin, ys_origin, color='magenta', linewidth=1, alpha=0.2, linestyle=':')

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
ax.annotate('TACTICAL PURPLE\ncreated here\n(structure proven)', xy=(32, ys_pp[0]),
            xytext=(35, ys_pp[0] + 60), fontsize=8, color='magenta',
            arrowprops=dict(arrowstyle='->', color='magenta'))

# Zone label (only the one that corresponds to a real concept)
ax.text(3, (orange['anchor'] + blue['anchor'] + blue['slope']*3) / 2,
        'CONTAINED\n(pre-break)', fontsize=9, color='steelblue', alpha=0.5, ha='center', va='center')

# Active line count
ax.text(0.98, 0.98, 'ACTIVE LINES: ~9\n'
        'Orange (strategic) ↘\n'
        'Yellow (strategic) ↗\n'
        'Purple ORIG (thesis) ↘\n'
        'Blue ORIG (broken) ↗\n'
        'Cont. Blue x5 (evidence) ↗\n'
        'Purple TACT (profit prot) ↘\n'
        '\nRULES:\n'
        'Blue/Yellow = ascending rays\n'
        'Purple/Orange = descending rays\n'
        'Lines = proven structure\n'
        'Each Blue = new quadrant\n'
        'Retroactive recognition:\n'
        '"that low turned out to matter"',
        transform=ax.transAxes, fontsize=7.5, va='top', ha='right',
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
