"""Debug belief engine entry logic for 02/05 and 02/17 — per-bar detail."""
import sys, os
sys.path.insert(0, '.')
import pandas as pd, pytz, numpy as np
from TradingAlgoFast import AlgoConfig, run_trading_algo_fast
from fred_belief_engine import BeliefEngine

EST = pytz.timezone("US/Eastern")
DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")

CONFIG = AlgoConfig(
    warmup_minutes=7,
    steep_angle_threshold=90.0,
    proximity_points=4.0,
    min_reversal_minutes=0,
    min_entry_angle=0.0,
    partial_tp_pts=50.0,
    spike_profit_pts=50.0,
    spike_profit_bars=9,
    wm_shield_distance=0.0,
    steep_line_reentry=False,
    steep_line_proximity=0.0,
    steep_line_exit_only=False,
    num_contracts=2,
)


def debug_session(date_str: str, end_time: str = "10:30", num_bars: int = 40):
    """Print per-bar debug for belief engine entry logic."""
    fpath = os.path.join(DATA_ROOT, f"CBOT_MINI_YM1_{date_str}.csv")
    df = pd.read_csv(fpath, index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index, utc=True).tz_convert(EST)

    day_start = pd.Timestamp(f"{date_str} 09:30", tz=EST)
    day_end = pd.Timestamp(f"{date_str} {end_time}", tz=EST)
    day_data = df[(df.index >= day_start) & (df.index <= day_end)]

    # Run mechanical algo to get line values
    algo_df = run_trading_algo_fast(day_data, date_str, "09:30", end_time, config=CONFIG)

    # Get mechanical signals for comparison
    mech_signals = algo_df[algo_df['signal'].isin(['BUY', 'SELL'])]

    print(f"\n{'='*120}")
    print(f"DEBUG: {date_str} — First {num_bars} bars")
    print(f"{'='*120}")
    print(f"\nMechanical algo first entry: ", end="")
    if len(mech_signals) > 0:
        first_mech = mech_signals.iloc[0]
        print(f"{mech_signals.index[0].strftime('%H:%M')} {first_mech['signal']} @ {first_mech['Close']:.0f}")
    else:
        print("NONE")

    # Run belief engine with detailed per-bar logging
    engine = BeliefEngine()

    print(f"\n{'Bar':<4} {'Time':<6} {'Close':<7} {'Purple':<8} {'Blue':<8} {'Orange':<8} {'Yellow':<8} "
          f"{'PrevCl':<7} {'P_cross':<8} {'B_cross':<8} {'O_cross':<8} {'Y_cross':<8} "
          f"{'Evidence':<30} {'Conf':<6} {'Resolve':<12} {'Action':<10} {'Reason'}")
    print("-" * 180)

    n = min(num_bars, len(algo_df))
    for i in range(n):
        row = algo_df.iloc[i]
        prev_row = algo_df.iloc[i - 1] if i > 0 else row

        close = float(row["Close"])
        prev_close = float(prev_row["Close"])

        purple = float(row["purple_ray"]) if "purple_ray" in row.index and not pd.isna(row["purple_ray"]) else np.nan
        blue = float(row["blue_ray"]) if "blue_ray" in row.index and not pd.isna(row["blue_ray"]) else np.nan
        orange = float(row["orange_ray"]) if "orange_ray" in row.index and not pd.isna(row["orange_ray"]) else np.nan
        yellow = float(row["yellow_ray"]) if "yellow_ray" in row.index and not pd.isna(row["yellow_ray"]) else np.nan

        prev_purple = float(prev_row["purple_ray"]) if "purple_ray" in prev_row.index and not pd.isna(prev_row["purple_ray"]) else np.nan
        prev_blue = float(prev_row["blue_ray"]) if "blue_ray" in prev_row.index and not pd.isna(prev_row["blue_ray"]) else np.nan
        prev_orange = float(prev_row["orange_ray"]) if "orange_ray" in prev_row.index and not pd.isna(prev_row["orange_ray"]) else np.nan
        prev_yellow = float(prev_row["yellow_ray"]) if "yellow_ray" in prev_row.index and not pd.isna(prev_row["yellow_ray"]) else np.nan

        # Detect crosses manually
        p_cross = ""
        if not np.isnan(prev_purple) and not np.isnan(purple):
            if prev_close <= prev_purple and close > purple:
                p_cross = "ABOVE"
            elif prev_close >= prev_purple and close < purple:
                p_cross = "BELOW"

        b_cross = ""
        if not np.isnan(prev_blue) and not np.isnan(blue):
            if prev_close <= prev_blue and close > blue:
                b_cross = "ABOVE"
            elif prev_close >= prev_blue and close < blue:
                b_cross = "BELOW"

        o_cross = ""
        if not np.isnan(prev_orange) and not np.isnan(orange):
            if prev_close <= prev_orange and close > orange:
                o_cross = "ABOVE"
            elif prev_close >= prev_orange and close < orange:
                o_cross = "BELOW"

        y_cross = ""
        if not np.isnan(prev_yellow) and not np.isnan(yellow):
            if prev_close <= prev_yellow and close > yellow:
                y_cross = "ABOVE"
            elif prev_close >= prev_yellow and close < yellow:
                y_cross = "BELOW"

        # Process through belief engine
        bar = {
            "time": algo_df.index[i],
            "Open": float(row["Open"]),
            "High": float(row["High"]),
            "Low": float(row["Low"]),
            "Close": close,
            "prev_close": prev_close,
        }
        lines = {
            "purple": purple, "blue": blue, "orange": orange, "yellow": yellow,
            "prev_purple": prev_purple, "prev_blue": prev_blue,
            "prev_orange": prev_orange, "prev_yellow": prev_yellow,
            "steep_purple": np.nan, "steep_blue": np.nan,
            "prev_steep_purple": np.nan, "prev_steep_blue": np.nan,
        }

        # Capture state before
        conf_before = engine.confidence
        resolve_before = engine.resolve_state

        engine.process_bar(i, bar, lines)

        # Get the log entry just created
        log_entry = engine.bar_logs[-1]
        evidence_str = log_entry["evidence_types"] if log_entry["evidence_types"] else "-"
        action = log_entry["action"]

        # Determine reason for non-entry
        reason = ""
        if action == "WAIT":
            reason = f"warmup (bar {i} < {engine.cfg.warmup_bars})"
        elif action == "HOLD" and engine.position == 0:
            if not any([p_cross, b_cross, o_cross, y_cross]):
                reason = "no line cross detected"
            else:
                reason = "cross detected but engine didn't fire??"
        elif action in ("BUY", "SELL", "REVERSE"):
            reason = "ENTRY"

        time_str = algo_df.index[i].strftime('%H:%M')
        print(f"{i:<4} {time_str:<6} {close:<7.0f} "
              f"{purple:<8.0f} {blue:<8.0f} {orange:<8.0f} {yellow:<8.0f} "
              f"{prev_close:<7.0f} "
              f"{p_cross:<8} {b_cross:<8} {o_cross:<8} {y_cross:<8} "
              f"{evidence_str:<30} "
              f"{log_entry['confidence']:<+6.1f} {log_entry['resolve_state']:<12} "
              f"{action:<10} {reason}")

    # Summary
    print(f"\n{'='*80}")
    print(f"SUMMARY: {date_str}")
    print(f"{'='*80}")

    total_crosses = sum(1 for log in engine.bar_logs if log["evidence_types"] and
                        any(x in log["evidence_types"] for x in ["CROSS", "cross"]))
    total_entries = sum(1 for log in engine.bar_logs if log["action"] in ("BUY", "SELL", "REVERSE"))

    print(f"  Total bars with line crosses: {total_crosses}")
    print(f"  Total belief engine entries: {total_entries}")
    print(f"  Mechanical algo entries (first {num_bars} bars): {len(mech_signals[mech_signals.index <= algo_df.index[min(num_bars-1, len(algo_df)-1)]])}")
    print(f"  Belief engine final P/L: {engine.bar_logs[-1]['session_pl']:.0f}")

    # Check: are lines valid during warmup?
    warmup_lines = []
    for i in range(min(engine.cfg.warmup_bars, len(algo_df))):
        row = algo_df.iloc[i]
        p = float(row["purple_ray"]) if "purple_ray" in row.index and not pd.isna(row["purple_ray"]) else np.nan
        b = float(row["blue_ray"]) if "blue_ray" in row.index and not pd.isna(row["blue_ray"]) else np.nan
        warmup_lines.append((p, b))

    print(f"\n  Line values during warmup (bars 0-{engine.cfg.warmup_bars-1}):")
    for i, (p, b) in enumerate(warmup_lines):
        print(f"    Bar {i}: purple={p:.0f}, blue={b:.0f}")


if __name__ == "__main__":
    debug_session("2026-02-05", "10:30", 40)
    debug_session("2026-02-17", "10:30", 40)
