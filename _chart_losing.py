"""Interactive chart for 2026-03-31 (-1378 pts worst day)."""
import pandas as pd, pytz, os
import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from evidence_engine import EvidenceEngine
from conviction_engine import ConvictionEngine

_EST = pytz.timezone('US/Eastern')
fpath = os.path.expanduser('~/Desktop/2YearsData/full_day/CBOT_MINI_YM1_2026-03-31.csv')
df = pd.read_csv(fpath, index_col=0, parse_dates=True)
df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
day = df[(df.index >= pd.Timestamp('2026-03-31 09:30', tz=_EST)) &
         (df.index <= pd.Timestamp('2026-03-31 16:59', tz=_EST))].reset_index()

n = len(day)
highs = day['High'].values; lows = day['Low'].values
closes = day['Close'].values; opens = day['Open'].values
times = [day.iloc[i]['time'].strftime('%H:%M') for i in range(n)]

# Run engines
evidence = EvidenceEngine()
evidence.run_session(day.set_index('time'))
conviction = ConvictionEngine(persistence_bars=3)
for bar, score, _ in evidence.belief_history:
    conviction.process_bar(bar, score)

# Trades from audit: 5 trades, -1378 total
trades = [
    (4, 23, 'SHORT', -424, 'TRANSITION'),
    (26, 74, 'LONG', -378, 'CONVICTION_LOST'),
    (87, 109, 'SHORT', -624, 'CONVICTION_LOST'),
    (194, 238, 'LONG', +38, 'CONVICTION_LOST'),
    (372, 441, 'LONG', +10, 'CONVICTION_LOST'),
]

# Plot
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(18, 11), gridspec_kw={'height_ratios': [3, 1]}, sharex=True)
fig.suptitle('2026-03-31 — WORST DAY (-1,378 pts) | 5 trades, 3 losers', fontsize=12, fontweight='bold')

# Candles
for i in range(n):
    color = '#26a69a' if closes[i] >= opens[i] else '#ef5350'
    ax1.plot([i, i], [lows[i], highs[i]], color='#555', linewidth=0.5)
    body_lo = min(opens[i], closes[i]); body_hi = max(opens[i], closes[i])
    rect = Rectangle((i-0.35, body_lo), 0.7, max(body_hi - body_lo, 2),
                     facecolor=color, edgecolor='#333', linewidth=0.3)
    ax1.add_patch(rect)

# Trade markers
for entry, exit_b, direction, pl, reason in trades:
    color = 'red' if pl < 0 else 'green'
    marker = 'v' if direction == 'SHORT' else '^'
    ax1.scatter([entry], [closes[entry]], color=color, s=150, marker=marker, zorder=10, edgecolors='black')
    ax1.scatter([exit_b], [closes[exit_b]], color=color, s=100, marker='s', zorder=10, edgecolors='black')
    ax1.plot([entry, exit_b], [closes[entry], closes[exit_b]], color=color, linewidth=1.5, alpha=0.5, linestyle='--')
    ax1.annotate(f'{direction}\n{pl:+.0f}\n{reason}', xy=(exit_b, closes[exit_b]),
                xytext=(exit_b+3, closes[exit_b]), fontsize=7, color=color)

ax1.set_ylabel('Price')
ax1.grid(True, alpha=0.1)

# Conviction panel
bars = [s[0] for s in conviction.state_history]
scores = [s[2] for s in conviction.state_history]
ax2.fill_between(bars, scores, 0, where=[s > 0 for s in scores], color='green', alpha=0.3)
ax2.fill_between(bars, scores, 0, where=[s < 0 for s in scores], color='red', alpha=0.3)
ax2.plot(bars, scores, color='black', linewidth=1)
ax2.axhline(5, color='green', linewidth=0.5, linestyle='--', alpha=0.5)
ax2.axhline(-5, color='red', linewidth=0.5, linestyle='--', alpha=0.5)
ax2.axhline(0, color='black', linewidth=0.5)
ax2.set_ylabel('Belief Score')
ax2.set_xlabel('Bar')
ax2.grid(True, alpha=0.1)

# State labels
prev_state = ""
for bar, state, score in conviction.state_history:
    if state != prev_state:
        ax2.annotate(state[:12], xy=(bar, score), fontsize=6, color='purple', rotation=30)
        prev_state = state

# X ticks
ticks = list(range(0, n, 30))
labels = [times[t] for t in ticks]
ax2.set_xticks(ticks); ax2.set_xticklabels(labels, rotation=45, fontsize=8)

plt.tight_layout()
plt.show()
