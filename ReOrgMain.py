"""ReOrgMain

Per-day orchestration for the YM trading workflow.
"""

import os
from typing import Optional

import pandas as pd
import pytz

from TradingAlgoFast import run_trading_algo_fast as run_trading_algo
from plotFigure import ChartPlotter

_EST = pytz.timezone("US/Eastern")


def _load_csv_as_df(fp: str) -> pd.DataFrame:
    """Load a YM intraday CSV and return a timezone-aware DataFrame."""
    df = pd.read_csv(fp, index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index, utc=False)
    if df.index.tz is None:
        df.index = df.index.tz_localize(_EST)
    else:
        df.index = df.index.tz_convert(_EST)
    return df


def _filter_window(data: pd.DataFrame, target_date: str, start_time: str, end_time: str) -> pd.DataFrame:
    try:
        t_start = pd.Timestamp(f"{target_date} {start_time}:00", tz=_EST)
        t_end   = pd.Timestamp(f"{target_date} {end_time}:00", tz=_EST)
        if data.index.tz is None:
            data.index = data.index.tz_localize(_EST)
        else:
            data.index = data.index.tz_convert(_EST)
        return data[(data.index >= t_start) & (data.index <= t_end)]
    except Exception as e:
        print(f"Warning: could not filter data by time window: {e}")
        return data


def _save_image(algo_df, target_date, start_time, end_time, image_root):
    import matplotlib.pyplot as _plt
    os.makedirs(image_root, exist_ok=True)
    plotter = ChartPlotter(algo_df, target_date, start_time, end_time, image_root, batch_mode=True)
    try:
        plotter.create_figure()
        plotter.update_plot(len(algo_df) - 1)
        base = target_date or "chart"
        img_path = os.path.join(image_root, f"{base}.jpg")
        plotter.fig.savefig(img_path, dpi=150, bbox_inches="tight")
        print(f"Saved plot image: {img_path}")
    except Exception as exc:
        print(f"Failed to save plot image for {target_date}: {exc}")
    finally:
        try:
            _plt.close(plotter.fig)
        except Exception:
            pass


def run_single_day(
    target_date: str,
    start_time: str = "09:30",
    end_time: str = "09:35",
    csv_root: Optional[str] = None,
    show_plot: bool = True,
    image_root: Optional[str] = None,
    tracking_root: Optional[str] = None,
) -> pd.DataFrame:
    if csv_root is None:
        csv_root = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "930_1000")

    csv_path = os.path.join(csv_root, f"CBOT_MINI_YM1_{target_date}.csv")
    print(f"Loading: {csv_path}")
    data = _load_csv_as_df(csv_path)

    if data is None or data.empty:
        raise ValueError(f"No intraday data found for {target_date} at {csv_path}")

    data = _filter_window(data, target_date, start_time, end_time)
    algo_df = run_trading_algo(data, target_date, start_time, end_time)

    if tracking_root is not None:
        os.makedirs(tracking_root, exist_ok=True)
        algo_df.to_csv(os.path.join(tracking_root, f"YM_tracking_{target_date}.csv"))

    if image_root is not None:
        _save_image(algo_df, target_date, start_time, end_time, image_root)

    if show_plot:
        plot_results(algo_df, target_date, start_time, end_time)

    return algo_df


def run_live_session(
    data: pd.DataFrame,
    target_date: str,
    start_time: str = "09:30",
    end_time: str = "09:35",
    show_plot: bool = True,
    image_root: Optional[str] = None,
    tracking_root: Optional[str] = None,
) -> pd.DataFrame:
    if data is None or data.empty:
        raise ValueError(f"No live data available for {target_date}")

    data = _filter_window(data, target_date, start_time, end_time)

    if data.empty:
        raise ValueError(f"No live data in window {start_time}-{end_time} for {target_date}")

    algo_df = run_trading_algo(data, target_date, start_time, end_time)

    if tracking_root is not None:
        os.makedirs(tracking_root, exist_ok=True)
        algo_df.to_csv(os.path.join(tracking_root, f"YM_tracking_{target_date}.csv"))

    if image_root is not None:
        _save_image(algo_df, target_date, start_time, end_time, image_root)

    if show_plot:
        plot_results(algo_df, target_date, start_time, end_time)

    return algo_df


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        parts = arg.split("-")
        if len(parts) == 2:
            year = int(os.environ.get("TARGET_YEAR", "2026"))
            target_date = f"{year}-{int(parts[0]):02d}-{int(parts[1]):02d}"
        else:
            target_date = arg
    else:
        target_date = os.environ.get("TARGET_DATE", "2026-02-11")

    run_single_day(target_date, show_plot=True)
