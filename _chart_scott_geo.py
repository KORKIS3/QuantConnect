"""Chart: Scott Geometry Engine output on 02/11 benchmark."""
import sys, os
import pandas as pd, pytz, numpy as np
import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from matplotlib.widgets import Slider
from scott_geometry_engine import ScottGeometryEngine

_EST = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")

LINE_COLORS = {
    'ORANGE': 'orange', 'YELLOW': '#DAA520',
    'PURPLE_ORIGINAL': 'purple', 'BLUE_ORIGINAL': 'deepskyblue',
    'CONTINUATION_BLUE': 'cyan', 'TACTICAL_PURPLE': 'magenta',
}

def run_chart(target_date, start_t="09:30", end_t="10:30"):
    fpath = os.path.join(_DATA_ROOT, f"CBOT_MINI_YM1_{target_date}.csv")
    df = pd.read_csv(fpath, index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
    ds = pd.Timestamp(f'{target_date} {start_t}', tz=_EST)
    de = pd.Timestamp(f'{target_date} {end_t}', tz=_EST)
    day = df[(df.index >= ds) & (df.index <= de)]

    n = len(day)
    highs = day['High'].values
    lows = day['Low'].values
    closes = day['Close'].values
    opens = day['Open'].values
    times = day.index

    engine = ScottGeometryEngine()
    engine.run_session(day)

    # Print summary
    print(f"\n{target_date} ({start_t}-{end_t}) — Scott Geometry Engine")
    print(f"  Bars: {n}")
    print(f"  Lines: {len(engine.lines)}")
    for l in engine.lines:
        print(f"    {l.line_type:<20} state={l.state:<10} anchor={l.anchor_price:.0f}(b{l.anchor_bar}) "
              f"slope={l.slope:+.2f} touches={l.touch_count}")

    # Chart
    fig, ax = plt.subplots(figsize=(18, 10))
    plt.subplots_adjust(bottom=0.12)
    ax_slider = plt.axes([0.12, 0.04, 0.7, 0.03])
    slider = Slider(ax_slider, 'Bar', 0, n - 1, valinit=n - 1, valstep=1)

    def draw_frame(frame):
        ax.clear()
        frame = int(frame)
        view_start = max(0, frame - 90)

        for i in range(view_start, frame + 1):
            color = '#26a69a' if closes[i] >= opens[i] else '#ef5350'
            ax.plot([i, i], [lows[i], highs[i]], color='#555', linewidth=0.6)
            body_lo = min(opens[i], closes[i])
            body_hi = max(opens[i], closes[i])
            rect = Rectangle((i - 0.35, body_lo), 0.7, max(body_hi - body_lo, 2),
                             facecolor=color, edgecolor='#333', linewidth=0.4)
            ax.add_patch(rect)

        vis_h = highs[view_start:frame+1]
        vis_l = lows[view_start:frame+1]
        p_min = min(vis_l) - 20
        p_max = max(vis_h) + 20

        # Draw lines
        for line in engine.lines:
            if line.created_bar > frame:
                continue
            # Skip broken yellows and oranges (only show current active)
            if line.line_type in ("YELLOW", "ORANGE") and line.state != "ACTIVE":
                continue
            color = LINE_COLORS.get(line.line_type, 'gray')
            start_b = max(line.anchor_bar, view_start)
            end_b = frame

            xs = list(range(start_b, end_b + 1))
            if not xs:
                continue
            ys = [line.value_at(x) for x in xs]
            # Clip to visible price range (generous margin)
            margin = (p_max - p_min) * 0.3
            ys_c = [y if (p_min - margin) <= y <= (p_max + margin) else np.nan for y in ys]

            # Skip if entire line is outside visible range
            if all(np.isnan(y) for y in ys_c):
                continue

            if line.state == "ACTIVE" or (line.state == "BROKEN" and line.broken_bar > frame):
                lw = 2.5 if line.line_type in ('ORANGE', 'YELLOW', 'PURPLE_ORIGINAL', 'BLUE_ORIGINAL') else 1.8
                ax.plot(xs, ys_c, color=color, linewidth=lw, alpha=0.9)
            elif line.state == "BROKEN":
                lw = 1.5 if line.line_type in ('PURPLE_ORIGINAL', 'BLUE_ORIGINAL') else 1.0
                ax.plot(xs, ys_c, color=color, linewidth=lw, linestyle='--', alpha=0.45)
            elif line.state == "RECLAIMED":
                ax.plot(xs, ys_c, color=color, linewidth=2.0, alpha=0.7)

        # Swing markers
        for b, p in engine.swing_highs:
            if view_start <= b <= frame:
                ax.scatter([b], [p], color='purple', s=25, marker='v', alpha=0.5, zorder=5)
        for b, p in engine.swing_lows:
            if view_start <= b <= frame:
                ax.scatter([b], [p], color='cyan', s=25, marker='^', alpha=0.5, zorder=5)

        ax.set_title(f'Scott Geometry — {target_date} | Bar {frame} ({times[frame].strftime("%H:%M")})',
                     fontsize=11, fontweight='bold')
        ax.set_xlim(view_start - 1, frame + 3)
        ax.set_ylim(p_min, p_max)
        ax.set_ylabel('Price')
        ax.grid(True, alpha=0.1)
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
    date = sys.argv[1] if len(sys.argv) > 1 else "2026-02-11"
    start = sys.argv[2] if len(sys.argv) > 2 else "09:30"
    end = sys.argv[3] if len(sys.argv) > 3 else "10:30"
    run_chart(date, start, end)
