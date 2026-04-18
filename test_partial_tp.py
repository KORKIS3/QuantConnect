"""Partial take-profit: 2 contracts, take profit on 1st at X pts, hold 2nd per system.
Compare vs baseline (both contracts held to system exit)."""
import os
import pandas as pd, pytz, numpy as np
from TradingAlgo import AlgoConfig
from TradingAlgoFast import run_trading_algo_fast

_EST = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")

config = AlgoConfig(warmup_minutes=12, steep_angle_threshold=70.0,
                    proximity_points=15.0, min_reversal_minutes=0, max_loss_per_trade=0,
                    confirmation_bars=0)

csv_files = sorted([f for f in os.listdir(_DATA_ROOT) if f.endswith(".csv")])
print(f"Partial take-profit test on {len(csv_files)} days (day session)...\n", flush=True)

_SPIKE_PTS = 100
_SPIKE_BARS = 5
_WM_TOLERANCE = 12
_WM_MIN_TOUCHES = 4
_WM_MIN_SPAN = 15
_WM_LOOKBACK = 30
_WM_SHIELD = 12.0
_MULTIPLIER = 5


def find_clusters(vals, times):
    if len(vals) < _WM_MIN_TOUCHES:
        return []
    indexed = sorted(zip(vals, times), key=lambda x: x[0])
    clusters = []
    used = set()
    for i in range(len(indexed)):
        if i in used:
            continue
        base = indexed[i][0]
        group = [(indexed[i][0], indexed[i][1])]
        used.add(i)
        for j in range(i + 1, len(indexed)):
            if j in used:
                continue
            if abs(indexed[j][0] - base) <= _WM_TOLERANCE:
                group.append((indexed[j][0], indexed[j][1]))
                used.add(j)
            elif indexed[j][0] - base > _WM_TOLERANCE:
                break
        if len(group) >= _WM_MIN_TOUCHES:
            tt = sorted([g[1] for g in group])
            span = (tt[-1] - tt[0]).total_seconds() / 60
            if span >= _WM_MIN_SPAN:
                clusters.append((float(np.mean([g[0] for g in group])), len(group)))
    return clusters


def run_backtest(algo_df, tp_pts, num_contracts=2):
    """Post-hoc 10-min filter + spike exit + wm shield + partial take-profit.
    tp_pts: take profit on 1st contract at this many pts (0=baseline, all contracts held to exit)
    num_contracts: total contracts per trade
    Returns total P/L in DOLLARS (not pts) to account for partial sizing.
    """
    rows = algo_df[algo_df["signal"].isin(["BUY", "SELL"])]
    if rows.empty:
        return None

    filtered = []
    for ts, row in rows.iterrows():
        sig = row["signal"]
        price = float(row["buy_price"] if sig == "BUY" else row["sell_price"])
        if not filtered:
            filtered.append((ts, sig, price))
            continue
        lt, ls, _ = filtered[-1]
        if ls != sig:
            if (ts - lt).total_seconds() / 60 >= 10:
                filtered.append((ts, sig, price))
        else:
            filtered.append((ts, sig, price))

    if not filtered:
        return None

    closes = algo_df["Close"].values.astype(float)
    highs = algo_df["High"].values.astype(float)
    lows = algo_df["Low"].values.astype(float)
    times = algo_df.index
    sig_idx = 0
    total_dollars = 0.0
    trade_count = 0
    winners = 0
    pos = "flat"
    ep = None
    entry_bar = 0
    partial_taken = False  # has the 1st contract been closed?

    for i in range(len(algo_df)):
        # Check partial take-profit (only if we haven't taken it yet)
        if tp_pts > 0 and pos != "flat" and ep is not None and not partial_taken:
            if pos == "long":
                unrealized = closes[i] - ep
            else:
                unrealized = ep - closes[i]
            if unrealized >= tp_pts:
                # Take profit on 1 contract
                total_dollars += unrealized * _MULTIPLIER  # 1 contract
                partial_taken = True

        # Check if this bar has a filtered signal
        if sig_idx < len(filtered) and times[i] == filtered[sig_idx][0]:
            ts, sig, price = filtered[sig_idx]
            sig_idx += 1

            # Water mark shield (day session)
            shielded = False
            if _WM_SHIELD > 0 and pos != "flat" and i >= _WM_LOOKBACK:
                ws = max(0, i - _WM_LOOKBACK)
                if pos == "long" and sig == "SELL":
                    for lvl, _ in find_clusters(lows[ws:i], times[ws:i]):
                        if lvl < closes[i] and (closes[i] - lvl) <= _WM_SHIELD:
                            shielded = True; break
                elif pos == "short" and sig == "BUY":
                    for lvl, _ in find_clusters(highs[ws:i], times[ws:i]):
                        if lvl > closes[i] and (lvl - closes[i]) <= _WM_SHIELD:
                            shielded = True; break

            if not shielded:
                # Close remaining contracts
                if pos == "long" and sig == "SELL":
                    pl_pts = price - ep
                    remaining = (num_contracts - 1) if partial_taken else num_contracts
                    total_dollars += pl_pts * remaining * _MULTIPLIER
                    trade_pl = pl_pts * num_contracts * _MULTIPLIER
                    if partial_taken:
                        # Add back the partial profit for trade counting
                        pass
                    trade_count += 1
                    if pl_pts > 0 or partial_taken:
                        winners += 1
                elif pos == "short" and sig == "BUY":
                    pl_pts = ep - price
                    remaining = (num_contracts - 1) if partial_taken else num_contracts
                    total_dollars += pl_pts * remaining * _MULTIPLIER
                    trade_count += 1
                    if pl_pts > 0 or partial_taken:
                        winners += 1

                if sig == "BUY":
                    pos, ep, entry_bar = "long", price, i
                else:
                    pos, ep, entry_bar = "short", price, i
                partial_taken = False
            continue

        # Spike exit
        if pos != "flat" and ep is not None and i > entry_bar:
            bh = i - entry_bar
            if bh <= _SPIKE_BARS:
                mv = (closes[i] - ep) if pos == "long" else (ep - closes[i])
                if mv >= _SPIKE_PTS:
                    remaining = (num_contracts - 1) if partial_taken else num_contracts
                    total_dollars += mv * remaining * _MULTIPLIER
                    trade_count += 1
                    winners += 1
                    pos, ep, entry_bar = "flat", None, 0
                    partial_taken = False

    # Close open position at session end
    if pos != "flat" and ep is not None:
        lc = closes[-1]
        pl_pts = (lc - ep) if pos == "long" else (ep - lc)
        remaining = (num_contracts - 1) if partial_taken else num_contracts
        total_dollars += pl_pts * remaining * _MULTIPLIER
        trade_count += 1
        if pl_pts > 0 or partial_taken:
            winners += 1

    return (total_dollars, trade_count, winners) if trade_count > 0 else None


# 2-contract tests
thresholds = [0, 50, 70, 85, 100]
print("=== 2 CONTRACTS: Take profit on 1st at X pts, hold 2nd ===\n", flush=True)

for tp in thresholds:
    total_usd = 0.0
    total_trades = 0
    total_winners = 0
    daily_pls = []

    for fname in csv_files:
        dd = fname.replace("CBOT_MINI_YM1_", "").replace(".csv", "")
        try:
            df = pd.read_csv(os.path.join(_DATA_ROOT, fname), index_col=0, parse_dates=True)
            df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
        except:
            continue
        if len(df) < 10:
            continue
        ds = pd.Timestamp(f"{dd} 09:30", tz=_EST)
        de = pd.Timestamp(f"{dd} 16:59", tz=_EST)
        day_data = df[(df.index >= ds) & (df.index <= de)]
        if len(day_data) < 15:
            continue
        try:
            algo = run_trading_algo_fast(day_data, dd, "09:30", "17:00", config=config)
        except:
            continue

        result = run_backtest(algo, tp, num_contracts=2)
        if result:
            usd, trades, wins = result
            total_usd += usd
            total_trades += trades
            total_winners += wins
            daily_pls.append(usd)

    wr = total_winners / total_trades * 100 if total_trades else 0
    avg = np.mean(daily_pls) if daily_pls else 0
    label = f"TP @{tp}pts" if tp > 0 else "BASELINE (2c)"
    print(f"{label:<18} Trades:{total_trades:>5}  Win%:{wr:>5.1f}%  ${total_usd:>+10,.0f}  Avg:${avg:>+7.1f}/day", flush=True)
