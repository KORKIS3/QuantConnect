"""
_live_chart_monitor.py
----------------------
Reopens a live chart from the tracking CSV and auto-refreshes when new data arrives.

Usage:
    python _live_chart_monitor.py
    python _live_chart_monitor.py --date 2026-04-22
    python _live_chart_monitor.py --interval 60
"""

import argparse
import os
import glob
import time
import threading
from datetime import datetime
import pytz
import pandas as pd
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt

from plotFigure import ChartPlotter

_EST = pytz.timezone("US/Eastern")
_TRACKING_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "IB_Live", "tracking")


def _latest_date():
    return datetime.now(_EST).strftime("%Y-%m-%d")


def _load_csv(date_str):
    # Find the most recently modified tracking CSV for this date
    pattern = os.path.join(_TRACKING_ROOT, f"YM_tracking_{date_str}_*.csv")
    files = glob.glob(pattern)
    if not files:
        # fallback to old format
        path = os.path.join(_TRACKING_ROOT, f"YM_tracking_{date_str}.csv")
        files = [path] if os.path.exists(path) else []
    if not files:
        return None

    # Always prefer the night session file if it exists and is recent
    night_files = [f for f in files if "_1800" in os.path.basename(f)]
    day_files   = [f for f in files if "_1800" not in os.path.basename(f)]

    now_et = datetime.now(_EST)
    if now_et.hour >= 18 or now_et.hour < 9:
        # Night hours — prefer night file
        candidates = night_files if night_files else files
    else:
        # Day hours — prefer day file
        candidates = day_files if day_files else files

    path = max(candidates, key=os.path.getmtime)
    print(f"[Monitor] Loading: {os.path.basename(path)}")

    try:
        df = pd.read_csv(path, index_col=0, parse_dates=True)
        df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)

        # Extract start time from filename and filter bars
        basename = os.path.basename(path)
        # e.g. YM_tracking_2026-04-22_1800.csv -> start = 18:00
        import re
        m = re.search(r'_(\d{4})\.csv$', basename)
        if m:
            hhmm = m.group(1)
            start_h, start_m = int(hhmm[:2]), int(hhmm[2:])
            if start_h >= 18:
                # Night session — only keep 18:00+ bars
                cutoff = pd.Timestamp(f"{date_str} {start_h:02d}:{start_m:02d}", tz=_EST)
                df = df[df.index >= cutoff]
            else:
                # Day session — only keep bars from start time
                cutoff = pd.Timestamp(f"{date_str} {start_h:02d}:{start_m:02d}", tz=_EST)
                df = df[df.index >= cutoff]

        return df if not df.empty else None
    except Exception as e:
        print(f"[Monitor] CSV read error: {e}")
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date",     default=None, help="Date to monitor (default: today)")
    parser.add_argument("--interval", type=int, default=60, help="Refresh interval seconds (default: 60)")
    args = parser.parse_args()

    date_str = args.date or _latest_date()
    interval_ms = args.interval * 1000

    print(f"[Monitor] Watching {date_str} — refreshing every {args.interval}s")

    df = _load_csv(date_str)
    if df is None:
        print(f"[Monitor] Waiting for CSV...")
        while df is None:
            time.sleep(5)
            df = _load_csv(date_str)

    # Build chart once — no ion(), no pause()
    plt.close("all")
    plotter = ChartPlotter(
        data=df,
        target_date=date_str,
        start_time=df.index[0].strftime("%H:%M"),
        end_time="17:00",   # fixed end so x-axis never rescales
        output_dir=_TRACKING_ROOT,
        batch_mode=True,    # skip snapshot saves on every update
    )
    plotter.create_figure()
    plotter.create_navigation_buttons()
    plotter.current_frame = len(df) - 1
    plotter.update_plot(len(df) - 1)
    print(f"[Monitor] Chart open — {len(df)} bars from {df.index[0].strftime('%H:%M')}")

    state = {"row_count": len(df)}

    def do_refresh():
        new_df = _load_csv(date_str)
        if new_df is None:
            return
        state["row_count"] = len(new_df)
        plotter.data = new_df
        plotter.current_frame = len(new_df) - 1
        plotter.update_plot(len(new_df) - 1)
        plotter.fig.canvas.draw()
        print(f"[Monitor] Updated — {len(new_df)} rows  last bar: {new_df.index[-1].strftime('%H:%M')}")

    # Wire Refresh Now button
    plotter._refresh_callback = do_refresh

    # Use Tkinter's after() to poll — no continuous redraw
    def _poll():
        new_df = _load_csv(date_str)
        if new_df is not None and len(new_df) != state["row_count"]:
            do_refresh()
        # Schedule next poll
        plotter.fig.canvas.get_tk_widget().after(interval_ms, _poll)

    plotter.fig.canvas.get_tk_widget().after(interval_ms, _poll)

    print(f"[Monitor] Auto-refreshing every {args.interval}s. Close the window to stop.")
    plt.show(block=True)


if __name__ == "__main__":
    main()
