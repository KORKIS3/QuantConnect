"""Chart with lines + trade placement for 02/11."""
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
times = [data.iloc[i]['time'].strftime('%H:%M') for i in range(n)]

fig, ax = plt.subplots(figsize=(19, 10))
fig.suptitle("02/11 — Lines + Trade Placement (Scott's methodology)", fontsize=13, fontweight='bold')

# Candlesticks
for i in range(n):
    color = '#26a69a' if closes[i] >= opens[i] else '#ef5350'
    ax.plot([i, i], [lows[i], highs[i]], color='#555', linewidth=0.6)
    body_lo = min(opens[i], closes[i]); body_hi = max(opens[i], closes[i])
    rect = Rectangle((i - 0.35, body_lo), 0.7, max(body_hi - body_lo, 2),
                     facecolor=color, edgecolor='#333', linewidth=0.4)
    ax.add_patch(rect)

# === STRATEGIC LINES ===

# Orange: session high 50585 (bar 2), descending
o_anchor = 50585; o_bar = 2; o_slope = -1.8
xs = list(range(o_bar, n))
ys = [o_anchor + o_slope * (x - o_bar) for x in xs]
ax.plot(xs, ys, color='orange', linewidth=2.5, alpha=0.9, label='Orange (strategic ceiling)')

# Yellow: session low 50459 (bar 0), ascending
y_anchor = 50459; y_bar = 0; y_slope = +1.8
xs = list(range(y_bar, n))
ys = [y_anchor + y_slope * (x - y_bar) for x in xs]
ax.plot(xs, ys, color='#FFD700', linewidth=2.5, alpha=0.9, label='Yellow (strategic floor)')

# Purple ORIGINAL: from 50585 (bar 2), containment slope -2.93
po_anchor = 50585; po_bar = 2; po_slope = -2.93
xs = list(range(po_bar, n))
ys = [po_anchor + po_slope * (x - po_bar) for x in xs]
ax.plot(xs, ys, color='purple', linewidth=2.2, alpha=0.85, label='Purple ORIG (thesis)')

# Blue ORIGINAL: from 50459 (bar 0), ascending, broken at bar 6
b_anchor = 50459; b_bar = 0; b_slope = +9.0
xs_active = list(range(b_bar, 7))
ys_active = [b_anchor + b_slope * (x - b_bar) for x in xs_active]
ax.plot(xs_active, ys_active, color='deepskyblue', linewidth=2.2, alpha=0.9, label='Blue ORIG (broken bar 6)')
xs_faded = list(range(6, 20))
ys_faded = [b_anchor + b_slope * (x - b_bar) for x in xs_faded]
ax.plot(xs_faded, ys_faded, color='deepskyblue', linewidth=1, alpha=0.2, linestyle='--')

# Purple TACTICAL: from 50544 (bar 16), slope -8.80, visible from bar 32
pt_anchor = 50544; pt_bar = 16; pt_slope = -8.80
xs = list(range(32, n))
ys = [pt_anchor + pt_slope * (x - pt_bar) for x in xs]
ax.plot(xs, ys, color='magenta', linewidth=2, alpha=0.8, label='Purple TACT (profit protection)')
xs_dot = list(range(pt_bar, 32))
ys_dot = [pt_anchor + pt_slope * (x - pt_bar) for x in xs_dot]
ax.plot(xs_dot, ys_dot, color='magenta', linewidth=0.8, alpha=0.2, linestyle=':')

# === CONTINUATION BLUES (ascending, from proven lows) ===
cont_blues = [(21, 50386), (27, 50364), (44, 50140), (51, 50078), (56, 50028)]
cb_slope = +1.83

for idx, (p1_bar, p1_low) in enumerate(cont_blues):
    xs = list(range(p1_bar, n))
    ys = [p1_low + cb_slope * (x - p1_bar) for x in xs]
    is_newest = (idx == len(cont_blues) - 1)
    lw = 2.0 if is_newest else 1.2
    alpha = 0.85 if is_newest else 0.45 + idx * 0.08
    ax.plot(xs, ys, color='cyan', linewidth=lw, alpha=alpha)
    ax.scatter([p1_bar], [p1_low], color='cyan', s=30, marker='^', zorder=5, alpha=0.7)

# === TRADES ===
# Based on accumulated evidence + conviction:

# TRADE 1: SHORT entry after Yellow break (bar 14-15)
# Evidence: Blue broken (bar 6) + Yellow broken (bar 14) = max conviction bearish
# Entry: bar 15 close (50501) — one bar after Yellow break for confirmation
trade1_bar = 15; trade1_price = 50501
ax.scatter([trade1_bar], [trade1_price], color='red', s=250, marker='v', zorder=10, edgecolors='black', linewidths=1.5)
ax.annotate('SHORT ENTRY\nbar 15 (09:45)\nConviction: Blue+Yellow broken\nEvidence accumulated over 6 bars',
            xy=(trade1_bar, trade1_price), xytext=(trade1_bar + 3, trade1_price + 50),
            fontsize=8, color='red', fontweight='bold',
            arrowprops=dict(arrowstyle='->', color='red', lw=1.2))

# CONVICTION STRENGTHENING EVENTS (not exits — reasons to HOLD)
# Each continuation Blue break = resolve confirmed = hold
conviction_bars = [27, 32, 48, 56]
for cb in conviction_bars:
    if cb < n:
        ax.scatter([cb], [closes[cb] + 15], color='lime', s=60, marker='+', zorder=8, linewidths=2)

ax.annotate('conviction strengthens\n(each Blue break = hold)',
            xy=(32, closes[32] + 15), xytext=(35, closes[32] + 80),
            fontsize=7, color='lime',
            arrowprops=dict(arrowstyle='->', color='lime', lw=0.7))

# EXIT: session end — tactical purple never violated, conviction never weakened
trade3_bar = 57; trade3_price = closes[57]
ax.scatter([trade3_bar], [trade3_price], color='blue', s=200, marker='s', zorder=10, edgecolors='black', linewidths=1.5)
ax.annotate('EXIT (session end)\nbar 57 (10:27)\nTactical purple never broken\nConviction never weakened\nFull position held entire time',
            xy=(trade3_bar, trade3_price), xytext=(trade3_bar - 10, trade3_price + 100),
            fontsize=8, color='blue', fontweight='bold',
            arrowprops=dict(arrowstyle='->', color='blue', lw=1.2))

# P/L annotation
entry_price = 50501
exit_price = closes[57]
pl = entry_price - exit_price
ax.text(0.02, 0.02, f'RESULT: SHORT {entry_price:.0f} to {exit_price:.0f}\n'
        f'P/L: +{pl:.0f} pts (full position, no partial)\n\n'
        f'Entry: accumulated evidence (Blue+Yellow broken)\n'
        f'Hold: conviction STRENGTHENED 4x (Blue breaks)\n'
        f'No partial TP: conviction never weakened\n'
        f'Exit: session discipline (10:27)\n\n'
        f'Partial TP only when conviction WEAKENS:\n'
        f'  - price fails to break continuation Blue\n'
        f'  - price reclaims broken structure\n'
        f'  - tactical purple approached from below',
        transform=ax.transAxes, fontsize=8, va='bottom',
        bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.9))

# Legend and axis
ticks = list(range(0, n, 5))
labels = [times[t] for t in ticks]
ax.set_xticks(ticks); ax.set_xticklabels(labels, rotation=45, fontsize=8)
ax.set_ylabel('Price'); ax.set_xlabel('Time')
ax.legend(loc='upper right', fontsize=8)
ax.grid(True, alpha=0.1)
ax.set_xlim(-2, n + 2)

plt.tight_layout()
plt.savefig('chart_0211_lines_trades.png', dpi=150, bbox_inches='tight')
print("Chart saved to chart_0211_lines_trades.png")
plt.show()
