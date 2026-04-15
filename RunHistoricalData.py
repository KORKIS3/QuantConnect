"""RunHistoricalData.py

Fetch historical YM data from IB, run the trading algo, save a chart image,
save a CSV, and open the interactive chart for click-through review.

Usage:
    python RunHistoricalData.py --start "2026-04-07 09:30" --end "2026-04-07 10:30"
    python RunHistoricalData.py --start "2026-04-07 18:00" --end "2026-04-07 19:00"

All times are Eastern. Bar size is automatically chosen:
    - 1-minute bars during 09:30-10:30 ET
    - 5-minute bars outside that window
"""

import argparse
import os
import pandas as pd
import pytz
import matplotlib
matplotlib.use("TkAgg")

from ib_insync import IB, Future
from TradingAlgo import run_trading_algo, AlgoConfig
from Plotter import plot_results

_EST = pytz.timezone("US/Eastern")
_IB_LIVE_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "IB_Live")


def fetch_ib_data(start: pd.Timestamp, end: pd.Timestamp, port: int = 4002) -> pd.DataFrame:
    """Fetch 1-minute bars from IB for the given EST window and return as DataFrame."""
    ib = IB()
    ib.connect("127.0.0.1", port, clientId=20)
    print(f"Connected to IB at port {port}")

    # Find the correct front-month contract for the requested date.
    base = Future(symbol="YM", exchange="CBOT", currency="USD", includeExpired=True)
    all_details = ib.reqContractDetails(base)
    all_contracts = sorted(
        [d.contract for d in all_details],
        key=lambda c: c.lastTradeDateOrContractMonth
    )
    date_str = start.strftime("%Y%m%d")
    contract = next(
        (c for c in all_contracts if c.lastTradeDateOrContractMonth >= date_str),
        all_contracts[-1]
    )
    print(f"Contract: {contract.localSymbol}  expiry={contract.lastTradeDateOrContractMonth}")

    # Request enough history to cover the window — use UTC end time.
    duration_secs = int((end - start).total_seconds()) + 600  # add 10 min buffer
    end_utc = end.astimezone(pytz.utc).strftime("%Y%m%d-%H:%M:%S")

    bars = ib.reqHistoricalData(
        contract,
        endDateTime=end_utc,
        durationStr=f"{duration_secs} S",
        barSizeSetting="1 min",
        whatToShow="TRADES",
        useRTH=False,
        formatDate=1,
    )
    ib.disconnect()
    print(f"Fetched {len(bars)} bars from IB")

    if not bars:
        raise ValueError("No data returned from IB for the requested window.")

    df = pd.DataFrame([{
        "time": b.date, "Open": b.open, "High": b.high,
        "Low": b.low, "Close": b.close, "Volume": b.volume
    } for b in bars]).set_index("time")

    df.index = pd.to_datetime(df.index)
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC").tz_convert(_EST)
    else:
        df.index = df.index.tz_convert(_EST)

    # Filter to requested window.
    df = df[(df.index >= start) & (df.index <= end)]
    print(f"Filtered to {len(df)} bars in window {start.strftime('%H:%M')} - {end.strftime('%H:%M')} ET")
    return df


def resample_mixed(df: pd.DataFrame, target_date: str) -> pd.DataFrame:
    """Resample to 1-min inside 09:30-10:30, 5-min outside."""
    core_start = pd.Timestamp(f"{target_date} 09:30:00", tz=_EST)
    core_end   = pd.Timestamp(f"{target_date} 10:30:00", tz=_EST)

    def _agg(d, freq):
        return d.resample(freq).agg(
            Open=("Open", "first"), High=("High", "max"),
            Low=("Low", "min"), Close=("Close", "last"),
            Volume=("Volume", "sum"),
        ).dropna(subset=["Open"])

    df_core    = df[(df.index >= core_start) & (df.index <= core_end)]
    df_outside = df[(df.index < core_start) | (df.index > core_end)]

    parts = []
    if not df_outside.empty:
        parts.append(_agg(df_outside, "5min"))
    if not df_core.empty:
        parts.append(_agg(df_core, "1min"))

    if not parts:
        return pd.DataFrame()
    return pd.concat(parts).sort_index()


def run(start_str: str, end_str: str, port: int = 4002) -> None:
    # Parse input times as EST.
    start = pd.Timestamp(start_str).tz_localize(_EST) if pd.Timestamp(start_str).tzinfo is None else pd.Timestamp(start_str).tz_convert(_EST)
    end   = pd.Timestamp(end_str).tz_localize(_EST)   if pd.Timestamp(end_str).tzinfo is None   else pd.Timestamp(end_str).tz_convert(_EST)
    target_date = start.strftime("%Y-%m-%d")
    start_time  = start.strftime("%H:%M")
    end_time    = end.strftime("%H:%M")

    print(f"\nFetching {target_date}  {start_time} – {end_time} ET")

    # 1. Fetch from IB.
    raw_df = fetch_ib_data(start, end, port=port)

    # 2. Resample to mixed 1-min / 5-min bars.
    minute_df = resample_mixed(raw_df, target_date)
    print(f"Resampled to {len(minute_df)} bars")
    print(minute_df[["Open","High","Low","Close"]].to_string())

    # 3. Run trading algo.
    config = AlgoConfig(warmup_minutes=12, steep_angle_threshold=70.0, proximity_points=15.0, min_reversal_minutes=10)
    algo_df = run_trading_algo(minute_df, target_date, start_time, end_time, config=config)

    # 4. Print signals and P/L.
    contracts, multiplier = 100, 5
    final_pl = float(algo_df["pl"].iloc[-1])
    print(f"\n=== {target_date}  {start_time} – {end_time} ===\n")
    signals = algo_df[algo_df["signal"].isin(["BUY","SELL"])]
    for ts, row in signals.iterrows():
        sig   = row["signal"]
        price = row["buy_price"] if sig == "BUY" else row["sell_price"]
        pl    = row["pl"]
        print(f"  {ts.strftime('%H:%M')}  {sig:4s}  @ {int(price)}   P/L: {pl:+.0f} pts  /  ${pl*contracts*multiplier:+,.0f}")
    print(f"\nFinal P/L:  {final_pl:+.0f} points  /  ${final_pl*contracts*multiplier:+,.0f}  (100 contracts)")

    # 5. Save CSV.
    os.makedirs(os.path.join(_IB_LIVE_ROOT, "historical"), exist_ok=True)
    csv_path = os.path.join(_IB_LIVE_ROOT, "historical", f"YM_{target_date}_{start_time.replace(':','')}_{end_time.replace(':','')}.csv")
    algo_df.to_csv(csv_path)
    print(f"\nCSV saved: {csv_path}")

    # 6. Save chart image (headless).
    import matplotlib.pyplot as plt
    from plotFigure import ChartPlotter
    matplotlib.use("Agg")
    img_path = csv_path.replace(".csv", ".jpg")
    plotter = ChartPlotter(algo_df, target_date, start_time, end_time, output_dir="", batch_mode=True)
    plotter.create_figure()
    plotter.update_plot(len(algo_df) - 1)
    plotter.fig.savefig(img_path, dpi=150, bbox_inches="tight")
    plt.close(plotter.fig)
    print(f"Chart saved: {img_path}")

    # 7. Open interactive chart for click-through review.
    matplotlib.use("TkAgg")
    plot_results(algo_df, target_date, start_time, end_time)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Fetch IB historical data and run trading algo.")
    p.add_argument("--start", required=True, help="Start datetime ET e.g. '2026-04-07 09:30'")
    p.add_argument("--end",   required=True, help="End datetime ET   e.g. '2026-04-07 10:30'")
    p.add_argument("--port",  type=int, default=4002, help="IB Gateway port (default: 4002)")
    args = p.parse_args()
    run(args.start, args.end, args.port)
