"""
Research: Dynamic Structure Promotion
Lines evolve. Weak → stronger replacement → dominant.
Show only the CURRENT BEST structure at any moment.

Key insight: Scott draws lines where price REPEATEDLY NEGOTIATES.
Not from the earliest legal pivot. From the most RELEVANT pivots.

Approach:
- Track ALL swing points as they form
- At each bar, compute the BEST purple and BEST blue from available pivots
- "Best" = highest quality score based on recent interaction
- Lines upgrade as better pivot pairs emerge
- Show only the promoted (dominant) line at each moment
"""
import os, sys
import pandas as pd, pytz, numpy as np
import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from matplotlib.widgets import Slider
from dataclasses import dataclass
from typing import List, Optional, Tuple

_EST = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")


def compute_line_relevance(p1_bar, p1_price, p2_bar, p2_price, slope,
                           direction, current_bar, highs, lows, closes,
                           interaction_dist=15.0):
    """Score how relevant a line is RIGHT NOW based on recent price behavior."""
    touches = 0
    near_bars = 0
    recent_interactions = 0  # interactions in last 20 bars (recency weighted)

    for b in range(p2_bar, current_bar + 1):
        line_val = p1_price + slope * (b - p1_bar)

        if direction == "RESISTANCE":
            dist = line_val - highs[b]
            if 0 <= dist <= interaction_dist:
                touches += 1
                if b >= current_bar - 20:
                    recent_interactions += 2  # recency bonus
            if abs(line_val - closes[b]) <= interaction_dist * 2:
                near_bars += 1
        else:  # SUPPORT
            dist = lows[b] - line_val
            if 0 <= dist <= interaction_dist:
                touches += 1
                if b >= current_bar - 20:
                    recent_interactions += 2
            if abs(closes[b] - line_val) <= interaction_dist * 2:
                near_bars += 1

    # Slope penalty: extreme slopes leave price quickly
    slope_abs = abs(slope)
    if slope_abs <= 2:
        slope_score = 10
    elif slope_abs <= 4:
        slope_score = 5
    elif slope_abs <= 7:
        slope_score = 0
    else:
        slope_score = -10

    # Recency: lines from recent pivots score higher
    bars_since_p2 = current_bar - p2_bar
    recency_score = max(0, 20 - bars_since_p2 * 0.1)

    # Pivot separation: P1 and P2 should be meaningfully apart
    separation = p2_bar - p1_bar
    sep_score = min(separation / 5, 10)  # max 10 pts for 50+ bar separation

    score = (touches * 15 +
             recent_interactions * 5 +
             near_bars * 1 +
             slope_score +
             recency_score +
             sep_score)

    return score, touches, near_bars


def find_best_line(pivots, direction, current_bar, highs, lows, closes,
                   session_extreme_bar, session_extreme_price,
                   interaction_dist=15.0):
    """Find the best line from available pivots. Returns (p1, p2, slope, score) or None."""
    if len(pivots) < 1:
        return None

    candidates = []

    # Try session extreme as P1 + each pivot as P2
    for p2_bar, p2_price, _ in pivots:
        if p2_bar <= session_extreme_bar:
            continue
        if direction == "RESISTANCE" and p2_price >= session_extreme_price:
            continue
        if direction == "SUPPORT" and p2_price <= session_extreme_price:
            continue

        slope = (p2_price - session_extreme_price) / (p2_bar - session_extreme_bar)
        if direction == "RESISTANCE" and slope >= 0:
            continue
        if direction == "SUPPORT" and slope <= 0:
            continue
        if abs(slope) > 12:
            continue

        score, touches, near = compute_line_relevance(
            session_extreme_bar, session_extreme_price, p2_bar, p2_price,
            slope, direction, current_bar, highs, lows, closes, interaction_dist)
        candidates.append((session_extreme_bar, session_extreme_price,
                          p2_bar, p2_price, slope, score, touches, near))

    # Try pivot-to-pivot pairs (connecting two swing points)
    for i in range(len(pivots)):
        for j in range(i + 1, len(pivots)):
            p1_bar, p1_price, _ = pivots[i]
            p2_bar, p2_price, _ = pivots[j]

            if direction == "RESISTANCE" and p2_price >= p1_price:
                continue  # need descending
            if direction == "SUPPORT" and p2_price <= p1_price:
                continue  # need ascending

            slope = (p2_price - p1_price) / (p2_bar - p1_bar)
            if direction == "RESISTANCE" and slope >= 0:
                continue
            if direction == "SUPPORT" and slope <= 0:
                continue
            if abs(slope) > 12:
                continue

            score, touches, near = compute_line_relevance(
                p1_bar, p1_price, p2_bar, p2_price,
                slope, direction, current_bar, highs, lows, closes, interaction_dist)
            candidates.append((p1_bar, p1_price, p2_bar, p2_price, slope, score, touches, near))

    if not candidates:
        return None

    # Return the best
    candidates.sort(key=lambda x: x[5], reverse=True)
    best = candidates[0]
    return best  # (p1_bar, p1_price, p2_bar, p2_price, slope, score, touches, near)


def run_chart(target_date):
    fpath = os.path.join(_DATA_ROOT, f"CBOT_MINI_YM1_{target_date}.csv")
    df = pd.read_csv(fpath, index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
    ds = pd.Timestamp(f'{target_date} 09:30', tz=_EST)
    de = pd.Timestamp(f'{target_date} 16:59', tz=_EST)
    day = df[(df.index >= ds) & (df.index <= de)]

    n = len(day)
    highs = day['High'].values
    lows = day['Low'].values
    closes = day['Close'].values
    opens = day['Open'].values
    times = day.index

    # Detect all swings upfront
    swing_threshold = 10.0
    swing_highs = []  # (bar, price, significance)
    swing_lows = []

    session_high = -1e30
    session_high_bar = 0
    session_low = 1e30
    session_low_bar = 0

    for i in range(n):
        if highs[i] > session_high:
            session_high = highs[i]
            session_high_bar = i
        if lows[i] < session_low:
            session_low = lows[i]
            session_low_bar = i

    # Detect swings
    for j in range(1, n - 1):
        hi_j = highs[j]
        left = hi_j - highs[j-1]
        right = hi_j - highs[j+1]
        if left >= swing_threshold and right >= swing_threshold:
            swing_highs.append((j, hi_j, (left + right) / 2))

        lo_j = lows[j]
        left = lows[j-1] - lo_j
        right = lows[j+1] - lo_j
        if left >= swing_threshold and right >= swing_threshold:
            swing_lows.append((j, lo_j, (left + right) / 2))

    print(f"\n{target_date} — Dynamic Structure Promotion")
    print(f"  Bars: {n}, Swing highs: {len(swing_highs)}, Swing lows: {len(swing_lows)}")
    print(f"  Session high: {session_high:.0f} (bar {session_high_bar})")
    print(f"  Session low: {session_low:.0f} (bar {session_low_bar})")

    # Orange/yellow history
    sh = -1e30
    sl = 1e30
    orange_hist = []
    yellow_hist = []
    sh_at = []  # (bar, price) session high at each bar
    sl_at = []
    for i in range(n):
        if highs[i] > sh:
            sh = highs[i]
            orange_hist.append((i, highs[i]))
        if lows[i] < sl:
            sl = lows[i]
            yellow_hist.append((i, lows[i]))
        sh_at.append((sh, [b for b, _ in orange_hist][-1] if orange_hist else 0))
        sl_at.append((sl, [b for b, _ in yellow_hist][-1] if yellow_hist else 0))

    # --- CHART ---
    fig, ax = plt.subplots(figsize=(18, 10))
    plt.subplots_adjust(bottom=0.12)
    ax_slider = plt.axes([0.12, 0.04, 0.7, 0.03])
    slider = Slider(ax_slider, 'Bar', 0, n - 1, valinit=n - 1, valstep=1)

    def draw_frame(frame):
        ax.clear()
        frame = int(frame)
        view_start = max(0, frame - 90)

        # Candles
        for i in range(view_start, frame + 1):
            color = 'green' if closes[i] >= opens[i] else 'red'
            ax.plot([i, i], [lows[i], highs[i]], color='black', linewidth=0.5)
            body_lo = min(opens[i], closes[i])
            body_hi = max(opens[i], closes[i])
            rect = Rectangle((i - 0.3, body_lo), 0.6, max(body_hi - body_lo, 1),
                             facecolor=color, edgecolor='black', linewidth=0.5)
            ax.add_patch(rect)

        vis_highs = highs[view_start:frame+1]
        vis_lows = lows[view_start:frame+1]
        p_min = min(vis_lows) - 15
        p_max = max(vis_highs) + 15

        # Orange (latest only solid)
        for idx, (bar, price) in enumerate(orange_hist):
            if bar > frame:
                break
            xs = list(range(max(bar, view_start), frame + 1))
            ys = [price + (-1.83) * (x - bar) for x in xs]
            ys_c = [y if p_min <= y <= p_max else np.nan for y in ys]
            is_latest = (idx == len(orange_hist) - 1) or (idx < len(orange_hist) - 1 and orange_hist[idx+1][0] > frame)
            ax.plot(xs, ys_c, color='orange', linewidth=2.2 if is_latest else 0.7,
                    alpha=0.9 if is_latest else 0.2, linestyle='-' if is_latest else '--')

        # Yellow
        for idx, (bar, price) in enumerate(yellow_hist):
            if bar > frame:
                break
            xs = list(range(max(bar, view_start), frame + 1))
            ys = [price + 1.83 * (x - bar) for x in xs]
            ys_c = [y if p_min <= y <= p_max else np.nan for y in ys]
            is_latest = (idx == len(yellow_hist) - 1) or (idx < len(yellow_hist) - 1 and yellow_hist[idx+1][0] > frame)
            ax.plot(xs, ys_c, color='#DAA520', linewidth=2.2 if is_latest else 0.7,
                    alpha=0.9 if is_latest else 0.2, linestyle='-' if is_latest else '--')

        # Find BEST purple and BEST blue at this frame
        available_sh = [(b, p, s) for b, p, s in swing_highs if b <= frame]
        available_sl = [(b, p, s) for b, p, s in swing_lows if b <= frame]

        # Session high/low at this frame
        curr_sh, curr_sh_bar = sh_at[frame]
        curr_sl, curr_sl_bar = sl_at[frame]

        best_purple = find_best_line(available_sh, "RESISTANCE", frame,
                                     highs, lows, closes, curr_sh_bar, curr_sh)
        best_blue = find_best_line(available_sl, "SUPPORT", frame,
                                   highs, lows, closes, curr_sl_bar, curr_sl)

        # Draw best purple
        if best_purple:
            p1b, p1p, p2b, p2p, slope, score, touches, near = best_purple
            xs = list(range(max(p1b, view_start), frame + 1))
            ys = [p1p + slope * (x - p1b) for x in xs]
            ys_c = [y if p_min - 10 <= y <= p_max + 10 else np.nan for y in ys]
            ax.plot(xs, ys_c, color='#8B008B', linewidth=2.5, alpha=0.9)
            # P1 and P2 markers
            if view_start <= p1b <= frame:
                ax.scatter([p1b], [p1p], color='purple', s=60, marker='v', zorder=5)
            if view_start <= p2b <= frame:
                ax.scatter([p2b], [p2p], color='purple', s=60, marker='v', zorder=5)
            # Label
            last_v = None
            for j in range(len(ys_c)-1, -1, -1):
                if ys_c[j] is not None and not np.isnan(ys_c[j]):
                    last_v = (xs[j], ys_c[j])
                    break
            if last_v:
                ax.annotate(f'Purple Q:{score:.0f} T:{touches}', xy=last_v,
                           fontsize=8, color='purple', ha='left', fontweight='bold')

        # Draw best blue
        if best_blue:
            p1b, p1p, p2b, p2p, slope, score, touches, near = best_blue
            xs = list(range(max(p1b, view_start), frame + 1))
            ys = [p1p + slope * (x - p1b) for x in xs]
            ys_c = [y if p_min - 10 <= y <= p_max + 10 else np.nan for y in ys]
            ax.plot(xs, ys_c, color='#1E90FF', linewidth=2.5, alpha=0.9)
            if view_start <= p1b <= frame:
                ax.scatter([p1b], [p1p], color='blue', s=60, marker='^', zorder=5)
            if view_start <= p2b <= frame:
                ax.scatter([p2b], [p2p], color='blue', s=60, marker='^', zorder=5)
            last_v = None
            for j in range(len(ys_c)-1, -1, -1):
                if ys_c[j] is not None and not np.isnan(ys_c[j]):
                    last_v = (xs[j], ys_c[j])
                    break
            if last_v:
                ax.annotate(f'Blue Q:{score:.0f} T:{touches}', xy=last_v,
                           fontsize=8, color='blue', ha='left', fontweight='bold')

        # Swing markers
        for bar, price, _ in available_sh:
            if view_start <= bar <= frame:
                ax.scatter([bar], [price], color='#8B008B', s=20, marker='v', alpha=0.4)
        for bar, price, _ in available_sl:
            if view_start <= bar <= frame:
                ax.scatter([bar], [price], color='#1E90FF', s=20, marker='^', alpha=0.4)

        ax.set_title(f'{target_date} | Bar {frame} ({times[frame].strftime("%H:%M")}) | '
                     f'Dynamic Structure Promotion',
                     fontsize=11, fontweight='bold')
        ax.set_xlim(view_start - 1, frame + 5)
        ax.set_ylim(p_min, p_max)
        ax.set_ylabel('Price')
        ax.grid(True, alpha=0.15)
        tick_step = max(1, (frame - view_start) // 10)
        ticks = list(range(view_start, frame + 1, tick_step))
        ax.set_xticks(ticks)
        ax.set_xticklabels([times[t].strftime('%H:%M') for t in ticks if t < n], rotation=45, fontsize=8)
        fig.canvas.draw_idle()

    slider.on_changed(draw_frame)

    def on_key(event):
        if event.key == 'right': slider.set_val(min(slider.val + 1, n - 1))
        elif event.key == 'left': slider.set_val(max(slider.val - 1, 0))
        elif event.key == 'up': slider.set_val(min(slider.val + 10, n - 1))
        elif event.key == 'down': slider.set_val(max(slider.val - 10, 0))
        elif event.key == 'home': slider.set_val(0)
        elif event.key == 'end': slider.set_val(n - 1)
    fig.canvas.mpl_connect('key_press_event', on_key)

    draw_frame(n - 1)
    plt.show(block=True)


if __name__ == "__main__":
    target_date = sys.argv[1] if len(sys.argv) > 1 else "2026-05-05"
    run_chart(target_date)
