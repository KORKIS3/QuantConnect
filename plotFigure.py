"""
YM Futures Trading Analysis - Plotting Module

Pure visualization layer.  All calculations (ray slopes, trendline fits,
signal detection, P/L arithmetic) are performed by TradingAlgo.run_trading_algo
and stored in the enriched per-minute DataFrame before this module is called.

ChartPlotter reads those pre-computed columns and draws.  No business logic,
no slope math, and no incremental signal detection live here.
"""

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.widgets import Button
import numpy as np
import pandas as pd
import os

# Columns that must be present for pure rendering.
# If any are absent when ChartPlotter is constructed, TradingAlgo is run
# automatically to enrich the DataFrame before proceeding.
_REQUIRED_COLS = [
    "orange_ray", "yellow_ray", "purple_ray", "blue_ray",
    "orange_ray_start_price", "orange_ray_start_time",
    "yellow_ray_start_price", "yellow_ray_start_time",
    "purple_ray_start_price", "purple_ray_start_time",
    "blue_ray_start_price",   "blue_ray_start_time",
    "orange_angle", "yellow_angle", "purple_angle", "blue_angle",
    "orange_ray_end_price", "yellow_ray_end_price",
    "purple_ray_end_price", "blue_ray_end_price",
    "signal", "buy_price", "sell_price", "position", "pl",
    "y_min", "y_max", "session_open",
    "rolling_price_change", "rolling_max_high", "rolling_min_low", "rolling_range",
    "rolling_max_high_time", "rolling_min_low_time",
    "rolling_buy_count", "rolling_sell_count",
]


class _StateCompat:
    """Backward-compatibility shim for callers that read ChartPlotter.state.*.

    Code written against the old mutable TradingState API (e.g. RunFullDataSet,
    run_signal_debug_*) continues to work without modification.  All values are
    derived from the pre-computed DataFrame rather than maintained as live state.
    """

    def __init__(self, data):
        self._data = data

    @property
    def detected_buy_signals(self):
        if "signal" not in self._data.columns:
            return {}
        return {
            ts: float(row["buy_price"])
            for ts, row in self._data.iterrows()
            if row.get("signal") == "BUY" and pd.notna(row.get("buy_price"))
        }

    @property
    def detected_sell_signals(self):
        if "signal" not in self._data.columns:
            return {}
        return {
            ts: float(row["sell_price"])
            for ts, row in self._data.iterrows()
            if row.get("signal") == "SELL" and pd.notna(row.get("sell_price"))
        }

    @property
    def detected_liquidation_signals(self):
        if "is_liquidation" not in self._data.columns:
            return set()
        return set(self._data.index[self._data["is_liquidation"].astype(bool)])

    @property
    def trading_halted(self):
        # In the new design all frames are rendered; halting is implicit in the data.
        return False

    @property
    def halt_time(self):
        return None

    @property
    def halt_reason(self):
        return None

    @property
    def all_signals_detected(self):
        return "signal" in self._data.columns

    @property
    def position(self):
        if "position" in self._data.columns and len(self._data) > 0:
            return str(self._data["position"].iloc[-1])
        return "flat"

    @property
    def entry_price(self):
        return None

    @property
    def entry_time(self):
        return None


class ChartPlotter:
    """Renders the interactive YM chart from a pre-computed DataFrame.

    All signal detection, ray calculations, and P/L arithmetic are performed
    by TradingAlgo.run_trading_algo before this class is created.
    ChartPlotter only reads DataFrame columns and draws — no calculations.
    """

    def __init__(self, data, target_date, start_time, end_time, output_dir, batch_mode=False):
        # Ensure the DataFrame has all required pre-computed columns.
        # Auto-run TradingAlgo if any are missing (e.g. raw OHLC input).
        missing = [c for c in _REQUIRED_COLS if c not in data.columns]
        if missing:
            from TradingAlgo import run_trading_algo
            print("plotFigure: running TradingAlgo to compute missing columns ...")
            data = run_trading_algo(data, target_date, start_time, end_time)

        self.data = data
        self.target_date = target_date
        self.start_time = start_time
        self.end_time = end_time
        self.output_dir = output_dir
        self.batch_mode = batch_mode

        # Backward-compatibility shim for code that reads plotter.state.*
        self.state = _StateCompat(self.data)

        self.current_frame = 0
        self.is_playing = False
        self.timer = None
        self.snapshots_taken = set()

        self.fig = None
        self.ax = None
        self.ax_top = None
        self.lines = {}
        self.annotations = []
        self.signal_markers = {"buy": [], "sell": [], "halt": []}
        self.signal_annotations = {"buy": [], "sell": [], "halt": []}

        # Per-ray angle annotation handles (replaced each frame).
        self.orange_angle_annotation = None
        self.yellow_angle_annotation = None
        self.purple_angle_annotation = None
        self.blue_angle_annotation = None

        self.stats_box = None
        self.current_time_text = None
        self.rays_debug_box = None

    # ------------------------------------------------------------------
    # Backward-compatibility no-op
    # ------------------------------------------------------------------

    def detect_all_signals_once(self):
        """No-op: signals are pre-computed by TradingAlgo.run_trading_algo."""
        pass

    # ------------------------------------------------------------------
    # Figure setup
    # ------------------------------------------------------------------

    def create_figure(self):
        """Create the matplotlib figure and axes."""
        self.fig = plt.figure(figsize=(16, 9))
        self.ax = plt.subplot2grid((10, 1), (0, 0), rowspan=9)
        self.fig.subplots_adjust(right=0.85)
        self.fig.suptitle(
            f"YM Futures - {self.target_date} ({self.start_time} - {self.end_time} EST) - INTERACTIVE",
            fontsize=16, fontweight="bold")

        self.lines["high"],  = self.ax.plot([], [], label="High",  color="green",     linewidth=2,   marker="o", markersize=5)
        self.lines["low"],   = self.ax.plot([], [], label="Low",   color="red",       linewidth=2,   marker="o", markersize=5)
        self.lines["close"], = self.ax.plot([], [], label="Close", color="black",     linewidth=2.5, marker="s", markersize=5)

        self.lines["ray_orange"],      = self.ax.plot([], [], "orange",           linewidth=2.5, label="Max Ray (-2.5 deg)", alpha=0.9)
        self.lines["ray_yellow"],      = self.ax.plot([], [], "yellow",           linewidth=2.5, label="Min Ray (+2.5 deg)", alpha=0.9)
        self.lines["ray_purple"],      = self.ax.plot([], [], color="darkviolet", linewidth=2.5, label="Max Ray (-45 deg)",  alpha=0.9)
        self.lines["ray_blue"],        = self.ax.plot([], [], color="blue",       linewidth=2.5, label="Min Ray (+45 deg)",  alpha=0.9)
        self.lines["ray_dark_purple"], = self.ax.plot([], [], color="indigo",     linewidth=2.5, label="Dark Purple Ray (-65 deg)", alpha=0.9)

        self.ax.set_ylabel("Price", fontsize=13, fontweight="bold")
        self.ax.set_xlabel("Time (EST)", fontsize=13, fontweight="bold")
        self.ax.set_title("Price Movement by Minute", fontsize=14, fontweight="bold", pad=35)
        self.ax.legend(loc="center left", bbox_to_anchor=(1, 0.5), fontsize=11)
        self.ax.grid(True, alpha=0.3, linestyle="--")
        self.ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
        plt.setp(self.ax.xaxis.get_majorticklabels(), rotation=45, ha="right")

        y_min = float(self.data["y_min"].iloc[0])
        y_max = float(self.data["y_max"].iloc[0])
        self.ax.set_ylim(y_min, y_max)
        self.ax.set_xlim(self.data.index[0], self.data.index[-1])

        self.stats_box = self.ax.text(
            1.02, 0.98, "", transform=self.ax.transAxes, fontsize=10,
            verticalalignment="top", horizontalalignment="left",
            bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.8))

        self.current_time_text = self.ax.text(
            0.5, 0.02, "", transform=self.ax.transAxes, fontsize=11,
            ha="center", bbox=dict(boxstyle="round", facecolor="lightblue", alpha=0.8))

        self.ax_top = self.ax.twiny()
        self.ax_top.set_xlim(self.ax.get_xlim())
        self.ax_top.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
        self.ax_top.set_xlabel("P/L by Minute (after trade)", fontsize=11, fontweight="bold")

    # ------------------------------------------------------------------
    # Main render entry-point
    # ------------------------------------------------------------------

    def update_plot(self, frame):
        """Render the chart at the given frame index (reads pre-computed data only)."""
        frame = max(0, min(frame, len(self.data) - 1))
        current_data = self.data.iloc[:frame + 1]
        if len(current_data) == 0:
            return

        self.update_price_lines(current_data)
        self.update_ray_lines(current_data)
        self.update_annotations(current_data)
        self.update_signal_markers(current_data)
        self.update_stats(current_data)
        self.update_pl_axis(current_data)
        self.save_snapshot(current_data)

    # ------------------------------------------------------------------
    # Render helpers — read from DataFrame columns, no calculations
    # ------------------------------------------------------------------

    def update_price_lines(self, current_data):
        """Update the OHLC price lines."""
        times = current_data.index
        self.lines["high"].set_data(times, current_data["High"])
        self.lines["low"].set_data(times,  current_data["Low"])
        self.lines["close"].set_data(times, current_data["Close"])

    def _draw_ray(self, line_key, ann_attr,
                  start_time, start_price, end_price,
                  current_time, current_price, angle,
                  color, edge_color, y_offset):
        """Draw one ray line and its angle label from pre-computed values."""
        end_time = self.data.index[-1]
        self.lines[line_key].set_data([start_time, end_time], [start_price, end_price])

        old_ann = getattr(self, ann_attr, None)
        if old_ann is not None:
            old_ann.remove()

        va = "top" if y_offset < 0 else "bottom"
        ann = self.ax.annotate(
            f"angle {abs(angle):.2f} deg",
            xy=(current_time, current_price),
            xytext=(10, y_offset), textcoords="offset points",
            ha="left", va=va, fontsize=9, color=color, fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.4", facecolor="white",
                      alpha=0.85, edgecolor=edge_color, linewidth=2))
        setattr(self, ann_attr, ann)

    def update_ray_lines(self, current_data):
        """Draw all four ray lines from pre-computed DataFrame columns."""
        row = current_data.iloc[-1]
        current_time = current_data.index[-1]

        self._draw_ray(
            "ray_orange", "orange_angle_annotation",
            row["orange_ray_start_time"], float(row["orange_ray_start_price"]),
            float(row["orange_ray_end_price"]),
            current_time, float(row["orange_ray"]), float(row["orange_angle"]),
            "darkorange", "orange", -15)

        self._draw_ray(
            "ray_yellow", "yellow_angle_annotation",
            row["yellow_ray_start_time"], float(row["yellow_ray_start_price"]),
            float(row["yellow_ray_end_price"]),
            current_time, float(row["yellow_ray"]), float(row["yellow_angle"]),
            "gold", "yellow", -15)

        self._draw_ray(
            "ray_purple", "purple_angle_annotation",
            row["purple_ray_start_time"], float(row["purple_ray_start_price"]),
            float(row["purple_ray_end_price"]),
            current_time, float(row["purple_ray"]), float(row["purple_angle"]),
            "darkviolet", "darkviolet", 15)

        self._draw_ray(
            "ray_blue", "blue_angle_annotation",
            row["blue_ray_start_time"], float(row["blue_ray_start_price"]),
            float(row["blue_ray_end_price"]),
            current_time, float(row["blue_ray"]), float(row["blue_angle"]),
            "blue", "blue", -15)

        # Dark purple ray not yet implemented in TradingAlgo.
        self.lines["ray_dark_purple"].set_data([], [])

        # Debug overlay: show current and previous bar ray values from the DataFrame.
        if hasattr(self, "rays_debug_box") and self.rays_debug_box is not None:
            self.rays_debug_box.remove()
            self.rays_debug_box = None

        if len(current_data) >= 2:
            prev_row  = current_data.iloc[-2]
            prev_time = current_data.index[-2]
            debug_text = (
                "Prev (" + prev_time.strftime("%H:%M:%S") + "):\n"
                "  Purple: " + f"{float(prev_row['purple_ray']):.2f}" + "\n"
                "  Blue:   " + f"{float(prev_row['blue_ray']):.2f}" + "\n"
                "  Orange: " + f"{float(prev_row['orange_ray']):.2f}" + "\n"
                "  Yellow: " + f"{float(prev_row['yellow_ray']):.2f}" + "\n"
                "Curr (" + current_time.strftime("%H:%M:%S") + "):\n"
                "  Purple: " + f"{float(row['purple_ray']):.2f}" + "\n"
                "  Blue:   " + f"{float(row['blue_ray']):.2f}" + "\n"
                "  Orange: " + f"{float(row['orange_ray']):.2f}" + "\n"
                "  Yellow: " + f"{float(row['yellow_ray']):.2f}"
            )
            self.rays_debug_box = self.fig.text(
                0.87, 0.15, debug_text,
                ha="left", va="bottom", fontsize=9, color="navy", fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.5", facecolor="white", alpha=0.85,
                          edgecolor="navy", linewidth=2),
                zorder=1000)

    def update_annotations(self, current_data):
        """Draw per-bar High / Low / Close price labels."""
        for ann in self.annotations:
            ann.remove()
        self.annotations.clear()

        for time, row in current_data.iterrows():
            time_str = time.strftime("%H:%M")

            ann = self.ax.annotate(
                str(int(row["High"])) + "\n" + time_str, xy=(time, row["High"]),
                xytext=(0, 8), textcoords="offset points", ha="center", va="bottom",
                fontsize=6, color="darkgreen", fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.3", facecolor="lightgreen", alpha=0.6, edgecolor="green"))
            self.annotations.append(ann)

            ann = self.ax.annotate(
                str(int(row["Low"])) + "\n" + time_str, xy=(time, row["Low"]),
                xytext=(0, -8), textcoords="offset points", ha="center", va="top",
                fontsize=6, color="darkred", fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.3", facecolor="lightcoral", alpha=0.6, edgecolor="red"))
            self.annotations.append(ann)

            ann = self.ax.annotate(
                str(int(row["Close"])) + "\n" + time_str, xy=(time, row["Close"]),
                xytext=(5, 0), textcoords="offset points", ha="left", va="center",
                fontsize=6, color="black", fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.3", facecolor="lightgray", alpha=0.6, edgecolor="black"))
            self.annotations.append(ann)

    def update_signal_markers(self, current_data):
        """Draw buy / sell markers from pre-computed signal columns."""
        for marker in self.signal_markers["buy"] + self.signal_markers["sell"] + self.signal_markers["halt"]:
            marker.remove()
        for ann in self.signal_annotations["buy"] + self.signal_annotations["sell"] + self.signal_annotations["halt"]:
            ann.remove()

        self.signal_markers     = {"buy": [], "sell": [], "halt": []}
        self.signal_annotations = {"buy": [], "sell": [], "halt": []}

        if "signal" not in current_data.columns:
            return

        for ts, row in current_data.iterrows():
            sig    = row.get("signal", "")
            is_liq = bool(row.get("is_liquidation", False))

            if sig == "BUY":
                price = row.get("buy_price")
                if pd.isna(price):
                    continue
                price = float(price)
                label = ("LIQ" if is_liq else "BUY") + "\n" + str(int(price)) + "\n" + ts.strftime("%H:%M")
                marker, = self.ax.plot(ts, price, marker="^", markersize=15,
                                       color="green", markeredgecolor="darkgreen",
                                       markeredgewidth=2, zorder=10)
                self.signal_markers["buy"].append(marker)
                ann = self.ax.annotate(
                    label, xy=(ts, price), xytext=(0, 30), textcoords="offset points",
                    ha="center", va="bottom", fontsize=8, color="white", fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.5", facecolor="green", alpha=0.9,
                              edgecolor="darkgreen", linewidth=2),
                    arrowprops=dict(arrowstyle="->", color="green", lw=2))
                self.signal_annotations["buy"].append(ann)

            elif sig == "SELL":
                price = row.get("sell_price")
                if pd.isna(price):
                    continue
                price = float(price)
                label = ("LIQ" if is_liq else "SELL") + "\n" + str(int(price)) + "\n" + ts.strftime("%H:%M")
                marker, = self.ax.plot(ts, price, marker="v", markersize=15,
                                       color="red", markeredgecolor="darkred",
                                       markeredgewidth=2, zorder=10)
                self.signal_markers["sell"].append(marker)
                ann = self.ax.annotate(
                    label, xy=(ts, price), xytext=(0, -30), textcoords="offset points",
                    ha="center", va="top", fontsize=8, color="white", fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.5", facecolor="red", alpha=0.9,
                              edgecolor="darkred", linewidth=2),
                    arrowprops=dict(arrowstyle="->", color="red", lw=2))
                self.signal_annotations["sell"].append(ann)

    def update_stats(self, current_data):
        """Update the statistics overlay box."""
        times = current_data.index
        row   = current_data.iloc[-1]

        session_open  = float(row["session_open"])
        current_close = float(row["Close"])
        price_change  = float(row["rolling_price_change"])
        max_high      = float(row["rolling_max_high"])
        min_low       = float(row["rolling_min_low"])
        price_range   = float(row["rolling_range"])
        max_time      = row["rolling_max_high_time"].strftime("%H:%M")
        min_time      = row["rolling_min_low_time"].strftime("%H:%M")
        n_buy         = int(row["rolling_buy_count"])
        n_sell        = int(row["rolling_sell_count"])

        stats_text  = "Minute: " + str(len(current_data)) + "/" + str(len(self.data)) + "\n"
        stats_text += "Current Time: " + times[-1].strftime("%H:%M") + "\n"
        stats_text += "--------------------\n"
        stats_text += "Opening: " + f"{session_open:,.0f}" + "\n"
        stats_text += "Current: " + f"{current_close:,.0f}" + "\n"
        stats_text += "Change: " + f"{price_change:+.0f}" + " points\n"
        stats_text += "--------------------\n"
        stats_text += "MAX: " + f"{max_high:,.0f}" + " @ " + max_time + "\n"
        stats_text += "MIN: " + f"{min_low:,.0f}" + " @ " + min_time + "\n"
        stats_text += "Range: " + f"{price_range:.0f}" + " points\n"
        stats_text += "--------------------\n"
        stats_text += "Signals: " + str(n_buy) + " BUY, " + str(n_sell) + " SELL"

        self.stats_box.set_text(stats_text)
        self.current_time_text.set_text("Viewing: " + times[-1].strftime("%H:%M:%S"))

    def update_pl_axis(self, current_data):
        """Render cumulative P/L labels from the pre-computed pl column."""
        self.ax_top.clear()
        self.ax_top.set_xlim(self.ax.get_xlim())
        self.ax_top.set_ylim(self.ax.get_ylim())
        self.ax_top.set_xlabel("Cumulative P/L by Minute", fontsize=11, fontweight="bold")
        self.ax_top.xaxis.set_label_position("top")
        self.ax_top.tick_params(axis="x", which="both", top=True, bottom=False,
                                labeltop=True, labelbottom=False)

        if "pl" not in current_data.columns:
            return

        y_pos = self.ax.get_ylim()[1] - 5
        for ts, row in current_data.iterrows():
            pl = float(row["pl"])
            if pl == 0:
                continue
            color = "green" if pl >= 0 else "red"
            sign  = "+" if pl >= 0 else ""
            self.ax_top.text(ts, y_pos, sign + f"{pl:.0f}",
                             ha="center", va="top", fontsize=7,
                             color=color, fontweight="bold",
                             bbox=dict(boxstyle="round,pad=0.3",
                                       facecolor="white", alpha=0.7,
                                       edgecolor=color, linewidth=1.5))

    def save_snapshot(self, current_data):
        """Save chart snapshots at key times."""
        if self.batch_mode:
            return
        snapshot_times = ["09:31", "09:38", "09:45", "09:55", "10:00"]
        current_time_hhmm = current_data.index[-1].strftime("%H:%M")
        if current_time_hhmm in snapshot_times and current_time_hhmm not in self.snapshots_taken:
            timestamp_filename = current_data.index[-1].strftime("%Y%m%d_%H%M")
            snapshot_filename = self.output_dir + "/YM_" + self.target_date + "_" + timestamp_filename + ".png"
            self.fig.savefig(snapshot_filename, dpi=300, bbox_inches="tight")
            self.snapshots_taken.add(current_time_hhmm)
            print("  Snapshot: " + snapshot_filename)

    # ------------------------------------------------------------------
    # Navigation buttons
    # ------------------------------------------------------------------

    def create_navigation_buttons(self):
        """Create interactive navigation buttons."""
        ax_start   = plt.axes([0.10, 0.02, 0.10, 0.04])
        ax_back    = plt.axes([0.22, 0.02, 0.10, 0.04])
        ax_forward = plt.axes([0.34, 0.02, 0.10, 0.04])
        ax_end     = plt.axes([0.46, 0.02, 0.10, 0.04])
        ax_play    = plt.axes([0.58, 0.02, 0.10, 0.04])

        self.btn_start   = Button(ax_start,   "<< Start")
        self.btn_back    = Button(ax_back,    "< Back")
        self.btn_forward = Button(ax_forward, "Forward >")
        self.btn_end     = Button(ax_end,     "End >>")
        self.btn_play    = Button(ax_play,    "Play")

        self.btn_start.on_clicked(self.on_start)
        self.btn_back.on_clicked(self.on_back)
        self.btn_forward.on_clicked(self.on_forward)
        self.btn_end.on_clicked(self.on_end)
        self.btn_play.on_clicked(self.on_play)

    def on_start(self, event):
        self.is_playing = False
        if self.timer:
            self.timer.stop()
        self.current_frame = 0
        self.update_plot(self.current_frame)
        self.fig.canvas.draw()
        self.fig.canvas.flush_events()

    def on_back(self, event):
        self.is_playing = False
        if self.timer:
            self.timer.stop()
        if self.current_frame > 0:
            self.current_frame -= 1
            self.update_plot(self.current_frame)
            self.fig.canvas.draw()
            self.fig.canvas.flush_events()

    def on_forward(self, event):
        self.is_playing = False
        if self.timer:
            self.timer.stop()
        if self.current_frame < len(self.data) - 1:
            self.current_frame += 1
            self.update_plot(self.current_frame)
            self.fig.canvas.draw()
            self.fig.canvas.flush_events()

    def on_end(self, event):
        self.is_playing = False
        if self.timer:
            self.timer.stop()
        self.current_frame = len(self.data) - 1
        self.update_plot(self.current_frame)
        self.fig.canvas.draw()
        self.fig.canvas.flush_events()

    def on_play(self, event):
        if self.is_playing:
            self.is_playing = False
            if self.timer:
                self.timer.stop()
            self.btn_play.label.set_text("Play")
            self.fig.canvas.draw()
        else:
            self.is_playing = True
            self.btn_play.label.set_text("Pause")
            self.fig.canvas.draw()
            self.play_animation()

    def play_animation(self):
        if self.is_playing and self.current_frame < len(self.data) - 1:
            self.current_frame += 1
            self.update_plot(self.current_frame)
            self.fig.canvas.draw()
            self.fig.canvas.flush_events()
            self.timer = self.fig.canvas.new_timer(interval=500)
            self.timer.single_shot = True
            self.timer.add_callback(self.play_animation)
            self.timer.start()
        else:
            self.is_playing = False
            self.btn_play.label.set_text("Play")
            self.fig.canvas.draw()

    def show(self):
        """Display the interactive chart."""
        self.create_figure()
        self.current_frame = 0
        self.update_plot(self.current_frame)
        self.create_navigation_buttons()
        self.fig.canvas.draw()

        print("\nInteractive graph ready!")
        print("  - Total minutes: " + str(len(self.data)))
        print("  - Use buttons to navigate\n")

        plt.show()


def plot_intraday_data(data, target_date, start_time, end_time):
    """Create and display the interactive chart for a single day."""
    if data is None or data.empty:
        print("\nNo data to plot")
        return

    print("\n" + "=" * 60)
    print("Creating Interactive Graph...")
    print("=" * 60)

    output_dir = os.path.join(os.path.expanduser("~"), "Desktop", "Trading", "Temp")
    os.makedirs(output_dir, exist_ok=True)

    plotter = ChartPlotter(data, target_date, start_time, end_time, output_dir)
    plotter.show()
    print("Session completed")
