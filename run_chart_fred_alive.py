"""
Interactive chart for FRED Is Alive trades.
Shows frozen ray structure + conviction-based entries/exits.

Usage:
    python run_chart_fred_alive.py 2025-04-07
    python run_chart_fred_alive.py 2026-03-31 09:30 17:00
"""
import sys, os
import pandas as pd, pytz, numpy as np
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.widgets import Button
from matplotlib.patches import Rectangle

from execution_engine import ExecutionEngine
from evidence_engine import EvidenceEngine
from conviction_engine import ConvictionEngine
from frozen_ray_engine import FrozenRayEngine

_EST = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")

LINE_COLORS = {
    'ORANGE': 'orange', 'YELLOW': '#DAA520',
    'PURPLE_ORIGINAL': '#8B008B', 'BLUE_ORIGINAL': '#1E90FF',
    'PURPLE_PROFIT': 'magenta', 'BLUE_PROFIT': '#00CED1',
}


class FredAliveChart:
    """Interactive bar-by-bar chart showing FRED Is Alive trades + frozen ray structure."""

    def __init__(self, day_data, target_date, trades, line_snapshots, belief_history, conviction_history):
        self.data = day_data
        self.target_date = target_date
        self.trades = trades
        self.line_snapshots = line_snapshots
        self.belief_history = belief_history
        self.conviction_history = conviction_history

        self.n = len(day_data)
        self.highs = day_data['High'].values
        self.lows = day_data['Low'].values
        self.closes = day_data['Close'].values
        self.opens = day_data['Open'].values
        self.times = day_data.index

        self.current_frame = 0
        self.is_playing = False
        self.timer = None

    def create_figure(self):
        self.fig = plt.figure(figsize=(17, 10))
        self.fig.subplots_adjust(left=0.06, right=0.82, top=0.93, bottom=0.13)

        self.ax = self.fig.add_axes([0.06, 0.25, 0.76, 0.66])
        self.ax_pl = self.fig.add_axes([0.06, 0.13, 0.76, 0.10], sharex=self.ax)

        session_pl = sum(t['pl'] for t in self.trades)
        self.fig.suptitle(
            f"FRED Is Alive — {self.target_date}  (09:30–17:00 ET)  |  "
            f"Session P/L: {session_pl:+.0f} pts  |  {len(self.trades)} trades",
            fontsize=12, fontweight="bold")

        self.ax.set_ylabel("Price", fontsize=10)
        self.ax.grid(True, alpha=0.2, linestyle="--")
        self.ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=_EST))
        plt.setp(self.ax.xaxis.get_majorticklabels(), rotation=45, ha="right", fontsize=8)

        self.ax_pl.set_ylabel("P/L", fontsize=9)
        self.ax_pl.axhline(0, color='gray', linewidth=0.5, linestyle='--')
        self.ax_pl.axhline(-300, color='red', linewidth=0.8, linestyle='--', alpha=0.5)
        self.ax_pl.grid(True, alpha=0.15)

        # Stats box
        self.stats_box = self.ax.text(
            1.01, 0.99, "", transform=self.ax.transAxes, fontsize=9,
            verticalalignment="top", horizontalalignment="left",
            bbox=dict(boxstyle="round", facecolor="lightyellow", alpha=0.9),
            fontfamily="monospace")

        # Navigation buttons
        ax_start = plt.axes([0.10, 0.02, 0.09, 0.04])
        ax_back = plt.axes([0.21, 0.02, 0.09, 0.04])
        ax_fwd = plt.axes([0.32, 0.02, 0.09, 0.04])
        ax_end = plt.axes([0.43, 0.02, 0.09, 0.04])
        ax_play = plt.axes([0.54, 0.02, 0.09, 0.04])

        self.btn_start = Button(ax_start, "<< Start")
        self.btn_back = Button(ax_back, "< Back")
        self.btn_fwd = Button(ax_fwd, "Forward >")
        self.btn_end = Button(ax_end, "End >>")
        self.btn_play = Button(ax_play, "Play")

        self.btn_start.on_clicked(self.on_start)
        self.btn_back.on_clicked(self.on_back)
        self.btn_fwd.on_clicked(self.on_forward)
        self.btn_end.on_clicked(self.on_end)
        self.btn_play.on_clicked(self.on_play)

        self.fig.canvas.mpl_connect('scroll_event', self._on_scroll)
        self.fig.canvas.mpl_connect('key_press_event', self._on_key)

    def update_plot(self, frame):
        self.current_frame = frame
        self.ax.clear()
        self.ax_pl.clear()

        # Determine view window
        view_start = max(0, frame - 90)
        view_end = frame

        # Draw candlesticks
        for i in range(view_start, view_end + 1):
            t = self.times[i]
            color = 'green' if self.closes[i] >= self.opens[i] else 'red'
            self.ax.plot([t, t], [self.lows[i], self.highs[i]], color='black', linewidth=0.5)
            body_lo = min(self.opens[i], self.closes[i])
            body_hi = max(self.opens[i], self.closes[i])
            width = pd.Timedelta(seconds=40)
            rect = Rectangle((t - width/2, body_lo), width, max(body_hi - body_lo, 0.5),
                             facecolor=color, edgecolor='black', linewidth=0.4)
            self.ax.add_patch(rect)

        # Draw frozen ray lines
        snap = self.line_snapshots[frame]
        price_min = min(self.lows[view_start:view_end+1]) - 30
        price_max = max(self.highs[view_start:view_end+1]) + 30

        for (ltype, auth, anchor_p, anchor_b, slope, status, touches, direction) in snap:
            if anchor_b > frame:
                continue
            color = LINE_COLORS.get(ltype, 'gray')
            start_b = max(anchor_b, view_start)
            xs = [self.times[b] for b in range(start_b, view_end + 1)]
            ys = [anchor_p + slope * (b - anchor_b) for b in range(start_b, view_end + 1)]

            # Clip to visible range
            ys_clip = [y if price_min - 50 <= y <= price_max + 50 else np.nan for y in ys]

            if status == "RETIRED":
                self.ax.plot(xs, ys_clip, color=color, linewidth=0.7, linestyle='--', alpha=0.2)
            elif status == "FROZEN":
                lw = 2.2 if auth <= 2 else 1.3
                self.ax.plot(xs, ys_clip, color=color, linewidth=lw, alpha=0.85)
                # Touch count at end
                if touches > 0 and not np.isnan(ys_clip[-1]):
                    self.ax.annotate(f'{touches}', xy=(xs[-1], ys_clip[-1]),
                                    fontsize=7, color=color, fontweight='bold')

        # Draw trades
        for t in self.trades:
            entry_bar = t['entry_bar']
            exit_bar = t['exit_bar']

            # Entry marker
            if view_start <= entry_bar <= frame:
                entry_time = self.times[entry_bar]
                if t['direction'] == 'LONG':
                    self.ax.scatter([entry_time], [t['entry_price']], color='blue', s=180,
                                   marker='^', zorder=10, edgecolors='black', linewidths=1.2)
                    self.ax.annotate(f"BUY\n{t['entry_price']:.0f}",
                                   xy=(entry_time, t['entry_price']),
                                   xytext=(entry_time, t['entry_price'] - 25),
                                   fontsize=8, color='blue', ha='center', fontweight='bold')
                else:
                    self.ax.scatter([entry_time], [t['entry_price']], color='darkred', s=180,
                                   marker='v', zorder=10, edgecolors='black', linewidths=1.2)
                    self.ax.annotate(f"SELL\n{t['entry_price']:.0f}",
                                   xy=(entry_time, t['entry_price']),
                                   xytext=(entry_time, t['entry_price'] + 25),
                                   fontsize=8, color='darkred', ha='center', fontweight='bold')

            # Exit marker
            if view_start <= exit_bar <= frame:
                exit_time = self.times[exit_bar]
                exit_color = 'green' if t['pl'] > 0 else 'red'
                self.ax.scatter([exit_time], [t['exit_price']], color=exit_color, s=150,
                               marker='X', zorder=10, edgecolors='black', linewidths=1)
                self.ax.annotate(f"{t['exit_reason']}\n{t['pl']:+.0f}",
                               xy=(exit_time, t['exit_price']),
                               xytext=(exit_time + pd.Timedelta(minutes=2), t['exit_price']),
                               fontsize=7, color=exit_color, fontweight='bold',
                               bbox=dict(boxstyle='round,pad=0.2', facecolor='white', alpha=0.8))

            # Dashed position line
            if entry_bar <= frame:
                end_b = min(exit_bar, frame)
                line_color = 'green' if t['pl'] > 0 else 'red'
                if exit_bar > frame:
                    line_color = 'gray'
                self.ax.plot([self.times[entry_bar], self.times[end_b]],
                            [t['entry_price'], self.closes[end_b] if exit_bar > frame else t['exit_price']],
                            color=line_color, linewidth=1.5, linestyle='--', alpha=0.5)

        # Session P/L curve
        pls = []
        realized = 0.0
        pos = 0
        entry_p = 0.0
        for i in range(view_start, view_end + 1):
            for t in self.trades:
                if t['entry_bar'] == i:
                    pos = 1 if t['direction'] == 'LONG' else -1
                    entry_p = t['entry_price']
                if t['exit_bar'] == i and pos != 0:
                    realized += t['pl']
                    pos = 0
            if pos != 0:
                unr = (self.closes[i] - entry_p) * pos * 2
                pls.append(realized + unr)
            else:
                pls.append(realized)

        pl_times = [self.times[i] for i in range(view_start, view_end + 1)]
        self.ax_pl.fill_between(pl_times, pls, 0,
                                where=[p >= 0 for p in pls], color='green', alpha=0.2)
        self.ax_pl.fill_between(pl_times, pls, 0,
                                where=[p < 0 for p in pls], color='red', alpha=0.2)
        self.ax_pl.plot(pl_times, pls, color='black', linewidth=1.2)
        self.ax_pl.axhline(0, color='gray', linewidth=0.5, linestyle='--')
        self.ax_pl.axhline(-300, color='red', linewidth=0.8, linestyle='--', alpha=0.4)
        self.ax_pl.set_ylabel("P/L", fontsize=9)
        self.ax_pl.grid(True, alpha=0.15)

        # Axis limits
        self.ax.set_xlim(self.times[view_start] - pd.Timedelta(minutes=1),
                         self.times[view_end] + pd.Timedelta(minutes=3))
        self.ax.set_ylim(price_min, price_max)
        self.ax.set_ylabel("Price", fontsize=10)
        self.ax.grid(True, alpha=0.2, linestyle="--")
        self.ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=_EST))

        # Stats box
        # Find current conviction state
        conv_state = "OBSERVING"
        belief = 0.0
        for bar, state, score in self.conviction_history:
            if bar <= frame:
                conv_state = state
                belief = score
            else:
                break

        current_pl = pls[-1] if pls else 0
        stats = (f"Bar: {frame} ({self.times[frame].strftime('%H:%M')})\n"
                 f"Close: {self.closes[frame]:.0f}\n"
                 f"─────────────────\n"
                 f"Conviction: {conv_state}\n"
                 f"Belief: {belief:+.1f}\n"
                 f"─────────────────\n"
                 f"Session P/L: {current_pl:+.0f}\n"
                 f"Trades: {sum(1 for t in self.trades if t['entry_bar'] <= frame)}\n"
                 f"─────────────────\n"
                 f"Day Range: {max(self.highs[:frame+1]) - min(self.lows[:frame+1]):.0f}")

        self.stats_box = self.ax.text(
            1.01, 0.99, stats, transform=self.ax.transAxes, fontsize=9,
            verticalalignment="top", horizontalalignment="left",
            bbox=dict(boxstyle="round", facecolor="lightyellow", alpha=0.9),
            fontfamily="monospace")

        self.fig.canvas.draw_idle()

    def on_start(self, event):
        self.current_frame = 0
        self.update_plot(0)

    def on_back(self, event):
        self.current_frame = max(0, self.current_frame - 1)
        self.update_plot(self.current_frame)

    def on_forward(self, event):
        self.current_frame = min(self.n - 1, self.current_frame + 1)
        self.update_plot(self.current_frame)

    def on_end(self, event):
        self.current_frame = self.n - 1
        self.update_plot(self.current_frame)

    def on_play(self, event):
        if self.is_playing:
            self.is_playing = False
            if self.timer:
                self.timer.stop()
        else:
            self.is_playing = True
            self.timer = self.fig.canvas.new_timer(interval=100)
            self.timer.add_callback(self._play_step)
            self.timer.start()

    def _play_step(self):
        if self.current_frame < self.n - 1 and self.is_playing:
            self.current_frame += 1
            self.update_plot(self.current_frame)
        else:
            self.is_playing = False
            if self.timer:
                self.timer.stop()

    def _on_scroll(self, event):
        if event.button == 'up':
            self.current_frame = min(self.n - 1, self.current_frame + 5)
        elif event.button == 'down':
            self.current_frame = max(0, self.current_frame - 5)
        self.update_plot(self.current_frame)

    def _on_key(self, event):
        if event.key == 'right':
            self.on_forward(None)
        elif event.key == 'left':
            self.on_back(None)
        elif event.key == 'up':
            self.current_frame = min(self.n - 1, self.current_frame + 10)
            self.update_plot(self.current_frame)
        elif event.key == 'down':
            self.current_frame = max(0, self.current_frame - 10)
            self.update_plot(self.current_frame)
        elif event.key == 'home':
            self.on_start(None)
        elif event.key == 'end':
            self.on_end(None)

    def show(self):
        self.create_figure()
        self.update_plot(self.n - 1)
        plt.show(block=True)


def run_fred_alive_chart(target_date, start_time="09:30", end_time="17:00"):
    """Load data, run FRED Is Alive, and show interactive chart."""
    fname = os.path.join(_DATA_ROOT, f"CBOT_MINI_YM1_{target_date}.csv")
    if not os.path.exists(fname):
        print(f"File not found: {fname}")
        return

    df = pd.read_csv(fname, index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
    ds = pd.Timestamp(f"{target_date} {start_time}", tz=_EST)
    de = pd.Timestamp(f"{target_date} {end_time}", tz=_EST)
    day_data = df[(df.index >= ds) & (df.index <= de)]

    if len(day_data) < 15:
        print(f"Not enough data for {target_date}")
        return

    print(f"Running FRED Is Alive for {target_date} ({len(day_data)} bars)...")

    # Run execution engine
    engine = ExecutionEngine()
    result = engine.run_session(day_data)
    trades = result['trades']

    # Run structure engine for line snapshots
    struct = FrozenRayEngine(swing_threshold=10.0)
    line_snapshots = []
    n = len(day_data)
    opens = day_data['Open'].values
    highs = day_data['High'].values
    lows = day_data['Low'].values
    closes = day_data['Close'].values

    for i in range(n):
        struct.process_bar(float(opens[i]), float(highs[i]), float(lows[i]), float(closes[i]))
        snap = [(l.line_type, l.authority_rank, l.anchor_price, l.anchor_bar,
                 l.slope, l.status, l.touch_count, l.direction)
                for l in struct.lines]
        line_snapshots.append(snap)

    # Run evidence + conviction for state display
    evidence = EvidenceEngine()
    evidence.run_session(day_data)
    conviction = ConvictionEngine(persistence_bars=3)
    for bar, score, _ in evidence.belief_history:
        conviction.process_bar(bar, score)

    print(f"Session P/L: {result['session_pl']:+.0f} pts ({len(trades)} trades)")
    for i, t in enumerate(trades):
        entry_t = day_data.index[t['entry_bar']].strftime('%H:%M')
        exit_t = day_data.index[t['exit_bar']].strftime('%H:%M')
        print(f"  Trade {i+1}: {t['direction']:<6} {entry_t}->{exit_t} "
              f"P/L={t['pl']:+.0f} held={t['bars_held']}bars reason={t['exit_reason']}")

    # Show chart
    chart = FredAliveChart(day_data, target_date, trades, line_snapshots,
                           evidence.belief_history, conviction.state_history)
    chart.show()


if __name__ == "__main__":
    target_date = sys.argv[1] if len(sys.argv) > 1 else "2026-03-31"
    start_t = sys.argv[2] if len(sys.argv) > 2 else "09:30"
    end_t = sys.argv[3] if len(sys.argv) > 3 else "17:00"
    run_fred_alive_chart(target_date, start_t, end_t)
