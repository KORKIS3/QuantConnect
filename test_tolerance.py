"""Test different tolerance values for the connect-the-highs purple/blue line.
Higher tolerance = more aggressive line (cuts through more highs, steeper slope).
Day session only, 2-year backtest."""
import os, time
import pandas as pd, pytz, numpy as np
from TradingAlgo import AlgoConfig

_EST = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")
config = AlgoConfig(warmup_minutes=12, steep_angle_threshold=70.0,
                    proximity_points=15.0, min_reversal_minutes=0, max_loss_per_trade=0)
csv_files = sorted([f for f in os.listdir(_DATA_ROOT) if f.endswith(".csv")])
print(f"Tolerance sweep on {len(csv_files)} days (day session 9:30-17:00)\n", flush=True)

_SPIKE_PTS, _SPIKE_BARS = 100, 5
_WM_TOL, _WM_MT, _WM_MS, _WM_LB, _WM_SHIELD = 12, 4, 15, 30, 12.0
_MUL = 5
_PARTIAL_TP = 50


def find_clusters(vals, times):
    if len(vals) < _WM_MT: return []
    indexed = sorted(zip(vals, times), key=lambda x: x[0])
    clusters, used = [], set()
    for i in range(len(indexed)):
        if i in used: continue
        base = indexed[i][0]; group = [(indexed[i][0], indexed[i][1])]; used.add(i)
        for j in range(i + 1, len(indexed)):
            if j in used: continue
            if abs(indexed[j][0] - base) <= _WM_TOL:
                group.append((indexed[j][0], indexed[j][1])); used.add(j)
            elif indexed[j][0] - base > _WM_TOL: break
        if len(group) >= _WM_MT:
            tt = sorted([g[1] for g in group])
            if (tt[-1] - tt[0]).total_seconds() / 60 >= _WM_MS:
                clusters.append((float(np.mean([g[0] for g in group])), len(group)))
    return clusters


def run_fast_with_tolerance(data, target_date, start_time, end_time, cfg, tol):
    """Run the fast algo with a custom tolerance for the connect-the-highs line."""
    import numpy as np
    import matplotlib.dates as mdates

    full_data = data.copy()
    est = pytz.timezone("US/Eastern")
    try:
        if full_data.index.tz is None:
            full_data.index = pd.to_datetime(full_data.index, errors="coerce").tz_localize(est)
        else:
            full_data.index = pd.to_datetime(full_data.index).tz_convert(est)
    except: pass

    n = len(full_data)
    if cfg.warmup_minutes is not None:
        cutoff_time = full_data.index[0] + pd.Timedelta(minutes=cfg.warmup_minutes)
    else:
        cutoff_time = pd.Timestamp(f"{target_date} {start_time}:00", tz=est) + pd.Timedelta(minutes=8)

    highs_arr  = full_data["High"].values.astype(np.float64)
    lows_arr   = full_data["Low"].values.astype(np.float64)
    closes_arr = full_data["Close"].values.astype(np.float64)
    times_idx  = full_data.index
    times_num  = np.array([mdates.date2num(t) for t in times_idx])

    _ax_w_in = 16.0 * (0.85 - 0.125)
    _ax_h_in = 9.0 * (0.88 - 0.11)
    _x_range = 75 / (24 * 60)
    _y_range = highs_arr.max() + 20.0 - (lows_arr.min() - 20.0)
    x_per_unit = _x_range / _ax_w_in
    y_per_unit = _y_range / _ax_h_in

    cutoff_idx = 0
    for i in range(n):
        if times_idx[i] >= cutoff_time:
            cutoff_idx = i; break

    # Orange/yellow
    orange_slope_val = -np.tan(np.deg2rad(cfg.orange_angle)) * (y_per_unit / x_per_unit)
    orange_vals = np.zeros(n)
    o_anchor_p = highs_arr[0]; o_anchor_t = times_num[0]
    for i in range(n):
        if highs_arr[i] > o_anchor_p: o_anchor_p = highs_arr[i]; o_anchor_t = times_num[i]
        orange_vals[i] = o_anchor_p + orange_slope_val * (times_num[i] - o_anchor_t)

    yellow_slope_val = np.tan(np.deg2rad(cfg.yellow_angle)) * (y_per_unit / x_per_unit)
    yellow_vals = np.zeros(n)
    y_anchor_p = lows_arr[0]; y_anchor_t = times_num[0]
    for i in range(n):
        if lows_arr[i] < y_anchor_p: y_anchor_p = lows_arr[i]; y_anchor_t = times_num[i]
        yellow_vals[i] = y_anchor_p + yellow_slope_val * (times_num[i] - y_anchor_t)

    # Purple/blue with custom tolerance
    purple_vals = np.full(n, highs_arr[0])
    blue_vals   = np.full(n, lows_arr[0])
    p_anchor_p = highs_arr[0]; p_anchor_idx = 0
    b_anchor_p = lows_arr[0];  b_anchor_idx = 0
    purple_slopes = np.zeros(n)
    blue_slopes   = np.zeros(n)
    p_best_j = -1; p_best_slope = -0.001
    b_best_j = -1; b_best_slope = 0.001

    for i in range(n):
        if highs_arr[i] > p_anchor_p: p_anchor_p = highs_arr[i]; p_anchor_idx = i; p_best_j = -1; p_best_slope = -0.001
        if lows_arr[i] < b_anchor_p: b_anchor_p = lows_arr[i]; b_anchor_idx = i; b_best_j = -1; b_best_slope = 0.001

        if i > p_anchor_idx:
            dt_i = times_num[i] - times_num[p_anchor_idx]
            if dt_i > 0:
                cand_slope = (highs_arr[i] - p_anchor_p) / dt_i
                if cand_slope <= 0:
                    valid = True
                    for k in range(p_anchor_idx + 1, i):
                        line_at_k = p_anchor_p + cand_slope * (times_num[k] - times_num[p_anchor_idx])
                        if highs_arr[k] > line_at_k + tol:  # <-- tolerance here
                            valid = False; break
                    if valid: p_best_j = i; p_best_slope = cand_slope

        p_slope = p_best_slope if p_best_j >= 0 else (purple_slopes[i-1] if i > 0 else -0.001)
        purple_slopes[i] = p_slope
        purple_vals[i] = p_anchor_p + p_slope * (times_num[i] - times_num[p_anchor_idx])

        if i > b_anchor_idx:
            dt_i = times_num[i] - times_num[b_anchor_idx]
            if dt_i > 0:
                cand_slope = (lows_arr[i] - b_anchor_p) / dt_i
                if cand_slope >= 0:
                    valid = True
                    for k in range(b_anchor_idx + 1, i):
                        line_at_k = b_anchor_p + cand_slope * (times_num[k] - times_num[b_anchor_idx])
                        if lows_arr[k] < line_at_k - tol:  # <-- tolerance here
                            valid = False; break
                    if valid: b_best_j = i; b_best_slope = cand_slope

        b_slope = b_best_slope if b_best_j >= 0 else (blue_slopes[i-1] if i > 0 else 0.001)
        blue_slopes[i] = b_slope
        blue_vals[i] = b_anchor_p + b_slope * (times_num[i] - times_num[b_anchor_idx])

    # Signal detection
    from TradingAlgoFast import _display_angle_from_slope, _build_signals_frame
    buy_signals = {}; sell_signals = {}; liquidation_timestamps = set()
    session_realized_pl = 0.0; temp_position = "flat"; temp_entry_price = None; temp_entry_time = None

    for i in range(max(cutoff_idx, 3), n):
        time_i = times_idx[i]
        current_close = closes_arr[i]
        prev_close = closes_arr[i-1]
        prev_orange = orange_vals[i-1]; prev_yellow = yellow_vals[i-1]
        prev_purple = purple_vals[i-1]; prev_blue = blue_vals[i-1]
        _dt = times_num[i] - times_num[i-1]
        curr_orange = orange_vals[i-1] + orange_slope_val * _dt
        curr_yellow = yellow_vals[i-1] + yellow_slope_val * _dt
        prev_purple_slope = purple_slopes[i-1]; prev_blue_slope = blue_slopes[i-1]
        liquidated_this_bar = False; is_last_bar = (i == n - 1)

        mins_since_entry = (time_i - temp_entry_time).total_seconds() / 60 if temp_entry_time else 999
        orange_cross_buy = prev_close <= prev_orange and current_close > prev_orange
        yellow_cross_sell = prev_close >= prev_yellow and current_close < prev_yellow
        safety_override = ((temp_position == "short" and orange_cross_buy) or (temp_position == "long" and yellow_cross_sell))
        reversal_blocked = (cfg.min_reversal_minutes > 0 and mins_since_entry < cfg.min_reversal_minutes and not safety_override)

        if temp_position != "long" and time_i not in buy_signals and not liquidated_this_bar:
            if not (temp_position == "short" and reversal_blocked):
                buy_triggered = False
                if prev_close <= prev_orange and current_close > prev_orange: buy_triggered = True
                if not buy_triggered:
                    pa = _display_angle_from_slope(prev_purple_slope, x_per_unit, y_per_unit)
                    if pa < cfg.steep_angle_threshold and prev_close <= prev_purple and current_close > prev_purple:
                        if abs(current_close - curr_orange) > cfg.proximity_points: buy_triggered = True
                if buy_triggered:
                    if temp_position == "short" and temp_entry_price is not None:
                        session_realized_pl += temp_entry_price - current_close
                    buy_signals[time_i] = current_close
                    if is_last_bar: temp_position = "flat"; temp_entry_price = None; temp_entry_time = None
                    else: temp_position = "long"; temp_entry_price = current_close; temp_entry_time = time_i

        if temp_position != "short" and time_i not in sell_signals and not liquidated_this_bar:
            if not (temp_position == "long" and reversal_blocked):
                sell_triggered = False
                if prev_close >= prev_yellow and current_close < prev_yellow: sell_triggered = True
                if not sell_triggered:
                    ba = _display_angle_from_slope(prev_blue_slope, x_per_unit, y_per_unit)
                    if ba < cfg.steep_angle_threshold and prev_close >= prev_blue and current_close < prev_blue:
                        if abs(current_close - curr_yellow) > cfg.proximity_points: sell_triggered = True
                if sell_triggered:
                    if temp_position == "long" and temp_entry_price is not None:
                        session_realized_pl += current_close - temp_entry_price
                    sell_signals[time_i] = current_close
                    if is_last_bar: temp_position = "flat"; temp_entry_price = None; temp_entry_time = None
                    else: temp_position = "short"; temp_entry_price = current_close; temp_entry_time = time_i

    result = _build_signals_frame(full_data, buy_signals, sell_signals, False, None, liquidation_timestamps)
    result["purple_ray"] = purple_vals; result["blue_ray"] = blue_vals
    result["purple_slope"] = purple_slopes; result["blue_slope"] = blue_slopes
    result["orange_ray"] = orange_vals; result["yellow_ray"] = yellow_vals
    return result


def run_bt_with_algo(algo_df, partial_tp=50):
    """Standard backtest replay: 10-min filter, spike exit, wm shield, partial TP."""
    rows = algo_df[algo_df["signal"].isin(["BUY", "SELL"])]
    if rows.empty: return None
    filtered = []
    for ts, row in rows.iterrows():
        sig = row["signal"]; price = float(row["buy_price"] if sig == "BUY" else row["sell_price"])
        if not filtered: filtered.append((ts, sig, price)); continue
        lt, ls, _ = filtered[-1]
        if ls != sig and (ts-lt).total_seconds()/60 >= 10: filtered.append((ts, sig, price))
        elif ls == sig: filtered.append((ts, sig, price))
    if not filtered: return None

    closes = algo_df["Close"].values.astype(float)
    highs = algo_df["High"].values.astype(float)
    lows = algo_df["Low"].values.astype(float)
    times = algo_df.index
    si = 0; tpls = []; pos = "flat"; ep = None; eb = 0; partial_taken = False

    for i in range(len(algo_df)):
        if partial_tp > 0 and pos != "flat" and ep is not None and not partial_taken:
            unr = (closes[i]-ep) if pos == "long" else (ep-closes[i])
            if unr >= partial_tp: tpls.append(unr); partial_taken = True

        if si < len(filtered) and times[i] == filtered[si][0]:
            ts, sig, price = filtered[si]; si += 1
            shielded = False
            if _WM_SHIELD > 0 and pos != "flat" and i >= _WM_LB:
                ws = max(0, i-_WM_LB)
                if pos == "long" and sig == "SELL":
                    for lvl, _ in find_clusters(lows[ws:i], times[ws:i]):
                        if lvl < closes[i] and (closes[i]-lvl) <= _WM_SHIELD: shielded = True; break
                elif pos == "short" and sig == "BUY":
                    for lvl, _ in find_clusters(highs[ws:i], times[ws:i]):
                        if lvl > closes[i] and (lvl-closes[i]) <= _WM_SHIELD: shielded = True; break
            if not shielded:
                if pos == "long" and sig == "SELL":
                    rem = 1 if partial_taken else 2
                    for _ in range(rem): tpls.append(price - ep)
                elif pos == "short" and sig == "BUY":
                    rem = 1 if partial_taken else 2
                    for _ in range(rem): tpls.append(ep - price)
                if sig == "BUY": pos, ep, eb = "long", price, i
                else: pos, ep, eb = "short", price, i
                partial_taken = False
            continue

        if pos != "flat" and ep is not None and i > eb:
            if i - eb <= _SPIKE_BARS:
                mv = (closes[i]-ep) if pos == "long" else (ep-closes[i])
                if mv >= _SPIKE_PTS:
                    rem = 1 if partial_taken else 2
                    for _ in range(rem): tpls.append(mv)
                    pos, ep, eb = "flat", None, 0; partial_taken = False

    if pos != "flat" and ep is not None:
        pl = (closes[-1]-ep) if pos == "long" else (ep-closes[-1])
        rem = 1 if partial_taken else 2
        for _ in range(rem): tpls.append(pl)

    return sum(tpls) if tpls else None


# Tolerance values to test
tolerances = [1, 5, 10, 20, 50, 100]

hdr = f"{'Tolerance':>12} {'Total USD':>14} {'Pts/c/day':>10} {'Win%':>6} {'Worst':>10} {'Best':>10}"
print(hdr)
print("-" * len(hdr))

for tol in tolerances:
    agg_pts = 0.0; daily_pls = []; wins = 0; losses = 0
    for fname in csv_files:
        dd = fname.replace("CBOT_MINI_YM1_", "").replace(".csv", "")
        try:
            df = pd.read_csv(os.path.join(_DATA_ROOT, fname), index_col=0, parse_dates=True)
            df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
        except: continue
        if len(df) < 10: continue
        ds = pd.Timestamp(f"{dd} 09:30", tz=_EST)
        de = pd.Timestamp(f"{dd} 17:00", tz=_EST)
        dd_data = df[(df.index >= ds) & (df.index <= de)]
        if len(dd_data) < 15: continue
        try:
            algo = run_fast_with_tolerance(dd_data, dd, "09:30", "17:00", config, tol)
        except: continue
        day_pts = run_bt_with_algo(algo)
        if day_pts is not None:
            agg_pts += day_pts
            daily_pls.append(day_pts)
            if day_pts > 0: wins += 1
            else: losses += 1

    n = len(daily_pls) if daily_pls else 1
    total_usd = agg_pts * _MUL
    avg_pts_cd = agg_pts / 2 / n
    win_pct = wins / (wins + losses) * 100 if (wins + losses) > 0 else 0
    worst = min(daily_pls) if daily_pls else 0
    best = max(daily_pls) if daily_pls else 0
    print(f"{tol:>12} ${total_usd:>+12,.0f} {avg_pts_cd:>+9.1f} {win_pct:>5.1f}% {worst:>+9.0f} pts {best:>+9.0f} pts", flush=True)

print(f"\nBaseline (regression): $+757,105  +143.4 pts/c/day")
print(f"Pts/c/day = total pts / 2 base contracts / {n} days", flush=True)
