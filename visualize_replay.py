"""
visualize_replay.py — Bar-by-bar visual replay of the frozen ray engine.

Shows:
- Active strategic lines (bold)
- Retired lines (faded)
- Touch counts on each line
- Quadrant regions (shaded)
- Line birth/death events (annotated)
- Resolve state evolution

Use arrow keys or slider to step through bars.
"""
import os, sys
import pandas as pd, pytz, numpy as np
import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, FancyBboxPatch
from matplotlib.widgets import Slider
from frozen_ray_engine import FrozenRayEngine

_EST = pytz.timezone('US/Eastern')
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")

LINE_COLORS = {
    'ORANGE': 'orange', 'YELLOW': 'gold',
    'PURPLE_ORIGINAL': 'purple', 'BLUE_ORIGINAL': 'deepskyblue',
    'PURPLE_PROFIT': 'magenta', 'BLUE_PROFIT': 'lime',
}


def load_day(target_date):
    fpath = os.path.join(_DATA_ROOT, f'CBOT_MINI_YM1_{target_date}.csv')
    df = pd.read_csv(fpath, index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
    day_start = pd.Timestamp(f'{target_date} 09:30', tz=_EST)
    day_end = pd.Timestamp(f'{target_date} 16:59', tz=_EST)
    return df[(df.index >= day_start) & (df.index <= day_end)].reset_index()


def run_replay(target_date):
    data = load_day(target_date)
    n = len(data)
    highs = data['High'].values
    lows = data['Low'].values
    closes = data['Close'].values
    opens = data['Open'].values
    times = [data.iloc[i]['time'].strftime('%H:%M') for i in range(n)]

    # Run engine and capture state at each bar
    snapshots = []
    engine = FrozenRayEngine(swing_threshold=10.0)

    # Create initial provisional lines
    engine.lines = []
    from frozen_ray_engine import FrozenRay
    engine.lines.append(FrozenRay(
        line_id=engine._new_id(), line_type="PURPLE_ORIGINAL", authority_rank=2,
        anchor_price=float(data.iloc[0]['High']), anchor_bar=0, slope=0.0,
        status="PROVISIONAL", direction="RESISTANCE", created_at_bar=0,
    ))
    engine.lines.append(FrozenRay(
        line_id=engine._new_id(), line_type="BLUE_ORIGINAL", authority_rank=2,
        anchor_price=float(data.iloc[0]['Low']), anchor_bar=0, slope=0.0,
        status="PROVISIONAL", direction="SUPPORT", created_at_bar=0,
    ))

    for i in range(n):
        engine.process_bar(float(opens[i]), float(highs[i]), float(lows[i]), float(closes[i]))
        # Snapshot: copy line states
        snap = {
            'bar': i,
            'quadrant': engine.quadrant_state,
            'lines': [(l.line_id, l.line_type, l.authority_rank, l.anchor_price,
                       l.anchor_bar, l.slope, l.status, l.touch_count, l.direction)
                      for l in engine.lines],
            'n_active': len([l for l in engine.lines if l.status == "FROZEN"]),
            'n_retired': len([l for l in engine.lines if l.status == "RETIRED"]),
            'events': [],
        }
        snapshots.append(snap)

    # --- INTERACTIVE CHART ---
    fig, ax = plt.subplots(figsize=(18, 10))
    plt.subplots_adjust(bottom=0.15)

    # Slider
    ax_slider = plt.axes([0.15, 0.03, 0.7, 0.03])
    slider = Slider(ax_slider, 'Bar', 0, n - 1, valinit=n - 1, valstep=1)

    def draw_frame(frame):
        ax.clear()
        frame = int(frame)
        snap = snapshots[frame]

        # Title
        ax.set_title(f'{target_date} | Bar {frame} ({times[frame]}) | '
                     f'Quadrant: {snap["quadrant"]} | '
                     f'Active: {snap["n_active"]} | Retired: {snap["n_retired"]}',
                     fontsize=11, fontweight='bold')

        # Draw candles up to current frame
        view_start = max(0, frame - 60)
        for i in range(view_start, frame + 1):
            color = 'green' if closes[i] >= opens[i] else 'red'
            ax.plot([i, i], [lows[i], highs[i]], color='black', linewidth=0.5)
            body_lo = min(opens[i], closes[i]); body_hi = max(opens[i], closes[i])
            rect = Rectangle((i - 0.3, body_lo), 0.6, max(body_hi - body_lo, 1),
                             facecolor=color, edgecolor='black', linewidth=0.5)
            ax.add_patch(rect)

        # Draw lines from snapshot
        for (lid, ltype, auth, anchor_p, anchor_b, slope, status, touches, direction) in snap['lines']:
            if anchor_b > frame:
                continue  # not yet created
            color = LINE_COLORS.get(ltype, 'gray')
            start = anchor_b
            end = frame

            # For retired lines, only draw up to retirement
            # (we don't have retired_at in snapshot, so draw to frame but faded)
            xs = list(range(max(start, view_start), end + 1))
            if not xs:
                continue
            ys = [anchor_p + slope * (x - anchor_b) for x in xs]

            if status == "RETIRED":
                ax.plot(xs, ys, color=color, linewidth=0.8, linestyle='--', alpha=0.25)
            elif status == "FROZEN":
                lw = 2.5 if auth <= 2 else 1.5
                ax.plot(xs, ys, color=color, linewidth=lw, alpha=0.9)
                # Touch count label at end of line
                if xs:
                    ax.annotate(f'T:{touches}', xy=(xs[-1], ys[-1]),
                               fontsize=7, color=color, ha='left', va='center')
            elif status == "PROVISIONAL":
                ax.scatter([anchor_b], [anchor_p], color=color, s=40, marker='o', alpha=0.5)

        # Quadrant shading
        # Find active resistance and support for shading
        active_res = None
        active_sup = None
        for (lid, ltype, auth, anchor_p, anchor_b, slope, status, touches, direction) in snap['lines']:
            if status != "FROZEN":
                continue
            val_at_frame = anchor_p + slope * (frame - anchor_b)
            if direction == "RESISTANCE" and (active_res is None or auth < active_res[0]):
                active_res = (auth, val_at_frame)
            if direction == "SUPPORT" and (active_sup is None or auth < active_sup[0]):
                active_sup = (auth, val_at_frame)

        if active_res and active_sup:
            res_val = active_res[1]
            sup_val = active_sup[1]
            ax.axhspan(sup_val, res_val, alpha=0.05, color='blue', label='Active Quadrant')
            ax.axhline(res_val, color='red', linewidth=0.5, linestyle=':', alpha=0.3)
            ax.axhline(sup_val, color='green', linewidth=0.5, linestyle=':', alpha=0.3)

        # Axis
        price_range = max(highs[view_start:frame+1]) - min(lows[view_start:frame+1])
        y_min = min(lows[view_start:frame+1]) - price_range * 0.05
        y_max = max(highs[view_start:frame+1]) + price_range * 0.05
        ax.set_xlim(view_start - 1, frame + 5)
        ax.set_ylim(y_min, y_max)
        ax.set_ylabel('Price')
        ax.grid(True, alpha=0.15)

        # X ticks
        tick_step = max(1, (frame - view_start) // 10)
        ticks = list(range(view_start, frame + 1, tick_step))
        labels = [times[t] if t < n else '' for t in ticks]
        ax.set_xticks(ticks)
        ax.set_xticklabels(labels, rotation=45, fontsize=8)

        fig.canvas.draw_idle()

    slider.on_changed(draw_frame)

    # Key bindings
    def on_key(event):
        if event.key == 'right':
            slider.set_val(min(slider.val + 1, n - 1))
        elif event.key == 'left':
            slider.set_val(max(slider.val - 1, 0))
        elif event.key == 'up':
            slider.set_val(min(slider.val + 10, n - 1))
        elif event.key == 'down':
            slider.set_val(max(slider.val - 10, 0))

    fig.canvas.mpl_connect('key_press_event', on_key)

    draw_frame(n - 1)
    plt.show()


if __name__ == "__main__":
    target_date = sys.argv[1] if len(sys.argv) > 1 else '2026-02-11'
    run_replay(target_date)
