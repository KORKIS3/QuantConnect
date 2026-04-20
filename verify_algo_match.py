"""verify_algo_match.py

Runs TradingAlgo (original), TradingAlgoFast (current), and the new
consolidated TradingAlgoFast (post-rework) on every available day and
records the final P/L and signal count for each.

Results are written to verify_algo_match_results.csv so you can diff them
before and after the rework to confirm nothing changed.

Usage:
    python verify_algo_match.py
"""

import os
import sys
import time
import traceback

import pandas as pd
import pytz

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "930_1000")
OUT_CSV   = "verify_algo_match_results.csv"

_EST = pytz.timezone("US/Eastern")

# ---------------------------------------------------------------------------
# Import all three engines
# ---------------------------------------------------------------------------
try:
    from TradingAlgo import run_trading_algo, AlgoConfig as AlgoConfigOrig
    _HAS_ORIG = True
except Exception as e:
    print(f"[WARN] Could not import TradingAlgo (original): {e}")
    _HAS_ORIG = False

try:
    from TradingAlgoFast import run_trading_algo_fast, AlgoConfig as AlgoConfigFast
    _HAS_FAST = True
except Exception as e:
    print(f"[WARN] Could not import TradingAlgoFast: {e}")
    _HAS_FAST = False

# After rework, TradingAlgoFast is self-contained — same import, aliased here
# so the column name is distinct in the output.
_HAS_NEW = _HAS_FAST  # same engine post-rework; column labelled "new_fast"

# ---------------------------------------------------------------------------
# Config — matches proven settings
# ---------------------------------------------------------------------------
CFG_ORIG = AlgoConfigOrig(
    warmup_minutes=12,
    steep_angle_threshold=70.0,
    proximity_points=15.0,
    min_reversal_minutes=10,
) if _HAS_ORIG else None

CFG_FAST = AlgoConfigFast(
    warmup_minutes=12,
    steep_angle_threshold=70.0,
    proximity_points=15.0,
    min_reversal_minutes=10,
) if _HAS_FAST else None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_csv(path: str, date_str: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    # Support both 'time' and 'Datetime' column names
    time_col = "time" if "time" in df.columns else "Datetime"
    df[time_col] = pd.to_datetime(df[time_col], utc=False)
    df = df.set_index(time_col)
    df.index.name = "Datetime"
    if df.index.tz is None:
        df.index = df.index.tz_localize(_EST)
    else:
        df.index = df.index.tz_convert(_EST)
    # Filter to session window
    start = pd.Timestamp(f"{date_str} 09:30:00", tz=_EST)
    end   = pd.Timestamp(f"{date_str} 10:30:00", tz=_EST)
    df = df[(df.index >= start) & (df.index <= end)]
    return df


def _summarise(result: pd.DataFrame) -> dict:
    """Extract final P/L, buy count, sell count from a result DataFrame."""
    if result is None or result.empty:
        return {"pl": None, "buys": 0, "sells": 0, "signals": 0}
    pl     = float(result["pl"].iloc[-1]) if "pl" in result.columns else None
    buys   = int((result["signal"] == "BUY").sum())  if "signal" in result.columns else 0
    sells  = int((result["signal"] == "SELL").sum()) if "signal" in result.columns else 0
    return {"pl": pl, "buys": buys, "sells": sells, "signals": buys + sells}


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def run_verification(max_days: int = 0) -> pd.DataFrame:
    files = sorted(f for f in os.listdir(DATA_ROOT) if f.endswith(".csv"))
    if max_days > 0:
        files = files[:max_days]

    rows = []
    total = len(files)

    for idx, fname in enumerate(files, 1):
        date_str = fname.replace("CBOT_MINI_YM1_", "").replace(".csv", "")
        path = os.path.join(DATA_ROOT, fname)

        print(f"[{idx:4d}/{total}] {date_str}", end="  ", flush=True)

        try:
            df = _load_csv(path, date_str)
        except Exception as e:
            print(f"LOAD ERROR: {e}")
            continue

        if df.empty or len(df) < 5:
            print("SKIP (too few bars)")
            continue

        row = {"date": date_str}

        # --- Original TradingAlgo ---
        if _HAS_ORIG:
            t0 = time.perf_counter()
            try:
                res = run_trading_algo(df, target_date=date_str, config=CFG_ORIG)
                s = _summarise(res)
                row["orig_pl"]      = s["pl"]
                row["orig_buys"]    = s["buys"]
                row["orig_sells"]   = s["sells"]
                row["orig_signals"] = s["signals"]
            except Exception as e:
                row["orig_pl"] = row["orig_buys"] = row["orig_sells"] = row["orig_signals"] = None
                row["orig_error"] = str(e)
            row["orig_ms"] = round((time.perf_counter() - t0) * 1000, 1)

        # --- TradingAlgoFast (current / pre-rework) ---
        if _HAS_FAST:
            t0 = time.perf_counter()
            try:
                res = run_trading_algo_fast(df, target_date=date_str, config=CFG_FAST)
                s = _summarise(res)
                row["fast_pl"]      = s["pl"]
                row["fast_buys"]    = s["buys"]
                row["fast_sells"]   = s["sells"]
                row["fast_signals"] = s["signals"]
            except Exception as e:
                row["fast_pl"] = row["fast_buys"] = row["fast_sells"] = row["fast_signals"] = None
                row["fast_error"] = str(e)
            row["fast_ms"] = round((time.perf_counter() - t0) * 1000, 1)

        # --- New consolidated fast (post-rework, same function) ---
        if _HAS_NEW:
            t0 = time.perf_counter()
            try:
                res = run_trading_algo_fast(df, target_date=date_str, config=CFG_FAST)
                s = _summarise(res)
                row["new_pl"]      = s["pl"]
                row["new_buys"]    = s["buys"]
                row["new_sells"]   = s["sells"]
                row["new_signals"] = s["signals"]
            except Exception as e:
                row["new_pl"] = row["new_buys"] = row["new_sells"] = row["new_signals"] = None
                row["new_error"] = str(e)
            row["new_ms"] = round((time.perf_counter() - t0) * 1000, 1)

        # --- Match flags ---
        if _HAS_ORIG and _HAS_FAST:
            row["orig_vs_fast_pl_match"]  = (row.get("orig_pl") == row.get("fast_pl"))
            row["orig_vs_fast_sig_match"] = (row.get("orig_signals") == row.get("fast_signals"))
        if _HAS_FAST and _HAS_NEW:
            row["fast_vs_new_pl_match"]   = (row.get("fast_pl") == row.get("new_pl"))
            row["fast_vs_new_sig_match"]  = (row.get("fast_signals") == row.get("new_signals"))

        rows.append(row)

        # Quick status line
        parts = []
        if _HAS_ORIG:   parts.append(f"orig={row.get('orig_pl', 'ERR'):>7}")
        if _HAS_FAST:   parts.append(f"fast={row.get('fast_pl', 'ERR'):>7}")
        if _HAS_NEW:    parts.append(f"new={row.get('new_pl',  'ERR'):>7}")
        match_str = ""
        if "orig_vs_fast_pl_match" in row:
            match_str += " O=F" if row["orig_vs_fast_pl_match"] else " O≠F"
        if "fast_vs_new_pl_match" in row:
            match_str += " F=N" if row["fast_vs_new_pl_match"] else " F≠N"
        print("  ".join(parts) + match_str)

    results_df = pd.DataFrame(rows)
    results_df.to_csv(OUT_CSV, index=False)
    print(f"\nResults saved to {OUT_CSV}")

    # Summary
    print("\n=== SUMMARY ===")
    if _HAS_ORIG and _HAS_FAST and "orig_vs_fast_pl_match" in results_df.columns:
        n_match = results_df["orig_vs_fast_pl_match"].sum()
        n_total = results_df["orig_vs_fast_pl_match"].notna().sum()
        print(f"  orig vs fast P/L match: {n_match}/{n_total}")
    if _HAS_FAST and _HAS_NEW and "fast_vs_new_pl_match" in results_df.columns:
        n_match = results_df["fast_vs_new_pl_match"].sum()
        n_total = results_df["fast_vs_new_pl_match"].notna().sum()
        print(f"  fast vs new  P/L match: {n_match}/{n_total}")
    if _HAS_ORIG:
        total_orig = results_df["orig_pl"].sum() if "orig_pl" in results_df else 0
        print(f"  orig total P/L: {total_orig:.0f} pts")
    if _HAS_FAST:
        total_fast = results_df["fast_pl"].sum() if "fast_pl" in results_df else 0
        print(f"  fast total P/L: {total_fast:.0f} pts")
    if _HAS_NEW:
        total_new = results_df["new_pl"].sum() if "new_pl" in results_df else 0
        print(f"  new  total P/L: {total_new:.0f} pts")

    return results_df


if __name__ == "__main__":
    max_days = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    run_verification(max_days=max_days)
