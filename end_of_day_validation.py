"""End-of-Day Validation: Compare backtest vs live trading for today.

Runs after market close. Produces:
1. Backtest CSV for today (from downloaded data)
2. Chart screenshots at each hour
3. Side-by-side comparison: backtest vs live CSV vs IB logs vs graph P/L

Usage: python end_of_day_validation.py [date]
       python end_of_day_validation.py 2026-06-08
"""
import asyncio
asyncio.set_event_loop(asyncio.new_event_loop())

import os, sys, re
import pandas as pd
import numpy as np
import pytz
import matplotlib
matplotlib.use("Agg")  # non-interactive for saving images
import matplotlib.pyplot as plt
from datetime import datetime

from TradingAlgoFast import AlgoConfig, run_trading_algo_fast
from plotFigure import plot_intraday_data

_EST = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")
_IB_LOG_DIR = os.path.join(os.path.expanduser("~"), "Desktop", "IB_Live", "logs")
_TRACKING_DIR = os.path.join(os.path.expanduser("~"), "Desktop", "IB_Live", "tracking")
_OUTPUT_DIR = os.path.join(os.path.expanduser("~"), "Desktop", "IB_Live", "validation")
os.makedirs(_OUTPUT_DIR, exist_ok=True)

# Live config (matches InteractiveBrokers.py)
LIVE_CONFIG = AlgoConfig(
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
)

HOUR_MARKS = ["10:00", "10:30", "11:00", "11:30", "12:00", "13:00", "14:00", "15:00", "16:00", "17:00"]


def get_target_date():
    if len(sys.argv) > 1:
        return sys.argv[1]
    return datetime.now(_EST).strftime("%Y-%m-%d")


def parse_ib_fills(target_date):
    """Parse IB log fills for the given date."""
    date_str = target_date.replace("-", "")
    pattern = re.compile(
        r"acctNumber='([^']+)'.*?side='(BOT|SLD)'.*?price=([\d.]+).*?orderId=(\d+).*?cumQty=([\d.]+)"
    )
    execid_pattern = re.compile(r"execId='([^']+)'")

    fills_by_exec = {}
    for fname in os.listdir(_IB_LOG_DIR):
        if date_str not in fname or not fname.endswith(".log"):
            continue
        if "DUO158495" not in fname and f"fred_ib_{date_str}" not in fname:
            continue
        fpath = os.path.join(_IB_LOG_DIR, fname)
        with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if "execDetails" not in line:
                    continue
                m = pattern.search(line)
                eid_m = execid_pattern.search(line)
                if m and eid_m:
                    acct, side, price, order_id, cum_qty = m.groups()
                    if acct != "DUO158495":
                        continue
                    exec_id = eid_m.group(1)
                    fills_by_exec[exec_id] = {
                        "side": side,
                        "price": float(price),
                        "order_id": int(order_id),
                        "cum_qty": float(cum_qty),
                    }

    # Deduplicate by orderId (keep max cumQty)
    orders = {}
    for fill in fills_by_exec.values():
        oid = fill["order_id"]
        if oid not in orders or fill["cum_qty"] > orders[oid]["cum_qty"]:
            orders[oid] = fill

    return sorted(orders.values(), key=lambda x: x["order_id"])


def parse_ib_pnl(target_date):
    """Get the last reported realizedPNL from IB logs."""
    date_str = target_date.replace("-", "")
    last_realized = 0.0
    # Use the account-specific log file directly
    for fname in sorted(os.listdir(_IB_LOG_DIR)):
        if date_str not in fname or not fname.endswith(".log"):
            continue
        if "DUO158495" not in fname:
            continue
        fpath = os.path.join(_IB_LOG_DIR, fname)
        with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if "realizedPNL=" in line:
                    m = re.search(r"realizedPNL=([-\d.]+)", line)
                    if m:
                        val = float(m.group(1))
                        if val != 0.0:
                            last_realized = val
    return last_realized


def run_backtest_for_day(target_date):
    """Run algo on today's data, return algo_df."""
    fname = os.path.join(_DATA_ROOT, f"CBOT_MINI_YM1_{target_date}.csv")
    if not os.path.exists(fname):
        print(f"  [!] No data file for {target_date}")
        return None

    df = pd.read_csv(fname, index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)

    day_start = pd.Timestamp(f"{target_date} 09:30", tz=_EST)
    day_end = pd.Timestamp(f"{target_date} 16:59", tz=_EST)
    day_data = df[(df.index >= day_start) & (df.index <= day_end)]

    if len(day_data) < 15:
        print(f"  [!] Insufficient data for {target_date}")
        return None

    algo_df = run_trading_algo_fast(day_data, target_date, "09:30", "17:00", config=LIVE_CONFIG)
    return algo_df


def save_hourly_charts(algo_df, target_date):
    """Save chart screenshots at each hour mark."""
    chart_dir = os.path.join(_OUTPUT_DIR, target_date, "charts")
    os.makedirs(chart_dir, exist_ok=True)

    day_start = pd.Timestamp(f"{target_date} 09:30", tz=_EST)

    for et in HOUR_MARKS:
        end_ts = pd.Timestamp(f"{target_date} {et}", tz=_EST)
        sliced = algo_df[(algo_df.index >= day_start) & (algo_df.index <= end_ts)]
        if len(sliced) < 5:
            continue

        try:
            fig, ax = plt.subplots(1, 1, figsize=(16, 8))
            ax.plot(sliced.index, sliced["Close"], "k-", linewidth=0.8, label="Close")
            if "purple_ray" in sliced.columns:
                ax.plot(sliced.index, sliced["purple_ray"], "purple", linewidth=1, label="Purple")
            if "blue_ray" in sliced.columns:
                ax.plot(sliced.index, sliced["blue_ray"], "blue", linewidth=1, label="Blue")
            if "orange_ray" in sliced.columns:
                ax.plot(sliced.index, sliced["orange_ray"], "orange", linewidth=1, label="Orange")
            if "yellow_ray" in sliced.columns:
                ax.plot(sliced.index, sliced["yellow_ray"], "gold", linewidth=1, label="Yellow")

            # Mark trades
            buys = sliced[sliced["signal"] == "BUY"]
            sells = sliced[sliced["signal"] == "SELL"]
            if not buys.empty:
                ax.scatter(buys.index, buys["buy_price"], marker="^", color="green", s=100, zorder=5)
            if not sells.empty:
                ax.scatter(sells.index, sells["sell_price"], marker="v", color="red", s=100, zorder=5)

            pl = sliced["session_pl"].iloc[-1]
            ax.set_title(f"Backtest {target_date} (09:30-{et}) | P/L: {pl:+.0f} pts")
            ax.legend(loc="upper left")
            ax.grid(True, alpha=0.3)

            chart_path = os.path.join(chart_dir, f"backtest_{et.replace(':', '')}.png")
            fig.savefig(chart_path, dpi=100, bbox_inches="tight")
            plt.close(fig)
        except Exception as exc:
            print(f"  [!] Chart error at {et}: {exc}")


def main():
    target_date = get_target_date()
    print(f"\n{'='*70}")
    print(f"END-OF-DAY VALIDATION: {target_date}")
    print(f"{'='*70}")

    # --- 0. Download today's data if missing ---
    print(f"\n[0] Checking/downloading data for {target_date}...")
    data_file = os.path.join(_DATA_ROOT, f"CBOT_MINI_YM1_{target_date}.csv")
    if not os.path.exists(data_file):
        print(f"  Data file not found. Downloading from IB...")
        import subprocess
        result = subprocess.run(
            [sys.executable, "download_yesterday.py", target_date],
            capture_output=True, text=True, timeout=120
        )
        if result.returncode != 0:
            print(f"  [!] Download failed: {result.stderr.strip()}")
            print(f"  Cannot proceed without data.")
            return
        print(f"  Download complete.")
    else:
        print(f"  Data file exists.")

    # --- 1. Run backtest ---
    print(f"\n[1] Running backtest for {target_date}...")
    algo_df = run_backtest_for_day(target_date)
    if algo_df is None:
        print("  Cannot proceed without data.")
        return

    # Save backtest CSV
    day_dir = os.path.join(_OUTPUT_DIR, target_date)
    os.makedirs(day_dir, exist_ok=True)
    bt_csv_path = os.path.join(day_dir, f"backtest_{target_date}.csv")
    algo_df.to_csv(bt_csv_path)
    print(f"  Backtest CSV saved: {bt_csv_path}")

    # --- 2. Save hourly charts ---
    print(f"\n[2] Saving hourly chart screenshots...")
    save_hourly_charts(algo_df, target_date)
    print(f"  Charts saved to: {os.path.join(day_dir, 'charts')}")

    # --- 3. Parse IB fills ---
    print(f"\n[3] Parsing IB log fills...")
    ib_fills = parse_ib_fills(target_date)
    ib_realized_usd = parse_ib_pnl(target_date)
    ib_realized_pts = ib_realized_usd / 0.5
    print(f"  IB fills: {len(ib_fills)}")
    for f in ib_fills:
        print(f"    {f['side']} {int(f['cum_qty'])} @ {f['price']:.0f} (orderId={f['order_id']})")
    print(f"  IB realizedPNL: ${ib_realized_usd:.2f} = {ib_realized_pts:.1f} pts")

    # --- 4. Parse live tracking CSV ---
    print(f"\n[4] Parsing live tracking CSV...")
    live_csv = None
    for fname in os.listdir(_TRACKING_DIR):
        if target_date in fname and "DUO158495" in fname and fname.endswith(".csv"):
            live_csv = pd.read_csv(os.path.join(_TRACKING_DIR, fname), index_col=0, parse_dates=True)
            break

    if live_csv is not None:
        live_trades = live_csv[live_csv["signal"].isin(["BUY", "SELL"])]
        live_pl = live_csv["ib_pl"].iloc[-1] if "ib_pl" in live_csv.columns else None
        print(f"  Live CSV trades: {len(live_trades)}")
        for ts, row in live_trades.iterrows():
            fp = row.get("fill_price", None)
            price = fp if pd.notna(fp) else (row["buy_price"] if row["signal"] == "BUY" else row["sell_price"])
            print(f"    {ts.strftime('%H:%M')} {row['signal']} @ {price:.0f}")
        print(f"  Live CSV ib_pl: {live_pl:.1f} pts" if live_pl else "  Live CSV ib_pl: N/A")
    else:
        live_pl = None
        print("  [!] No live tracking CSV found")

    # --- 5. Backtest P/L at each hour ---
    print(f"\n[5] Backtest P/L at each hour mark...")
    day_start = pd.Timestamp(f"{target_date} 09:30", tz=_EST)
    for et in HOUR_MARKS:
        end_ts = pd.Timestamp(f"{target_date} {et}", tz=_EST)
        sliced = algo_df[(algo_df.index >= day_start) & (algo_df.index <= end_ts)]
        if len(sliced) >= 2:
            pl = sliced["session_pl"].iloc[-1]
            print(f"    {et}: {pl:+.1f} pts")

    # --- 6. Backtest trades ---
    print(f"\n[6] Backtest trades...")
    bt_trades = algo_df[algo_df["signal"].isin(["BUY", "SELL"])]
    for ts, row in bt_trades.iterrows():
        sig = row["signal"]
        price = row["buy_price"] if sig == "BUY" else row["sell_price"]
        liq = " (liq)" if row.get("is_liquidation", False) else ""
        print(f"    {ts.strftime('%H:%M')} {sig} @ {price:.0f}{liq}")
    bt_final_pl = algo_df["session_pl"].iloc[-1]
    print(f"  Backtest final P/L: {bt_final_pl:+.1f} pts")

    # --- 7. COMPARISON ---
    print(f"\n{'='*70}")
    print(f"COMPARISON SUMMARY")
    print(f"{'='*70}")
    print(f"{'Source':<25}{'P/L (pts)':<15}{'Trades':<10}")
    print(f"{'-'*50}")
    print(f"{'Backtest (session_pl)':<25}{bt_final_pl:<+15.1f}{len(bt_trades):<10}")
    if live_pl is not None:
        print(f"{'Live CSV (ib_pl)':<25}{live_pl:<+15.1f}{len(live_trades):<10}")
    print(f"{'IB Log (realized)':<25}{ib_realized_pts:<+15.1f}{len(ib_fills):<10}")
    print(f"{'Graph (ib_total/0.5)':<25}{ib_realized_pts:<+15.1f}{'(same as IB)':<10}")

    # Flag mismatches
    print(f"\n--- MATCH CHECK ---")
    sources = {"Backtest": bt_final_pl, "IB Log": ib_realized_pts}
    if live_pl is not None:
        sources["Live CSV"] = live_pl

    values = list(sources.values())
    if max(values) - min(values) < 5:
        print(f"  ✓ All sources within 5 pts — MATCH")
    else:
        print(f"  ✗ MISMATCH detected:")
        for name, val in sources.items():
            print(f"    {name}: {val:+.1f}")
        print(f"    Gap: {max(values) - min(values):.1f} pts")
        print(f"    Note: Backtest uses instant fills; IB has cushion + commissions")

    # Save comparison report
    report_path = os.path.join(day_dir, f"validation_report_{target_date}.txt")
    with open(report_path, "w") as f:
        f.write(f"End-of-Day Validation Report: {target_date}\n")
        f.write(f"{'='*50}\n\n")
        f.write(f"Backtest P/L: {bt_final_pl:+.1f} pts ({len(bt_trades)} trades)\n")
        if live_pl is not None:
            f.write(f"Live CSV P/L: {live_pl:+.1f} pts ({len(live_trades)} trades)\n")
        f.write(f"IB Log P/L:   {ib_realized_pts:+.1f} pts ({len(ib_fills)} fills)\n")
        f.write(f"\nIB Fills:\n")
        for fill in ib_fills:
            f.write(f"  {fill['side']} {int(fill['cum_qty'])} @ {fill['price']:.0f}\n")
        f.write(f"\nBacktest Trades:\n")
        for ts, row in bt_trades.iterrows():
            sig = row["signal"]
            price = row["buy_price"] if sig == "BUY" else row["sell_price"]
            f.write(f"  {ts.strftime('%H:%M')} {sig} @ {price:.0f}\n")
    print(f"\n  Report saved: {report_path}")
    print(f"  Output dir: {day_dir}")


if __name__ == "__main__":
    main()
