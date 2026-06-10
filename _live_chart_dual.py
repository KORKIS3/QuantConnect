"""
_live_chart_dual.py
-------------------
Two interactive charts side by side:
  1. CSV view — algo's internal signals/position (from tracking CSV)
  2. IB view  — actual IB fills/position (parsed from IB log)

Both share the same OHLC price data, but trade markers and P/L differ.

Usage:
    python _live_chart_dual.py
    python _live_chart_dual.py --date 2026-06-09
    python _live_chart_dual.py --interval 60
"""

import argparse
import os
import re
import glob
import time
from datetime import datetime
import pytz
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt

from plotFigure import ChartPlotter

_EST = pytz.timezone("US/Eastern")
_TRACKING_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "IB_Live", "tracking")
_LOG_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "IB_Live", "logs")


def _latest_date():
    return datetime.now(_EST).strftime("%Y-%m-%d")


def _find_tracking_csv(date_str):
    """Find the most recent day-session tracking CSV for a given date."""
    pattern = os.path.join(_TRACKING_ROOT, f"*{date_str}*0930*.csv")
    files = glob.glob(pattern)
    if not files:
        # Broader fallback
        pattern = os.path.join(_TRACKING_ROOT, f"*{date_str}*.csv")
        files = glob.glob(pattern)
    if not files:
        return None
    return max(files, key=os.path.getmtime)


def _find_ib_log(date_str):
    """Find the IB log with trade details (the DUO account log)."""
    date_compact = date_str.replace("-", "")
    pattern = os.path.join(_LOG_ROOT, f"fred_ib_DU*_{date_compact}_*.log")
    files = glob.glob(pattern)
    if not files:
        return None
    return max(files, key=os.path.getmtime)


def _load_csv(date_str):
    """Load tracking CSV and return DataFrame."""
    path = _find_tracking_csv(date_str)
    if path is None or not os.path.exists(path):
        return None
    try:
        df = pd.read_csv(path, index_col=0, parse_dates=True)
        df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
        # Filter to day session
        m = re.search(r'_(\d{4})\.csv$', os.path.basename(path))
        if m:
            hhmm = m.group(1)
            start_h, start_m = int(hhmm[:2]), int(hhmm[2:])
            cutoff = pd.Timestamp(f"{date_str} {start_h:02d}:{start_m:02d}", tz=_EST)
            df = df[df.index >= cutoff]
        return df if not df.empty else None
    except Exception as e:
        print(f"[Dual] CSV read error: {e}")
        return None


def _parse_ib_fills(date_str):
    """Parse IB log for actual fill events. Returns list of dicts."""
    path = _find_ib_log(date_str)
    if path is None:
        return []

    fills = []
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            # Match execDetails lines with fill info
            if "execDetails Execution(" not in line:
                continue
            # Extract side, price, shares, time
            side_m = re.search(r"side='(BOT|SLD)'", line)
            price_m = re.search(r"price=(\d+\.?\d*),\s*permId", line)
            shares_m = re.search(r"shares=(\d+\.?\d*)", line)
            time_m = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", line)
            if side_m and price_m and time_m:
                fill_time = pd.Timestamp(time_m.group(1), tz=_EST)
                fills.append({
                    "time": fill_time,
                    "side": "BUY" if side_m.group(1) == "BOT" else "SELL",
                    "price": float(price_m.group(1)),
                    "qty": int(float(shares_m.group(1))) if shares_m else 2,
                })
    return fills


def _build_ib_df(csv_df, fills):
    """Build an IB-view DataFrame: same OHLC as CSV but with IB's actual fills/position/P/L."""
    df = csv_df.copy()

    # Clear algo signal columns — we'll replace with IB actuals
    df["signal"] = ""
    df["buy_price"] = np.nan
    df["sell_price"] = np.nan
    df["position"] = "flat"
    df["pl"] = 0.0
    if "session_pl" in df.columns:
        df["session_pl"] = 0.0

    # Replay fills to compute IB position and P/L
    ib_position = 0  # number of contracts (+ = long, - = short)
    entry_price = 0.0
    realized_pl = 0.0

    # Map fills to bar times (floor to minute)
    fill_map = {}  # bar_time -> list of fills
    for fill in fills:
        bar_time = fill["time"].floor("min")
        if bar_time not in fill_map:
            fill_map[bar_time] = []
        fill_map[bar_time].append(fill)

    for idx in df.index:
        bar_fills = fill_map.get(idx, [])
        for fill in bar_fills:
            if fill["side"] == "BUY":
                df.at[idx, "signal"] = "BUY"
                df.at[idx, "buy_price"] = fill["price"]
                if ib_position < 0:
                    # Closing short
                    realized_pl += (entry_price - fill["price"]) * abs(ib_position)
                    ib_position += fill["qty"]
                    if ib_position > 0:
                        entry_price = fill["price"]
                elif ib_position == 0:
                    ib_position = fill["qty"]
                    entry_price = fill["price"]
                else:
                    # Adding to long (shouldn't happen with current logic)
                    ib_position += fill["qty"]
            else:  # SELL
                df.at[idx, "signal"] = "SELL"
                df.at[idx, "sell_price"] = fill["price"]
                if ib_position > 0:
                    # Closing long
                    realized_pl += (fill["price"] - entry_price) * ib_position
                    ib_position -= fill["qty"]
                    if ib_position < 0:
                        entry_price = fill["price"]
                elif ib_position == 0:
                    ib_position = -fill["qty"]
                    entry_price = fill["price"]
                else:
                    # Adding to short (shouldn't happen)
                    ib_position -= fill["qty"]

        # Set position label
        if ib_position > 0:
            df.at[idx, "position"] = "long"
        elif ib_position < 0:
            df.at[idx, "position"] = "short"
        else:
            df.at[idx, "position"] = "flat"

        # P/L: realized + unrealized
        unrealized = 0.0
        if ib_position > 0:
            unrealized = (df.at[idx, "Close"] - entry_price) * ib_position
        elif ib_position < 0:
            unrealized = (entry_price - df.at[idx, "Close"]) * abs(ib_position)
        df.at[idx, "pl"] = realized_pl + unrealized
        if "session_pl" in df.columns:
            df.at[idx, "session_pl"] = realized_pl + unrealized

    return df


def main():
    parser = argparse.ArgumentParser(description="Dual chart: CSV vs IB fills")
    parser.add_argument("--date", default=None, help="Date (default: today)")
    parser.add_argument("--interval", type=int, default=60, help="Refresh interval seconds")
    args = parser.parse_args()

    date_str = args.date or _latest_date()
    interval_ms = args.interval * 1000

    print(f"[Dual] Loading {date_str}...")

    # Load CSV data
    csv_df = _load_csv(date_str)
    if csv_df is None:
        print(f"[Dual] No tracking CSV found for {date_str}. Waiting...")
        while csv_df is None:
            time.sleep(5)
            csv_df = _load_csv(date_str)

    # Parse IB fills and build IB view
    fills = _parse_ib_fills(date_str)
    ib_df = _build_ib_df(csv_df, fills)

    print(f"[Dual] CSV: {len(csv_df)} bars, IB fills: {len(fills)}")

    # Create two chart windows
    plt.close("all")

    # Chart 1: CSV view (algo's internal state)
    csv_plotter = ChartPlotter(
        data=csv_df,
        target_date=date_str,
        start_time=csv_df.index[0].strftime("%H:%M"),
        end_time="17:00",
        output_dir=_TRACKING_ROOT,
        batch_mode=True,
    )
    csv_plotter.create_figure()
    csv_plotter.fig.canvas.manager.set_window_title(f"CSV View (Algo) — {date_str}")
    # Position first window on the left
    try:
        mngr = csv_plotter.fig.canvas.manager
        mngr.window.wm_geometry("+50+100")
    except Exception:
        pass
    csv_plotter.create_navigation_buttons()
    csv_plotter.current_frame = len(csv_df) - 1
    csv_plotter.update_plot(len(csv_df) - 1)

    # Force matplotlib to register the first figure before creating the second
    csv_plotter.fig.canvas.draw()
    plt.pause(0.1)

    # Chart 2: IB view (actual fills)
    ib_plotter = ChartPlotter(
        data=ib_df,
        target_date=date_str,
        start_time=ib_df.index[0].strftime("%H:%M"),
        end_time="17:00",
        output_dir=_TRACKING_ROOT,
        batch_mode=True,
    )
    ib_plotter.create_figure()
    ib_plotter.fig.canvas.manager.set_window_title(f"IB View (Actual Fills) — {date_str}")
    # Offset the second window so both are visible
    try:
        mngr = ib_plotter.fig.canvas.manager
        mngr.window.wm_geometry("+800+100")
    except Exception:
        pass
    ib_plotter.create_navigation_buttons()
    ib_plotter.current_frame = len(ib_df) - 1
    ib_plotter.update_plot(len(ib_df) - 1)

    # Force the second figure to render
    ib_plotter.fig.canvas.draw()
    plt.pause(0.1)

    state = {"row_count": len(csv_df), "fill_count": len(fills)}

    print(f"[Dual] Figures open: {plt.get_fignums()}")

    # Force both windows visible and raised
    try:
        csv_plotter.fig.canvas.manager.window.deiconify()
        csv_plotter.fig.canvas.manager.window.lift()
        csv_plotter.fig.canvas.manager.window.attributes('-topmost', True)
        csv_plotter.fig.canvas.manager.window.attributes('-topmost', False)
    except Exception:
        pass
    try:
        ib_plotter.fig.canvas.manager.window.deiconify()
        ib_plotter.fig.canvas.manager.window.lift()
        ib_plotter.fig.canvas.manager.window.attributes('-topmost', True)
        ib_plotter.fig.canvas.manager.window.attributes('-topmost', False)
    except Exception:
        pass

    def do_refresh():
        new_csv = _load_csv(date_str)
        if new_csv is None:
            return
        new_fills = _parse_ib_fills(date_str)
        new_ib = _build_ib_df(new_csv, new_fills)

        state["row_count"] = len(new_csv)
        state["fill_count"] = len(new_fills)

        # Update CSV chart
        csv_plotter.data = new_csv
        csv_plotter.current_frame = len(new_csv) - 1
        csv_plotter.update_plot(len(new_csv) - 1)
        csv_plotter.fig.canvas.draw()

        # Update IB chart
        ib_plotter.data = new_ib
        ib_plotter.current_frame = len(new_ib) - 1
        ib_plotter.update_plot(len(new_ib) - 1)
        ib_plotter.fig.canvas.draw()

        print(f"[Dual] Refreshed — {len(new_csv)} bars, {len(new_fills)} IB fills")

    # Wire refresh callbacks
    csv_plotter._refresh_callback = do_refresh
    ib_plotter._refresh_callback = do_refresh

    # Auto-poll using Tkinter's after()
    def _poll():
        new_csv = _load_csv(date_str)
        new_fills = _parse_ib_fills(date_str)
        if new_csv is not None and (len(new_csv) != state["row_count"] or len(new_fills) != state["fill_count"]):
            do_refresh()
        csv_plotter.fig.canvas.get_tk_widget().after(interval_ms, _poll)

    csv_plotter.fig.canvas.get_tk_widget().after(interval_ms, _poll)

    print(f"[Dual] Both charts open. Auto-refreshing every {args.interval}s. Close windows to stop.")
    plt.show(block=True)


if __name__ == "__main__":
    main()
