"""ReOrgMain

Per-day orchestration for the YM trading workflow.

This module can:
- Load a single day's intraday CSV from the desktop folder.
- Run the headless trading algorithm (`TradingAlgo.run_trading_algo`).
- Optionally render and show the interactive chart via `Plotter`.
- Optionally save a final chart image and a per-minute tracking CSV
  without opening any interactive windows (for batch runs).
"""

import os
from typing import Optional

import pandas as pd

from RunFullDataSet import _load_csv_as_df
from TradingAlgo import run_trading_algo
from Plotter import plot_results
from plotFigure import ChartPlotter


def run_single_day(
    target_date: str,
    start_time: str = "09:30",
    end_time: str = "10:00",
    csv_root: Optional[str] = None,
    show_plot: bool = True,
    image_root: Optional[str] = None,
    tracking_root: Optional[str] = None,
) -> pd.DataFrame:
    """Run the full workflow for a single date.

    Always runs the trading algorithm to produce an enriched per-minute
    DataFrame. Optionally:
    - `show_plot`: display the interactive chart (for manual runs).
    - `image_root`: save a final chart image under this root directory
      (used by RunAllDays for headless batch images).
    - `tracking_root`: save the enriched DataFrame as a CSV in this
      directory (per-day tracking sheet).
    """

    if csv_root is None:
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        csv_root = os.path.join(desktop, "CBOT_MINI_YM1_ByDate_930_1000")

    csv_path = os.path.join(csv_root, f"CBOT_MINI_YM1_{target_date}.csv")

    print(f"Loading: {csv_path}")
    data = _load_csv_as_df(csv_path)

    if data is None or data.empty:
        raise ValueError(f"No intraday data found for {target_date} at {csv_path}")

    # Run trading algorithm to compute signals / P&L per minute.
    algo_df = run_trading_algo(data, target_date, start_time, end_time)

    # Optionally persist the tracking DataFrame as a CSV.
    if tracking_root is not None:
        os.makedirs(tracking_root, exist_ok=True)
        tracking_path = os.path.join(tracking_root, f"YM_tracking_{target_date}.csv")
        algo_df.to_csv(tracking_path)
        print(f"Saved tracking CSV: {tracking_path}")

    # Optionally save a final chart image without showing a window.
    if image_root is not None:
        os.makedirs(image_root, exist_ok=True)

        # Use the same batch-style pattern as RunFullDataSet: create a
        # ChartPlotter in batch_mode, step through frames, and save the
        # final rendered figure.
        output_dir = image_root  # re-use as the plotter's output_dir
        plotter = ChartPlotter(data, target_date, start_time, end_time, output_dir, batch_mode=True)

        try:
            plotter.create_figure()
            plotter.fig.canvas.draw()
        except Exception:
            pass

        try:
            for frame in range(len(data)):
                plotter.update_plot(frame)
                if plotter.state.trading_halted:
                    break
        except Exception:
            pass

        # Build a unique image path per date.
        base_name = target_date or "chart"
        img_name = f"{base_name}.jpg"
        img_path = os.path.join(image_root, img_name)
        suffix = 1
        while os.path.exists(img_path):
            img_name = f"{base_name}_{suffix}.jpg"
            img_path = os.path.join(image_root, img_name)
            suffix += 1

        try:
            final_frame = max(0, len(getattr(plotter, "data", [])) - 1)
            plotter.state.current_frame = final_frame
            plotter.update_plot(final_frame)
            try:
                plotter.fig.canvas.draw()
                plotter.fig.canvas.flush_events()
            except Exception:
                pass

            plotter.fig.savefig(img_path, dpi=150, bbox_inches="tight")
            print(f"Saved plot image: {img_path}")
        except Exception as exc:
            print(f"Failed to save plot image for {target_date}: {exc}")
        finally:
            try:
                import matplotlib.pyplot as _plt
                _plt.close(plotter.fig)
            except Exception:
                pass

    # Optionally show the interactive chart (manual workflows).
    if show_plot:
        plot_results(algo_df, target_date, start_time, end_time)

    return algo_df


if __name__ == "__main__":
    # Simple CLI behaviour: allow overriding the date via env var
    # TARGET_DATE; default to 2026-02-11 for convenience. When run
    # directly, we default to showing the interactive plot.
    default_date = os.environ.get("TARGET_DATE", "2026-02-11")
    run_single_day(default_date, show_plot=True)
