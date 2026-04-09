"""AnalyseTrades.py

Tests the theory: if price closes back across the entry ray after entering a trade,
does that trade end up a loser?

Usage:
    python AnalyseTrades.py                          # analyses all CSVs in IB_Live/tracking
    python AnalyseTrades.py --csv path/to/file.csv   # single file
"""

import argparse
import os
import pandas as pd
import pytz

_EST = pytz.timezone("US/Eastern")
_TRACKING_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "IB_Live", "tracking")


def analyse_file(csv_path: str) -> pd.DataFrame:
    """Analyse one tracking CSV and return a per-trade summary."""
    df = pd.read_csv(csv_path, index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index)
    if df.index.tz is None:
        df.index = df.index.tz_localize(_EST)
    else:
        df.index = df.index.tz_convert(_EST)

    signals = df[df["signal"].isin(["BUY", "SELL"])].copy()
    if signals.empty:
        return pd.DataFrame()

    results = []

    for idx, (entry_ts, entry_row) in enumerate(signals.iterrows()):
        sig = entry_row["signal"]

        # Find the next signal (exit point).
        if idx + 1 < len(signals):
            exit_ts  = signals.index[idx + 1]
            exit_row = signals.iloc[idx + 1]
            exit_pl  = float(exit_row["pl"])
        else:
            # Last signal — use last bar as exit.
            exit_ts  = df.index[-1]
            exit_row = df.iloc[-1]
            exit_pl  = float(exit_row["pl"])

        entry_pl = float(entry_row["pl"])
        trade_pl = exit_pl - entry_pl

        # Determine which ray triggered entry and its value at entry.
        if sig == "BUY":
            entry_price = float(entry_row.get("buy_price", entry_row["Close"]))
            # BUY triggered by orange or purple ray crossing upward.
            # Use whichever ray is closest to entry price from below.
            orange_at_entry = float(entry_row.get("orange_ray", float("nan")))
            purple_at_entry = float(entry_row.get("purple_ray", float("nan")))
            # Entry ray = the one the close just crossed above.
            prev_idx = df.index[df.index.get_loc(entry_ts) - 1]
            prev_row = df.loc[prev_idx]
            prev_close = float(prev_row["Close"])
            prev_orange = float(prev_row.get("orange_ray", float("nan")))
            prev_purple = float(prev_row.get("purple_ray", float("nan")))

            entry_ray_name = None
            entry_ray_value = None
            if prev_close <= prev_orange and entry_price > orange_at_entry:
                entry_ray_name  = "orange"
                entry_ray_value = orange_at_entry
            elif prev_close <= prev_purple and entry_price > purple_at_entry:
                entry_ray_name  = "purple"
                entry_ray_value = purple_at_entry

        else:  # SELL
            entry_price = float(entry_row.get("sell_price", entry_row["Close"]))
            yellow_at_entry = float(entry_row.get("yellow_ray", float("nan")))
            blue_at_entry   = float(entry_row.get("blue_ray",   float("nan")))
            prev_idx = df.index[df.index.get_loc(entry_ts) - 1]
            prev_row = df.loc[prev_idx]
            prev_close = float(prev_row["Close"])
            prev_yellow = float(prev_row.get("yellow_ray", float("nan")))
            prev_blue   = float(prev_row.get("blue_ray",   float("nan")))

            entry_ray_name = None
            entry_ray_value = None
            if prev_close >= prev_yellow and entry_price < yellow_at_entry:
                entry_ray_name  = "yellow"
                entry_ray_value = yellow_at_entry
            elif prev_close >= prev_blue and entry_price < blue_at_entry:
                entry_ray_name  = "blue"
                entry_ray_value = blue_at_entry

        # Check if price crossed back over the entry ray before the exit.
        crossed_back = False
        crossed_back_ts = None
        if entry_ray_name is not None:
            trade_bars = df.loc[entry_ts:exit_ts]
            for bar_ts, bar_row in trade_bars.iterrows():
                if bar_ts == entry_ts:
                    continue
                bar_close = float(bar_row["Close"])
                ray_col   = f"{entry_ray_name}_ray"
                ray_val   = float(bar_row.get(ray_col, float("nan")))
                if pd.isna(ray_val):
                    continue
                if sig == "BUY" and bar_close < ray_val:
                    crossed_back = True
                    crossed_back_ts = bar_ts
                    break
                elif sig == "SELL" and bar_close > ray_val:
                    crossed_back = True
                    crossed_back_ts = bar_ts
                    break

        results.append({
            "date":           entry_ts.strftime("%Y-%m-%d"),
            "entry_time":     entry_ts.strftime("%H:%M"),
            "exit_time":      exit_ts.strftime("%H:%M"),
            "signal":         sig,
            "entry_price":    int(entry_price),
            "entry_ray":      entry_ray_name or "unknown",
            "crossed_back":   crossed_back,
            "crossback_time": crossed_back_ts.strftime("%H:%M") if crossed_back_ts else "",
            "trade_pl":       round(trade_pl, 1),
            "winner":         trade_pl > 0,
        })

    return pd.DataFrame(results)


def summarise(all_trades: pd.DataFrame) -> None:
    if all_trades.empty:
        print("No trades found.")
        return

    total = len(all_trades)
    crossed = all_trades[all_trades["crossed_back"]]
    not_crossed = all_trades[~all_trades["crossed_back"]]

    print("\n" + "=" * 60)
    print("THEORY TEST: Does crossing back = loser?")
    print("=" * 60)
    print(f"\nTotal trades analysed: {total}")
    print()

    if not crossed.empty:
        win_rate = crossed["winner"].mean() * 100
        avg_pl   = crossed["trade_pl"].mean()
        print(f"Crossed back over entry ray ({len(crossed)} trades):")
        print(f"  Win rate:  {win_rate:.0f}%")
        print(f"  Avg P/L:   {avg_pl:+.1f} pts")

    if not not_crossed.empty:
        win_rate = not_crossed["winner"].mean() * 100
        avg_pl   = not_crossed["trade_pl"].mean()
        print(f"\nDid NOT cross back ({len(not_crossed)} trades):")
        print(f"  Win rate:  {win_rate:.0f}%")
        print(f"  Avg P/L:   {avg_pl:+.1f} pts")

    print()
    print("Per-trade detail:")
    print("-" * 60)
    pd.set_option("display.width", 120)
    print(all_trades.to_string(index=False))
    print()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--csv", default=None, help="Path to a single tracking CSV (default: all in IB_Live/tracking)")
    args = p.parse_args()

    if args.csv:
        csv_files = [args.csv]
    else:
        csv_files = [
            os.path.join(_TRACKING_ROOT, f)
            for f in os.listdir(_TRACKING_ROOT)
            if f.startswith("YM_tracking_") and f.endswith(".csv")
        ]
        csv_files.sort()

    if not csv_files:
        print(f"No tracking CSVs found in {_TRACKING_ROOT}")
    else:
        all_trades = pd.concat([analyse_file(f) for f in csv_files], ignore_index=True)
        summarise(all_trades)
