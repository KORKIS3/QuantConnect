"""
YM Futures Trading Analysis - Plotting Module

Pure visualization layer.  All calculations are performed by TradingAlgo
and stored in the enriched per-minute DataFrame before this module is called.
"""

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.widgets import Button
import pandas as pd
import os
import pytz

_EST = pytz.timezone("US/Eastern")

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
    def __init__(self, data, target_date, start_time, end_time, output_dir, batch_mode=False):
        missing = [c for c in _REQUIRED_COLS if c not in data.columns]
        if missing:
            from TradingAlgoFast import run_trading_algo_fast as run_trading_algo
            data = run_trading_algo(data, target_date, start_time, end_time)

        self.data = data
        self.target_date = target_date
        self.start_time = start_time
        self.end_time = end_time
        self.output_dir = output_dir
        self.batch_mode = batch_mode
        self.state = _StateCompat(self.data)

        self.current_frame = 0
        self.is_playing = False
        self.timer = None
        self.snapshots_taken = set()

        self.fig = None
        self.ax = None
        self.ax_top = None
        self.lines = {}
        self.signal_markers = {"buy": [], "sell": [], "halt": [], "tp": []}
        self.signal_annotations = {"buy": [], "sell": [], "halt": [], "tp": []}

        self.orange_angle_annotation = None
        self.yellow_angle_annotation = None
        self.purple_angle_annotation = None
        self.blue_angle_annotation = None

        self.stats_box = None
        self.current_time_text = None

    def detect_all_signals_once(self):
        pass

    # ------------------------------------------------------------------
    # Figure setup
    # ------------------------------------------------------------------

    def create_figure(self):
        self.fig = plt.figure(figsize=(16, 9))
        self.fig.subplots_adjust(left=0.07, right=0.82, top=0.92, bottom=0.12)
        self.ax = self.fig.add_subplot(111)

        self.fig.suptitle(
            f"YM Futures  {self.target_date}  ({self.start_time} – {self.end_time} ET)",
            fontsize=14, fontweight="bold")

        # Price lines — High (green), Low (red), Close (black)
        self.lines["high"],  = self.ax.plot([], [], color="green",  linewidth=1.8, marker="o", markersize=4, label="High")
        self.lines["low"],   = self.ax.plot([], [], color="red",    linewidth=1.8, marker="o", markersize=4, label="Low")
        self.lines["close"], = self.ax.plot([], [], color="black",  linewidth=2.2, marker="s", markersize=4, label="Close")

        # Ray lines — orange/yellow fixed, blue/purple families dynamic
        self.lines["ray_orange"],      = self.ax.plot([], [], color="orange",     linewidth=2, label="Orange ray",  alpha=0.9)
        self.lines["ray_yellow"],      = self.ax.plot([], [], color="gold",       linewidth=2, label="Yellow ray",  alpha=0.9)
        self.lines["ray_purple"],      = self.ax.plot([], [], color="darkviolet", linewidth=2, label="Purple ray",  alpha=0.9)
        self.lines["ray_blue"],        = self.ax.plot([], [], color="blue",       linewidth=2, label="Blue ray",    alpha=0.9)
        self.lines["ray_dark_purple"], = self.ax.plot([], [], color="indigo",     linewidth=2, label="Dark purple", alpha=0.9)
        self.lines["ray_magenta"],     = self.ax.plot([], [], color="magenta",    linewidth=1.5, label="Swing High", alpha=0.85, linestyle="--")
        self.lines["ray_lime"],        = self.ax.plot([], [], color="limegreen",  linewidth=1.5, label="Swing Low",  alpha=0.85, linestyle="--")

        # Steeper blue lines (progressively darker blue)
        _steep_blue_colors   = ["#0055CC", "#003399", "#001166", "#000033"]
        _steep_purple_colors = ["#7700CC", "#550099", "#330066", "#110033"]
        for li in range(4):
            self.lines[f"ray_blue_steep_{li}"],   = self.ax.plot([], [], color=_steep_blue_colors[li],
                                                                   linewidth=1.8, alpha=0.85, linestyle="--")
            self.lines[f"ray_purple_steep_{li}"], = self.ax.plot([], [], color=_steep_purple_colors[li],
                                                                   linewidth=1.8, alpha=0.85, linestyle="--")

        self.ax.set_ylabel("Price", fontsize=12)
        self.ax.set_xlabel("Time (ET)", fontsize=12)
        self.ax.legend(loc="upper left", fontsize=9, framealpha=0.7)
        self.ax.grid(True, alpha=0.25, linestyle="--")
        self.ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=_EST))
        plt.setp(self.ax.xaxis.get_majorticklabels(), rotation=45, ha="right")

        if len(self.data) > 0:
            y_min = float(self.data["y_min"].iloc[0])
            y_max = float(self.data["y_max"].iloc[0])
            self.ax.set_ylim(y_min, y_max)
            self.ax.set_xlim(self.data.index[0], self.data.index[-1])

        # Stats box — right side, includes P/L
        self.stats_box = self.ax.text(
            1.01, 0.99, "", transform=self.ax.transAxes, fontsize=9,
            verticalalignment="top", horizontalalignment="left",
            bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.85),
            fontfamily="monospace")

        # Current time label — bottom centre
        self.current_time_text = self.ax.text(
            0.5, -0.08, "", transform=self.ax.transAxes, fontsize=10,
            ha="center", bbox=dict(boxstyle="round", facecolor="lightblue", alpha=0.8))

        # No top twin axis — P/L is in the stats box instead
        self.ax_top = None

    # ------------------------------------------------------------------
    # Main render
    # ------------------------------------------------------------------

    def update_plot(self, frame):
        frame = max(0, min(frame, len(self.data) - 1))
        current_data = self.data.iloc[:frame + 1]
        if len(current_data) == 0:
            return

        self.update_price_lines(current_data)
        self.update_ray_lines(current_data)
        self.update_annotations(current_data)
        self.update_signal_markers(current_data)
        self.update_stats(current_data)
        self.save_snapshot(current_data)

    # ------------------------------------------------------------------
    # Render helpers
    # ------------------------------------------------------------------

    def update_price_lines(self, current_data):
        times = current_data.index
        self.lines["high"].set_data(times,  current_data["High"])
        self.lines["low"].set_data(times,   current_data["Low"])
        self.lines["close"].set_data(times, current_data["Close"])
        # Y-axis locked to full session range (set once in create_figure)

    def _draw_ray(self, line_key, ann_attr,
                  start_time, start_price, end_price,
                  current_time, current_price, angle,
                  color, edge_color, y_offset):
        import math
        end_time = current_time
        if math.isnan(float(start_price)) or math.isnan(float(end_price)):
            self.lines[line_key].set_data([], [])
            old_ann = getattr(self, ann_attr, None)
            if old_ann is not None:
                try: old_ann.remove()
                except Exception: pass
            setattr(self, ann_attr, None)
            return
        self.lines[line_key].set_data([start_time, end_time], [start_price, end_price])

        old_ann = getattr(self, ann_attr, None)
        if old_ann is not None:
            try:
                old_ann.remove()
            except Exception:
                pass

        va = "top" if y_offset < 0 else "bottom"
        ann = self.ax.annotate(
            f"{abs(angle):.1f}°",
            xy=(current_time, current_price),
            xytext=(6, y_offset), textcoords="offset points",
            ha="left", va=va, fontsize=8, color=color, fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white",
                      alpha=0.75, edgecolor=edge_color, linewidth=1.5))
        setattr(self, ann_attr, ann)

    def update_ray_lines(self, current_data):
        row = current_data.iloc[-1]
        current_time = current_data.index[-1]

        self._draw_ray("ray_orange", "orange_angle_annotation",
            row["orange_ray_start_time"], float(row["orange_ray_start_price"]),
            float(row["orange_ray_end_price"]),
            current_time, float(row["orange_ray"]), float(row["orange_angle"]),
            "darkorange", "orange", -14)

        self._draw_ray("ray_yellow", "yellow_angle_annotation",
            row["yellow_ray_start_time"], float(row["yellow_ray_start_price"]),
            float(row["yellow_ray_end_price"]),
            current_time, float(row["yellow_ray"]), float(row["yellow_angle"]),
            "goldenrod", "gold", -28)

        purple_angle = row["purple_angle"][-1] if isinstance(row["purple_angle"], list) else float(row["purple_angle"])
        self._draw_ray("ray_purple", "purple_angle_annotation",
            row["purple_ray_start_time"], float(row["purple_ray_start_price"]),
            float(row["purple_ray_end_price"]),
            current_time, float(row["purple_ray"]), purple_angle,
            "darkviolet", "darkviolet", 14)

        blue_angle = row["blue_angle"][-1] if isinstance(row["blue_angle"], list) else float(row["blue_angle"])
        self._draw_ray("ray_blue", "blue_angle_annotation",
            row["blue_ray_start_time"], float(row["blue_ray_start_price"]),
            float(row["blue_ray_end_price"]),
            current_time, float(row["blue_ray"]), blue_angle,
            "blue", "blue", 28)

        self.lines["ray_dark_purple"].set_data([], [])
        self.lines["ray_magenta"].set_data([], [])
        self.lines["ray_lime"].set_data([], [])

        # Steeper blue/purple lines
        # Draw from P1 anchor (last touch on primary line) to current bar value
        for li in range(4):
            # Steeper blue
            col_v  = f"blue_steep_{li}_vals"
            col_s  = f"blue_steep_{li}_start_prices"
            col_p1 = f"blue_steep_{li}_p1_idxs"
            key    = f"ray_blue_steep_{li}"
            if col_v in current_data.columns:
                series = current_data[col_v].dropna()
                if not series.empty:
                    # Only show the steep line up to the LAST valid bar (where it's not NaN)
                    # This makes invalidated lines disappear from the chart
                    last_valid_time = series.index[-1]
                    
                    # Check if this steep line is still valid at the current time
                    # If the last valid time is before the current time, don't show it
                    if last_valid_time >= current_data.index[-1]:
                        p1_series = current_data[col_p1]
                        valid_p1  = p1_series[p1_series >= 0]
                        p1i       = int(valid_p1.iloc[-1]) if not valid_p1.empty else -1
                        p1_time   = self.data.index[p1i] if 0 <= p1i < len(self.data) else series.index[0]
                        sp        = float(current_data[col_s].dropna().iloc[-1])
                        ep        = float(series.iloc[-1])
                        self.lines[key].set_data([p1_time, series.index[-1]], [sp, ep])
                    else:
                        # Steep line was invalidated - don't show it
                        self.lines[key].set_data([], [])
                else:
                    self.lines[key].set_data([], [])
            else:
                self.lines[key].set_data([], [])

            # Steeper purple
            col_v  = f"purple_steep_{li}_vals"
            col_s  = f"purple_steep_{li}_start_prices"
            col_p1 = f"purple_steep_{li}_p1_idxs"
            key    = f"ray_purple_steep_{li}"
            if col_v in current_data.columns:
                series = current_data[col_v].dropna()
                if not series.empty:
                    # Only show the steep line up to the LAST valid bar (where it's not NaN)
                    # This makes invalidated lines disappear from the chart
                    last_valid_time = series.index[-1]
                    
                    # Check if this steep line is still valid at the current time
                    # If the last valid time is before the current time, don't show it
                    if last_valid_time >= current_data.index[-1]:
                        p1_series = current_data[col_p1]
                        valid_p1  = p1_series[p1_series >= 0]
                        p1i       = int(valid_p1.iloc[-1]) if not valid_p1.empty else -1
                        p1_time   = self.data.index[p1i] if 0 <= p1i < len(self.data) else series.index[0]
                        sp        = float(current_data[col_s].dropna().iloc[-1])
                        ep        = float(series.iloc[-1])
                        self.lines[key].set_data([p1_time, series.index[-1]], [sp, ep])
                    else:
                        # Steep line was invalidated - don't show it
                        self.lines[key].set_data([], [])
                else:
                    self.lines[key].set_data([], [])
            else:
                self.lines[key].set_data([], [])

    def update_annotations(self, current_data):
        """Draw High / Low / Close labels for every bar."""
        for ann in getattr(self, "annotations", []):
            try:
                ann.remove()
            except Exception:
                pass
        self.annotations = []

        if len(current_data) == 0:
            return

        for time, row in current_data.iterrows():
            t = time.strftime("%H:%M")
            ann = self.ax.annotate(
                f"{int(row['High'])}\n{t}", xy=(time, row["High"]),
                xytext=(0, 7), textcoords="offset points", ha="center", va="bottom",
                fontsize=7, color="darkgreen", fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.2", facecolor="lightgreen", alpha=0.7, edgecolor="green"))
            self.annotations.append(ann)

            ann = self.ax.annotate(
                f"{int(row['Low'])}\n{t}", xy=(time, row["Low"]),
                xytext=(0, -7), textcoords="offset points", ha="center", va="top",
                fontsize=7, color="darkred", fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.2", facecolor="lightcoral", alpha=0.7, edgecolor="red"))
            self.annotations.append(ann)

            ann = self.ax.annotate(
                f"{int(row['Close'])}\n{t}", xy=(time, row["Close"]),
                xytext=(7, 0), textcoords="offset points", ha="left", va="center",
                fontsize=7, color="black", fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.2", facecolor="lightgray", alpha=0.7, edgecolor="black"))
            self.annotations.append(ann)

    def update_signal_markers(self, current_data):
        for marker in self.signal_markers["buy"] + self.signal_markers["sell"] + self.signal_markers["halt"] + self.signal_markers.get("tp", []) + self.signal_markers.get("expired", []) + self.signal_markers.get("pending", []):
            try:
                marker.remove()
            except Exception:
                pass
        for ann in self.signal_annotations["buy"] + self.signal_annotations["sell"] + self.signal_annotations["halt"] + self.signal_annotations.get("tp", []) + self.signal_annotations.get("expired", []) + self.signal_annotations.get("pending", []):
            try:
                ann.remove()
            except Exception:
                pass

        self.signal_markers     = {"buy": [], "sell": [], "halt": [], "tp": [], "expired": [], "pending": []}
        self.signal_annotations = {"buy": [], "sell": [], "halt": [], "tp": [], "expired": [], "pending": []}

        if "signal" not in current_data.columns:
            return

        has_order_status = "order_status" in current_data.columns

        for ts, row in current_data.iterrows():
            sig    = row.get("signal", "")
            is_liq = bool(row.get("is_liquidation", False))
            order_status = str(row.get("order_status", "")) if has_order_status else ""

            # Expired limit order — grey X marker at the limit price
            if order_status == "expired":
                limit_p = row.get("limit_price")
                if pd.notna(limit_p):
                    limit_p = float(limit_p)
                    marker, = self.ax.plot(ts, limit_p, marker="x", markersize=10,
                                           color="grey", markeredgewidth=2.5, zorder=9)
                    self.signal_markers["expired"].append(marker)
                    ann = self.ax.annotate(
                        f"EXPIRED\n{int(limit_p)}", xy=(ts, limit_p), xytext=(0, -18),
                        textcoords="offset points",
                        ha="center", va="top", fontsize=7, color="white", fontweight="bold",
                        bbox=dict(boxstyle="round,pad=0.3", facecolor="grey", alpha=0.7,
                                  edgecolor="dimgrey", linewidth=1.0))
                    self.signal_annotations["expired"].append(ann)
                continue  # don't draw a buy/sell marker for expired signals

            # Pending limit order — hollow circle marker at the limit price
            if order_status == "pending":
                limit_p = row.get("limit_price")
                if pd.notna(limit_p):
                    limit_p = float(limit_p)
                    color = "cyan" if sig == "BUY" or (not sig and limit_p < row.get("Close", 0)) else "orange"
                    marker, = self.ax.plot(ts, limit_p, marker="o", markersize=10,
                                           color="none", markeredgecolor=color,
                                           markeredgewidth=2.0, zorder=9)
                    self.signal_markers["pending"].append(marker)
                    ann = self.ax.annotate(
                        f"LIMIT\n{int(limit_p)}", xy=(ts, limit_p), xytext=(0, -18),
                        textcoords="offset points",
                        ha="center", va="top", fontsize=7, color="white", fontweight="bold",
                        bbox=dict(boxstyle="round,pad=0.3", facecolor=color, alpha=0.7,
                                  edgecolor=color, linewidth=1.0))
                    self.signal_annotations["pending"].append(ann)
                continue

            if sig == "BUY":
                # Use fill_price if available (actual IB fill), else buy_price (theoretical)
                if has_order_status and order_status == "filled" and pd.notna(row.get("fill_price")):
                    price = float(row["fill_price"])
                    label_prefix = "FILLED" if not is_liq else "LIQ"
                    face_color = "#00aa00"  # darker green for confirmed fill
                    edge_color = "#005500"
                else:
                    price = row.get("buy_price")
                    if pd.isna(price):
                        continue
                    price = float(price)
                    label_prefix = "LIQ" if is_liq else "BUY"
                    face_color = "green"
                    edge_color = "darkgreen"

                label = label_prefix + "\n" + str(int(price))
                marker, = self.ax.plot(ts, price, marker="^", markersize=12,
                                       color=face_color, markeredgecolor=edge_color,
                                       markeredgewidth=1.5, zorder=10)
                self.signal_markers["buy"].append(marker)
                ann = self.ax.annotate(
                    label, xy=(ts, price), xytext=(0, 22), textcoords="offset points",
                    ha="center", va="bottom", fontsize=8, color="white", fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.4", facecolor=face_color, alpha=0.9,
                              edgecolor=edge_color, linewidth=1.5),
                    arrowprops=dict(arrowstyle="->", color=face_color, lw=1.5))
                self.signal_annotations["buy"].append(ann)

                # Draw dashed line from signal price to limit/fill price if different
                if has_order_status and order_status == "filled":
                    sig_p = row.get("buy_price")
                    if pd.notna(sig_p) and abs(float(sig_p) - price) > 2:
                        self.ax.plot([ts, ts], [float(sig_p), price], '--',
                                     color='green', alpha=0.5, lw=1.0, zorder=8)

            elif sig == "SELL":
                # Use fill_price if available (actual IB fill), else sell_price (theoretical)
                if has_order_status and order_status == "filled" and pd.notna(row.get("fill_price")):
                    price = float(row["fill_price"])
                    label_prefix = "FILLED" if not is_liq else "LIQ"
                    face_color = "#cc0000"  # darker red for confirmed fill
                    edge_color = "#660000"
                else:
                    price = row.get("sell_price")
                    if pd.isna(price):
                        continue
                    price = float(price)
                    label_prefix = "LIQ" if is_liq else "SELL"
                    face_color = "red"
                    edge_color = "darkred"

                label = label_prefix + "\n" + str(int(price))
                marker, = self.ax.plot(ts, price, marker="v", markersize=12,
                                       color=face_color, markeredgecolor=edge_color,
                                       markeredgewidth=1.5, zorder=10)
                self.signal_markers["sell"].append(marker)
                ann = self.ax.annotate(
                    label, xy=(ts, price), xytext=(0, -22), textcoords="offset points",
                    ha="center", va="top", fontsize=8, color="white", fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.4", facecolor=face_color, alpha=0.9,
                              edgecolor=edge_color, linewidth=1.5),
                    arrowprops=dict(arrowstyle="->", color=face_color, lw=1.5))
                self.signal_annotations["sell"].append(ann)

                # Draw dashed line from signal price to limit/fill price if different
                if has_order_status and order_status == "filled":
                    sig_p = row.get("sell_price")
                    if pd.notna(sig_p) and abs(float(sig_p) - price) > 2:
                        self.ax.plot([ts, ts], [float(sig_p), price], '--',
                                     color='red', alpha=0.5, lw=1.0, zorder=8)

            # Partial TP marker — gold diamond on the bar where TP fired
            if bool(row.get("partial_tp", False)):
                tp_price = float(row.get("Close", 0))
                marker, = self.ax.plot(ts, tp_price, marker="D", markersize=9,
                                       color="gold", markeredgecolor="darkorange",
                                       markeredgewidth=1.5, zorder=11)
                self.signal_markers["tp"].append(marker)
                ann = self.ax.annotate(
                    f"TP\n{int(tp_price)}", xy=(ts, tp_price), xytext=(18, 0),
                    textcoords="offset points",
                    ha="left", va="center", fontsize=7, color="white", fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.3", facecolor="darkorange", alpha=0.9,
                              edgecolor="gold", linewidth=1.2))
                self.signal_annotations["tp"].append(ann)

    def update_stats(self, current_data):
        row   = current_data.iloc[-1]
        times = current_data.index

        session_open  = float(row["session_open"])
        current_close = float(row["Close"])
        price_change  = float(row["rolling_price_change"])
        max_high      = float(row["rolling_max_high"])
        min_low       = float(row["rolling_min_low"])
        price_range   = float(row["rolling_range"])
        max_time      = pd.Timestamp(row["rolling_max_high_time"]).strftime("%H:%M")
        min_time      = pd.Timestamp(row["rolling_min_low_time"]).strftime("%H:%M")
        n_buy         = int(row["rolling_buy_count"])
        n_sell        = int(row["rolling_sell_count"])
        session_pl    = float(row.get("session_pl", 0.0))
        position      = str(row.get("position", "flat"))
        pl_sign       = "+" if session_pl >= 0 else ""
        pl_color_tag  = "▲" if session_pl > 0 else ("▼" if session_pl < 0 else "–")

        stats_text  = f"Bar: {len(current_data)}/{len(self.data)}\n"
        stats_text += f"Time: {times[-1].strftime('%H:%M')}\n"
        stats_text += "─" * 18 + "\n"
        stats_text += f"Open:  {session_open:,.0f}\n"
        stats_text += f"Close: {current_close:,.0f}\n"
        stats_text += f"Chg:   {price_change:+.0f} pts\n"
        stats_text += "─" * 18 + "\n"
        stats_text += f"High:  {max_high:,.0f} @{max_time}\n"
        stats_text += f"Low:   {min_low:,.0f} @{min_time}\n"
        stats_text += f"Range: {price_range:.0f} pts\n"
        stats_text += "─" * 18 + "\n"
        stats_text += f"Pos:   {position}\n"
        stats_text += f"P/L:   {pl_sign}{session_pl:.0f} {pl_color_tag}\n"
        stats_text += "─" * 18 + "\n"
        stats_text += f"Sigs:  {n_buy}B  {n_sell}S"

        self.stats_box.set_text(stats_text)
        self.current_time_text.set_text(times[-1].strftime("%H:%M:%S  ET"))

    def update_pl_axis(self, current_data):
        # P/L is now in the stats box — this is a no-op kept for compatibility.
        pass

    def save_snapshot(self, current_data):
        if self.batch_mode or not self.output_dir:
            return
        snapshot_times = ["09:31", "09:38", "09:45", "09:55", "10:00"]
        current_time_hhmm = current_data.index[-1].strftime("%H:%M")
        if current_time_hhmm in snapshot_times and current_time_hhmm not in self.snapshots_taken:
            timestamp_filename = current_data.index[-1].strftime("%Y%m%d_%H%M")
            snapshot_filename = os.path.join(
                self.output_dir, f"YM_{self.target_date}_{timestamp_filename}.png")
            self.fig.savefig(snapshot_filename, dpi=150, bbox_inches="tight")
            self.snapshots_taken.add(current_time_hhmm)

    # ------------------------------------------------------------------
    # Navigation buttons
    # ------------------------------------------------------------------

    def create_navigation_buttons(self):
        ax_start   = plt.axes([0.10, 0.02, 0.09, 0.04])
        ax_back    = plt.axes([0.21, 0.02, 0.09, 0.04])
        ax_forward = plt.axes([0.32, 0.02, 0.09, 0.04])
        ax_end     = plt.axes([0.43, 0.02, 0.09, 0.04])
        ax_play    = plt.axes([0.54, 0.02, 0.09, 0.04])

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

    def _on_scroll(self, event):
        """Mouse wheel zoom: scroll up = zoom in, scroll down = zoom out."""
        if event.inaxes != self.ax:
            return
        ax = self.ax
        xlim = ax.get_xlim()
        ylim = ax.get_ylim()
        xdata = event.xdata
        ydata = event.ydata
        if xdata is None or ydata is None:
            return
        scale = 0.85 if event.button == 'up' else 1.15
        # Zoom around mouse position
        ax.set_xlim([xdata - (xdata - xlim[0]) * scale,
                     xdata + (xlim[1] - xdata) * scale])
        ax.set_ylim([ydata - (ydata - ylim[0]) * scale,
                     ydata + (ylim[1] - ydata) * scale])
        self.fig.canvas.draw_idle()

    def show(self):
        self.create_figure()
        self.current_frame = 0
        self.update_plot(self.current_frame)
        self.create_navigation_buttons()
        # Wire up mouse wheel zoom
        self.fig.canvas.mpl_connect('scroll_event', self._on_scroll)
        self.fig.canvas.draw()
        plt.show()


def plot_intraday_data(data, target_date, start_time, end_time):
    if data is None or data.empty:
        print("No data to plot")
        return
    output_dir = os.path.join(os.path.expanduser("~"), "Desktop", "Trading", "Temp")
    os.makedirs(output_dir, exist_ok=True)
    plotter = ChartPlotter(data, target_date, start_time, end_time, output_dir)
    plotter.show()
