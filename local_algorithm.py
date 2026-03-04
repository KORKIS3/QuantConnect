#!/usr/bin/env python3
"""
local_algorithm.py

Runnable wrapper so you can run the existing dataset/setup locally
without QuantConnect. It reuses the CSV loading, plotting, and
trade-stats helpers from `RunFullDataSet.py`.

Usage:
    python local_algorithm.py --folder /path/to/csvs --start 09:30 --end 10:00
"""
from __future__ import annotations

import argparse
import glob
import os
from typing import List

import pandas as pd

try:
    from RunFullDataSet import _load_csv_as_df, _compute_trade_stats
except Exception:
    # If running as a module from different cwd, try relative import
    from .RunFullDataSet import _load_csv_as_df, _compute_trade_stats  # type: ignore

from plotFigure import ChartPlotter


def process_folder(folder: str, start_time: str = "09:30", end_time: str = "10:00", output_image_dir: str | None = None) -> pd.DataFrame:
    """Process all CSV files in `folder`, create plot images, and return a results DataFrame.

    This reuses the project's `ChartPlotter` and the helpers in `RunFullDataSet.py` so
    behavior stays identical to the existing desktop runner.
    """
    pattern = os.path.join(folder, "*.csv")
    files = sorted(glob.glob(pattern))
    if not files:
        raise FileNotFoundError(f"No CSV files found in: {folder}")

    results = []
    output_dir = output_image_dir or os.path.join(os.path.expanduser('~'), 'Desktop', 'Trading', 'Temp')
    os.makedirs(output_dir, exist_ok=True)

    for fp in files:
        fname = os.path.basename(fp)
        print('\n' + '='*60)
        print(f"Processing file: {fname}")

        try:
            df = _load_csv_as_df(fp)
        except Exception as e:
            print(f"Failed to load {fp}: {e}")
            continue

        # Quick window check from original script
        try:
            times = df.index.time
            has_start = any(t.strftime('%H:%M') == start_time for t in times)
            has_end = any(t.strftime('%H:%M') == end_time for t in times)
            if not (has_start or has_end):
                print(f"Skipping {fname}: does not contain {start_time}–{end_time} timestamps")
                continue
        except Exception:
            print(f"Skipping {fname}: could not verify timestamps")
            continue

        # Infer target_date from filename or first timestamp (keeps same logic as RunFullDataSet)
        import re, calendar

        target_date = ''
        m = re.search(r"(\d{4}-\d{2}-\d{2})", fname)
        if m:
            target_date = m.group(1)
        else:
            m2 = re.search(r"(\d{8})", fname)
            if m2:
                s = m2.group(1)
                target_date = f"{s[0:4]}-{s[4:6]}-{s[6:8]}"

        m3 = re.search(r"(?i)\b(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*[\s_\-]*(\d{1,2})\b", fname)
        if m3:
            month_str = m3.group(1)
            day = int(m3.group(2))
            try:
                month_num = list(calendar.month_abbr).index(month_str[:3].title())
                year = 2026
                target_date = f"{year:04d}-{month_num:02d}-{day:02d}"
            except Exception:
                pass

        if not target_date:
            try:
                target_date = df.index[0].strftime('%Y-%m-%d')
            except Exception:
                target_date = ''

        # Ensure we have numeric high/low data
        if 'High' not in df.columns or 'Low' not in df.columns:
            print(f"Skipping {fname}: missing High/Low columns after mapping")
            continue
        if df['High'].dropna().empty or df['Low'].dropna().empty:
            print(f"Skipping {fname}: High/Low columns contain no numeric data")
            continue

        plotter = ChartPlotter(df, target_date, start_time, end_time, output_dir)
        try:
            plotter.create_figure()
        except Exception:
            pass
        plotter.detect_all_signals_once()

        # Save figure similarly to RunFullDataSet
        try:
            image_dir = os.path.join(os.path.expanduser('~'), 'Desktop', 'TradingPics')
            os.makedirs(image_dir, exist_ok=True)
            base_name = target_date or re.sub(r'[^A-Za-z0-9_.-]', '_', os.path.splitext(fname)[0])
            img_name = f"{base_name}.jpg"
            img_path = os.path.join(image_dir, img_name)
            suffix = 1
            while os.path.exists(img_path):
                img_name = f"{base_name}_{suffix}.jpg"
                img_path = os.path.join(image_dir, img_name)
                suffix += 1

            if hasattr(plotter, 'fig') and getattr(plotter, 'fig') is not None:
                try:
                    final_frame = max(0, len(getattr(plotter, 'data', [])) - 1)
                    plotter.state.current_frame = final_frame
                    plotter.update_plot(final_frame)
                    try:
                        plotter.fig.canvas.draw()
                        plotter.fig.canvas.flush_events()
                    except Exception:
                        pass
                    plotter.fig.savefig(img_path, dpi=150, bbox_inches='tight')
                    print(f"Saved plot image: {img_path}")
                except Exception as e:
                    print(f"Failed to save plot image for {fname}: {e}")
        except Exception as e:
            print('Failed to prepare image directory:', e)

        try:
            import matplotlib.pyplot as _plt
            _plt.close(plotter.fig)
        except Exception:
            pass

        stats = _compute_trade_stats(plotter)

        results.append({
            'FileName': fname,
            'Date': target_date,
            'final_P/L': stats['final_pl'],
            'winning_trades': stats['winning_trades'],
            'losing_trades': stats['losing_trades'],
            'win_pct': stats['win_pct'],
            'Captured 100 points': stats.get('captured_100', 'No'),
            'p/l high': stats.get('pl_high', 0.0),
            'p/l when liquidated': stats.get('liquidation_pl', None),
            'p/l liquidation trade': stats.get('liquidation_trade_pl', None),
        })

    df_res = pd.DataFrame(results)
    return df_res


def _cli():
    p = argparse.ArgumentParser(prog='local_algorithm', description='Run local algorithm/plots on CSV folder')
    p.add_argument('--folder', '-f', required=True, help='Folder containing CSV files to process')
    p.add_argument('--start', default='09:30', help='Start time to check for (HH:MM)')
    p.add_argument('--end', default='10:00', help='End time to check for (HH:MM)')
    p.add_argument('--out', default=None, help='Optional output image dir')
    args = p.parse_args()

    df = process_folder(args.folder, args.start, args.end, args.out)
    # write results summary to desktop as CSV
    out_csv = os.path.join(os.path.expanduser('~'), 'Desktop', 'local_algorithm_results.csv')
    df.to_csv(out_csv, index=False)
    print(f"Wrote results: {out_csv}")


if __name__ == '__main__':
    _cli()
