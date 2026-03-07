"""
Process ScottDataTry2_3_5 - CBOT_MINI_YM1!, 30.csv
Run a RunFullDataSet-style pass for each individual day
Time window: 09:30 - 10:00 (30-minute bars)
"""
import os
import datetime

import pandas as pd
import pytz

from plotFigure import ChartPlotter
from RunFullDataSet import _compute_trade_stats

# Paths
home = os.path.expanduser("~")
desktop = os.path.join(home, "Desktop")
input_csv = os.path.join(desktop, "ScottDataTry2_3_5 - CBOT_MINI_YM1!, 30.csv")
charts_dir = os.path.join(desktop, "TradingPics_Scott_930-1000_all_days")
output_tmp = os.path.join(desktop, "Trading", "Temp")

start_time_str = "09:30"
end_time_str = "10:00"

print("=" * 60)
print("RunFullDataSet on Scott 30-min data (per day)")
print("=" * 60)
print(f"Input:  {input_csv}")
print(f"Window: {start_time_str}-{end_time_str} (30-min bars)")

# Load CSV
if not os.path.exists(input_csv):
    print("ERROR: Input CSV not found.")
    raise SystemExit(1)

df = pd.read_csv(input_csv)
if "time" not in df.columns:
    print("ERROR: Column 'time' not found in CSV.")
    raise SystemExit(1)

# Parse time column as index
df["time"] = pd.to_datetime(df["time"])
df = df.set_index("time")

# Rename to standard OHLC columns
df = df.rename(columns={
    "open": "Open",
    "high": "High",
    "low": "Low",
    "close": "Close",
})

# Keep only price columns we use
df = df[["Open", "High", "Low", "Close"]].copy()

# Ensure EST timezone
est = pytz.timezone("US/Eastern")
if df.index.tz is None:
    df.index = df.index.tz_localize(est)
else:
    df.index = df.index.tz_convert(est)

print(f"Rows: {len(df)}")
print(f"Date range: {df.index[0].date()} to {df.index[-1].date()}")

# Add simple date column for grouping
df["date"] = df.index.date
dates = sorted(df["date"].unique())
print(f"Trading days found: {len(dates)}")

os.makedirs(charts_dir, exist_ok=True)
os.makedirs(output_tmp, exist_ok=True)

results = []

print("\n" + "=" * 60)
print("Processing each day (Scott 30-min data)")
print("=" * 60)

for i, day in enumerate(dates, 1):
    day_str = day.strftime("%Y-%m-%d")
    print(f"\n[{i}/{len(dates)}] {day_str}")

    day_df = df[df["date"] == day].copy()
    day_df = day_df.drop(columns=["date"])
    if day_df.empty:
        print("  Skipped: no data for this day")
        continue

    # Window: include the 09:30 bar only (30m bar covering 09:30-10:00)
    # Use >= 09:30 and < 10:00 so we do not accidentally include the 10:00-10:30 bar.
    win_start = datetime.time(9, 30)
    win_end_excl = datetime.time(10, 0)
    day_win = day_df[(day_df.index.time >= win_start) & (day_df.index.time < win_end_excl)]

    if day_win.empty:
        print("  Skipped: no 09:30 bar for this day")
        continue

    print(f"  Bars in window: {len(day_win)}")
    print(f"  Time(s): {[ts.strftime('%H:%M') for ts in day_win.index]}")

    # ChartPlotter expects High/Low/Close; we can drop Open
    hlc = day_win[["High", "Low", "Close"]].copy()

    try:
        plotter = ChartPlotter(hlc, day_str, start_time_str, end_time_str, output_tmp)
        plotter.create_figure()
        plotter.detect_all_signals_once()

        # Save chart
        img_name = f"{day_str}_Scott_930-1000.jpg"
        img_path = os.path.join(charts_dir, img_name)
        if getattr(plotter, "fig", None) is not None:
            final_frame = max(0, len(hlc) - 1)
            plotter.state.current_frame = final_frame
            plotter.update_plot(final_frame)
            try:
                plotter.fig.canvas.draw()
                plotter.fig.canvas.flush_events()
            except Exception:
                pass
            plotter.fig.savefig(img_path, dpi=150, bbox_inches="tight")
            print(f"  Saved chart: {img_name}")

            import matplotlib.pyplot as plt
            plt.close(plotter.fig)

        stats = _compute_trade_stats(plotter)
        buy_count = len(plotter.state.detected_buy_signals)
        sell_count = len(plotter.state.detected_sell_signals)

        print(f"  Signals: {buy_count} BUY, {sell_count} SELL")
        print(f"  Trades: {stats['total_trades']} ({stats['winning_trades']}W/{stats['losing_trades']}L)")
        print(f"  Final P/L: {stats['final_pl']:.2f} pts (High: {stats['pl_high']:.2f} pts)")

        results.append({
            "Date": day_str,
            "Bars": len(hlc),
            "Buy_Signals": buy_count,
            "Sell_Signals": sell_count,
            "Total_Trades": stats["total_trades"],
            "Winning_Trades": stats["winning_trades"],
            "Losing_Trades": stats["losing_trades"],
            "Win_Pct": stats["win_pct"],
            "Final_PL": stats["final_pl"],
            "PL_High": stats["pl_high"],
            "Captured_100": stats["captured_100"],
            "Liquidation_PL": stats.get("liquidation_trade_pl", 0) or 0,
        })
    except Exception as e:
        print(f"  Error processing {day_str}: {e}")
        import traceback
        traceback.print_exc()

print("\n" + "=" * 60)
print("Summary over all days")
print("=" * 60)

if not results:
    print("No days were processed.")
else:
    res_df = pd.DataFrame(results)
    total_days = len(res_df)
    total_pl = float(res_df["Final_PL"].sum())
    avg_pl = total_pl / total_days if total_days else 0.0
    total_liq = float(res_df["Liquidation_PL"].sum())
    avg_liq = total_liq / total_days if total_days else 0.0
    captured_days = int((res_df["Captured_100"] == "Yes").sum())

    print(f"Days processed: {total_days}")
    print(f"Total P/L: {total_pl:.2f} pts")
    print(f"Average P/L per day: {avg_pl:.2f} pts")
    print(f"Total liquidation P/L: {total_liq:.2f} pts")
    print(f"Average liquidation P/L per day: {avg_liq:.2f} pts")
    print(f"Days capturing 100+ pts: {captured_days}/{total_days}")

    # Save summary CSV on desktop
    summary_csv = os.path.join(desktop, "Scott_930-1000_all_days_Summary.csv")
    res_df.to_csv(summary_csv, index=False)
    print(f"\nSummary CSV saved: {summary_csv}")
    print(f"Charts saved under: {charts_dir}")

print("=" * 60)
