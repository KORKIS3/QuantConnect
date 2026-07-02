"""
generate_hourly_snapshots.py

Regenerates the hourly Algo View / IB View chart JPEGs for today, the same
images that InteractiveBrokers.py normally saves live on each hour mark
during a trading session.

- Algo View: today's price CSV run through the algo (TradingAlgoFast).
- IB View: today's IB logs (fred_ib_*.log), parsed for actual fills,
  overlaid on the same price data.

Output: ~/Desktop/charts/YM_<date>_<HHMM>_algo_snapshot.jpg
        ~/Desktop/charts/YM_<date>_<HHMM>_ib_snapshot.jpg

Usage:
    python generate_hourly_snapshots.py                # today, hours 9-16
    python generate_hourly_snapshots.py 2026-07-01      # specific date
"""

import os
import re
import sys
from collections import defaultdict

import numpy as np
import pandas as pd
import pytz

from TradingAlgoFast import AlgoConfig, run_trading_algo_fast
from plotFigure import ChartPlotter

_EST = pytz.timezone("US/Eastern")

_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")
_LOG_DIR = os.path.join(os.path.expanduser("~"), "Desktop", "IB_Live", "logs")
_OUT_DIR = os.path.join(os.path.expanduser("~"), "Desktop", "charts")

# Same live defaults as InteractiveBrokers.py
_CONFIG = AlgoConfig(
    warmup_minutes=7,
    steep_angle_threshold=90.0,
    proximity_points=4.0,
    min_reversal_minutes=0,
    min_entry_angle=0.0,
    partial_tp_pts=50.0,
    spike_profit_pts=100.0,
    spike_profit_bars=9,
    wm_shield_distance=0.0,
    swing_anchor_threshold=10.0,
    num_contracts=2,
    cushion_points=0.0,
    limit_expiry_bars=5,
)

HOURS = [9, 10, 11, 12, 13, 14, 15, 16]

_EXEC_RE = re.compile(
    r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*execDetails Execution\("
    r".*side='(BOT|SLD)'.*price=([\d.]+).*orderId=(\d+).*cumQty=([\d.]+)"
)


def load_price_data(target_date: str) -> pd.DataFrame:
    csv_path = os.path.join(_DATA_ROOT, f"CBOT_MINI_YM1_{target_date}.csv")
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"No price CSV found: {csv_path}")
    df = pd.read_csv(csv_path, index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
    return df


def parse_ib_fills(target_date: str) -> list:
    """Parse today's IB logs into a list of fill events, same logic as
    InteractiveBrokers.IBDataBridge._seed_events_from_logs but standalone
    (all accounts' logs are merged since we just want the fills)."""
    date_compact = target_date.replace("-", "")
    if not os.path.isdir(_LOG_DIR):
        return []

    log_files = sorted(
        os.path.join(_LOG_DIR, f)
        for f in os.listdir(_LOG_DIR)
        if f.startswith(f"fred_ib_{date_compact}") or f"_{date_compact}_" in f
        if f.endswith(".log")
    )
    if not log_files:
        return []

    fills_by_order = {}
    for log_file in log_files:
        try:
            with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    m = _EXEC_RE.search(line)
                    if not m:
                        continue
                    time_str, side, price, order_id, cum_qty = m.groups()
                    cum_qty_f = float(cum_qty)
                    if order_id not in fills_by_order or cum_qty_f > fills_by_order[order_id]["qty"]:
                        fills_by_order[order_id] = {
                            "time_str": time_str,
                            "side": side,
                            "price": float(price),
                            "qty": cum_qty_f,
                        }
        except Exception as exc:
            print(f"  [!] Error reading {log_file}: {exc}")

    sorted_fills = sorted(fills_by_order.values(), key=lambda x: x["time_str"])

    events = []
    pos = 0
    for fill in sorted_fills:
        fill_time = pd.Timestamp(fill["time_str"], tz=_EST)
        signal = "BUY" if fill["side"] == "BOT" else "SELL"
        qty = int(fill["qty"])

        is_liquidation = False
        if signal == "BUY" and pos <= 0:
            if pos < 0:
                is_liquidation = (pos + qty) == 0
            pos = pos + qty
        elif signal == "SELL" and pos >= 0:
            if pos > 0:
                is_liquidation = (pos - qty) == 0
            pos = pos - qty
        else:
            pos = pos + qty if signal == "BUY" else pos - qty

        events.append({
            "time": fill_time,
            "signal": signal,
            "fill_price": fill["price"],
            "qty": qty,
            "is_partial_tp": False,
            "is_liquidation": is_liquidation,
        })
    return events


def build_ib_view_df(algo_df: pd.DataFrame, fill_events: list) -> pd.DataFrame:
    """Overlay actual IB fills onto the algo dataframe's OHLC data,
    same logic as InteractiveBrokers._build_ib_view_df."""
    df = algo_df.copy()
    df["signal"] = ""
    df["buy_price"] = np.nan
    df["sell_price"] = np.nan
    df["partial_tp"] = False
    df["position"] = "flat"
    df["pl"] = 0.0
    if "session_pl" in df.columns:
        df["session_pl"] = 0.0

    fill_map = defaultdict(list)
    for ev in fill_events:
        bar_time = ev["time"].floor("min")
        fill_map[bar_time].append(ev)

    ib_position = 0
    entry_price = 0.0
    realized_pl = 0.0

    for idx in df.index:
        for ev in fill_map.get(idx, []):
            side = ev["signal"]
            price = float(ev["fill_price"])
            qty = ev["qty"]

            if side == "BUY":
                df.at[idx, "signal"] = "BUY"
                df.at[idx, "buy_price"] = price
                if ib_position < 0:
                    close_qty = min(qty, abs(ib_position))
                    realized_pl += (entry_price - price) * close_qty
                    ib_position += qty
                    if ib_position > 0:
                        entry_price = price
                    elif ib_position == 0:
                        entry_price = 0.0
                elif ib_position == 0:
                    ib_position = qty
                    entry_price = price
                else:
                    ib_position += qty
            else:  # SELL
                df.at[idx, "signal"] = "SELL"
                df.at[idx, "sell_price"] = price
                if ib_position > 0:
                    close_qty = min(qty, ib_position)
                    realized_pl += (price - entry_price) * close_qty
                    ib_position -= qty
                    if ib_position < 0:
                        entry_price = price
                    elif ib_position == 0:
                        entry_price = 0.0
                elif ib_position == 0:
                    ib_position = -qty
                    entry_price = price
                else:
                    ib_position -= qty

        if ib_position > 0:
            df.at[idx, "position"] = "long"
        elif ib_position < 0:
            df.at[idx, "position"] = "short"
        else:
            df.at[idx, "position"] = "flat"

        close = df.at[idx, "Close"]
        unrealized = 0.0
        if ib_position > 0:
            unrealized = (close - entry_price) * ib_position
        elif ib_position < 0:
            unrealized = (entry_price - close) * abs(ib_position)
        df.at[idx, "pl"] = realized_pl + unrealized
        if "session_pl" in df.columns:
            df.at[idx, "session_pl"] = realized_pl + unrealized

    return df


def save_chart(df: pd.DataFrame, target_date: str, end_time: str, out_path: str,
               window_minutes: int = 90) -> None:
    # Fixed window ending at end_time. Default is a 90-minute rolling
    # window (HH:00 -> (HH-1):30 to HH:00). Pass a larger window_minutes
    # (e.g. 600) to get a full-day chart. Clipped to the first available
    # bar so the axis doesn't extend past the session open.
    x_end = pd.Timestamp(f"{target_date} {end_time}", tz=df.index.tz)
    x_start = max(x_end - pd.Timedelta(minutes=window_minutes), df.index[0])
    window_start_time = x_start.strftime("%H:%M")

    plotter = ChartPlotter(df, target_date, window_start_time, end_time, output_dir="", batch_mode=True)
    # Strip per-bar labels + legend so the resulting image is
    # OCR-friendly (only BUY/SELL/TP boxes and the price line remain).
    plotter.markers_only = True
    plotter.create_figure()
    plotter.ax.set_xlim(x_start, x_end)
    if plotter.ax_top is not None:
        plotter.ax_top.set_xlim(x_start, x_end)

    plotter.update_plot(len(df) - 1)

    # Center Y-axis around the visible window's price range (not full session)
    window_df = df[(df.index >= x_start) & (df.index <= x_end)]
    if not window_df.empty:
        current_price = float(window_df["Close"].iloc[-1])
        padding = 100.0
        y_lo = current_price - padding
        y_hi = current_price + padding
        # Expand to include rays and recent highs/lows within the window
        ray_cols = ["purple_ray", "blue_ray", "orange_ray", "yellow_ray"]
        for col in ray_cols:
            if col in window_df.columns:
                vals = window_df[col].dropna()
                if not vals.empty:
                    y_lo = min(y_lo, float(vals.min()) - 20)
                    y_hi = max(y_hi, float(vals.max()) + 20)
        if "High" in window_df.columns:
            y_hi = max(y_hi, float(window_df["High"].max()) + 10)
        if "Low" in window_df.columns:
            y_lo = min(y_lo, float(window_df["Low"].min()) - 10)
        plotter.ax.set_ylim(y_lo, y_hi)

    # dpi=300 doubles the pixel dimensions vs. the previous dpi=150,
    # yielding ~4372x2588 images so the on-chart text (BUY/SELL/TP box
    # labels, prices, timestamps) OCRs cleanly.
    plotter.fig.savefig(out_path, dpi=300, bbox_inches="tight")
    import matplotlib.pyplot as plt
    plt.close(plotter.fig)


def main():
    target_date = sys.argv[1] if len(sys.argv) > 1 else pd.Timestamp.now(tz=_EST).strftime("%Y-%m-%d")
    print(f"Generating hourly snapshots for {target_date} ...")

    price_df = load_price_data(target_date)
    fill_events = parse_ib_fills(target_date)
    print(f"  Parsed {len(fill_events)} IB fill(s) from logs.")

    os.makedirs(_OUT_DIR, exist_ok=True)

    day_start = pd.Timestamp(f"{target_date} 09:30", tz=_EST)

    last_bar_ts = price_df.index.max()

    for hour in HOURS:
        end_time = f"{hour:02d}:00"
        end_ts = pd.Timestamp(f"{target_date} {end_time}", tz=_EST)
        if end_ts > last_bar_ts:
            print(f"  [{end_time}] no data yet (data ends {last_bar_ts.strftime('%H:%M')}), skipping")
            continue
        sliced = price_df[(price_df.index >= day_start) & (price_df.index <= end_ts)]
        if len(sliced) < 5:
            print(f"  [{end_time}] not enough data, skipping")
            continue

        try:
            algo_df = run_trading_algo_fast(sliced, target_date, "09:30", end_time, config=_CONFIG)
        except Exception as exc:
            print(f"  [{end_time}] algo error: {exc}")
            continue

        algo_path = os.path.join(_OUT_DIR, f"YM_{target_date}_{hour:02d}00_algo_snapshot.jpg")
        try:
            save_chart(algo_df, target_date, end_time, algo_path)
            print(f"  [{end_time}] saved {algo_path}")
        except Exception as exc:
            print(f"  [{end_time}] algo chart error: {exc}")

        if fill_events:
            try:
                ib_df = build_ib_view_df(algo_df, fill_events)
                ib_path = os.path.join(_OUT_DIR, f"YM_{target_date}_{hour:02d}00_ib_snapshot.jpg")
                save_chart(ib_df, target_date, end_time, ib_path)
                print(f"  [{end_time}] saved {ib_path}")
            except Exception as exc:
                print(f"  [{end_time}] IB chart error: {exc}")

    print("Done.")


if __name__ == "__main__":
    main()
