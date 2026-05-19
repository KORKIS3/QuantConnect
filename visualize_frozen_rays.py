"""
visualize_frozen_rays.py — Phase 1 visualization and audit tool.

Runs frozen ray engine on specified days, produces chart + audit report.
"""
import os, sys
import pandas as pd, pytz, numpy as np
import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
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
    if not os.path.exists(fpath):
        return None
    df = pd.read_csv(fpath, index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
    day_start = pd.Timestamp(f'{target_date} 09:30', tz=_EST)
    day_end = pd.Timestamp(f'{target_date} 16:59', tz=_EST)
    return df[(df.index >= day_start) & (df.index <= day_end)].reset_index()

def run_and_visualize(target_date, show_chart=True):
    """Run engine on a day, validate, optionally show chart."""
    data = load_day(target_date)
    if data is None:
        print(f"{target_date}: DATA NOT FOUND")
        return None

    n = len(data)
    engine = FrozenRayEngine(swing_threshold=10.0)
    engine.run_session(data)

    # Validate
    violations = engine.validate_containment()

    # Report
    print(f"\n{'='*70}")
    print(f"  {target_date}  |  {n} bars  |  Quadrant: {engine.quadrant_state}")
    print(f"{'='*70}")
    print(f"  Lines created: {len(engine.lines)}")
    print(f"  Active: {len(engine.get_active_lines())}")
    print(f"  Containment violations: {len(violations)}")
    if violations:
        for v in violations[:5]:
            print(f"    LINE {v['line_id']} ({v['line_type']}) bar {v['bar']}: violation={v['violation']:.1f}")

    print(f"\n  {'ID':<4} {'Type':<16} {'Auth':>4} {'Status':<10} {'Anchor':>7} {'Slope':>7} {'Touches':>7} {'Adj':>4}")
    print(f"  {'-'*70}")
    for line in engine.lines:
        print(f"  {line.line_id:<4} {line.line_type:<16} {line.authority_rank:>4} {line.status:<10} "
              f"{line.anchor_price:>7.0f} {line.slope:>+7.2f} {line.touch_count:>7} {line.wick_adjust_count:>4}")

    if not show_chart:
        return engine

    # --- CHART ---
    fig, ax = plt.subplots(figsize=(18, 10))
    fig.suptitle(f'FROZEN RAY ENGINE — {target_date} | Quadrant: {engine.quadrant_state} | Violations: {len(violations)}',
                 fontsize=12, fontweight='bold')

    highs = data['High'].values
    lows = data['Low'].values
    closes = data['Close'].values
    opens = data['Open'].values

    # Candlesticks
    for i in range(n):
        color = 'green' if closes[i] >= opens[i] else 'red'
        ax.plot([i, i], [lows[i], highs[i]], color='black', linewidth=0.5)
        body_lo = min(opens[i], closes[i]); body_hi = max(opens[i], closes[i])
        rect = Rectangle((i-0.3, body_lo), 0.6, max(body_hi - body_lo, 1),
                         facecolor=color, edgecolor='black', linewidth=0.5)
        ax.add_patch(rect)

    # Draw all lines
    for line in engine.lines:
        color = LINE_COLORS.get(line.line_type, 'gray')
        start = line.anchor_bar
        end = line.retired_at_bar if line.status == "RETIRED" and line.retired_at_bar > 0 else n - 1
        xs = list(range(start, end + 1))
        ys = [line.value_at(x) for x in xs]

        if line.status == "RETIRED":
            ax.plot(xs, ys, color=color, linewidth=1, linestyle='--', alpha=0.35)
        elif line.status == "FROZEN":
            lw = 2.5 if line.authority_rank <= 2 else 1.5
            ax.plot(xs, ys, color=color, linewidth=lw, linestyle='-', alpha=0.9)
            # Label
            label_x = min(start + 3, end)
            label_y = line.value_at(label_x)
            ax.annotate(f"{line.line_type}\nT:{line.touch_count} A:{line.authority_rank}",
                       xy=(label_x, label_y), fontsize=7, color=color, alpha=0.8)
        elif line.status == "PROVISIONAL":
            # Show as dotted from anchor
            ax.scatter([start], [line.anchor_price], color=color, s=60, marker='o', zorder=5)
            ax.annotate(f"PROV", xy=(start, line.anchor_price), fontsize=7, color=color)

    # Violation markers
    for v in violations:
        ax.scatter([v['bar']], [v.get('high', v.get('low', 0))],
                  color='red', s=100, marker='x', zorder=10, linewidths=2)

    # X-axis
    ticks = list(range(0, n, max(1, n // 15)))
    labels = [data.iloc[i]['time'].strftime('%H:%M') if i < n else '' for i in ticks]
    ax.set_xticks(ticks); ax.set_xticklabels(labels, rotation=45, fontsize=8)
    ax.set_ylabel('Price'); ax.set_xlabel('Time')
    ax.grid(True, alpha=0.2)
    ax.set_xlim(-1, n + 1)

    plt.tight_layout()
    plt.show()
    return engine


if __name__ == "__main__":
    dates = sys.argv[1:] if len(sys.argv) > 1 else ['2026-02-11', '2025-04-21', '2025-04-23']
    for d in dates:
        run_and_visualize(d, show_chart=True)
