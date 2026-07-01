"""Compute P/L from IB execution fills for 06/23 and 06/24, then compare to backtest."""
from collections import deque
import pandas as pd, pytz, os
from TradingAlgoFast import AlgoConfig, run_trading_algo_fast

def fifo_pl(fills):
    """Compute realized P/L from fills using FIFO. Returns (total_pts, trade_log)."""
    long_entries = deque()
    short_entries = deque()
    realized = 0.0
    for time, side, qty, price in fills:
        remaining = qty
        if side == 'BOT':
            while remaining > 0 and short_entries:
                eq, ep = short_entries[0]
                cq = min(remaining, eq)
                realized += (ep - price) * cq
                remaining -= cq
                if cq == eq:
                    short_entries.popleft()
                else:
                    short_entries[0] = (eq - cq, ep)
            if remaining > 0:
                long_entries.append((remaining, price))
        else:  # SLD
            while remaining > 0 and long_entries:
                eq, ep = long_entries[0]
                cq = min(remaining, eq)
                realized += (price - ep) * cq
                remaining -= cq
                if cq == eq:
                    long_entries.popleft()
                else:
                    long_entries[0] = (eq - cq, ep)
            if remaining > 0:
                short_entries.append((remaining, price))
    open_long = sum(q for q, p in long_entries)
    open_short = sum(q for q, p in short_entries)
    return realized, open_long, open_short


def run_backtest_day(date_str):
    """Run backtest for a single day with live config."""
    config = AlgoConfig(
        warmup_minutes=7, steep_angle_threshold=90.0, proximity_points=4.0,
        min_reversal_minutes=0, min_entry_angle=0.0, partial_tp_pts=50.0,
        spike_profit_pts=100.0, spike_profit_bars=9, wm_shield_distance=0.0,
        swing_anchor_threshold=10.0, num_contracts=2, cushion_points=0.0, limit_expiry_bars=5,
    )
    EST = pytz.timezone("US/Eastern")
    fpath = os.path.expanduser(f"~/Desktop/2YearsData/full_day/CBOT_MINI_YM1_{date_str}.csv")
    if not os.path.exists(fpath):
        return None, []
    df = pd.read_csv(fpath, index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index, utc=True).tz_convert(EST)
    day_start = pd.Timestamp(f"{date_str} 09:30", tz=EST)
    day_end = pd.Timestamp(f"{date_str} 16:59", tz=EST)
    day_data = df[(df.index >= day_start) & (df.index <= day_end)]
    if len(day_data) < 15:
        return None, []
    algo_df = run_trading_algo_fast(day_data, date_str, "09:30", "17:00", config=config)
    final_pl = float(algo_df["session_pl"].iloc[-1])
    trades = []
    for idx, row in algo_df.iterrows():
        if row["signal"] in ("BUY", "SELL"):
            sig = row["signal"]
            price = row["buy_price"] if sig == "BUY" else row["sell_price"]
            trades.append((idx.strftime("%H:%M"), sig, float(price)))
    return final_pl, trades


# === JUNE 23 FILLS ===
fills_0623 = [
    ('09:34', 'SLD', 2, 51771), ('09:36', 'BOT', 1, 51707),
    ('09:39', 'BOT', 1, 51804), ('09:39', 'BOT', 1, 51804), ('09:39', 'BOT', 1, 51804),
    ('09:42', 'SLD', 1, 51868), ('09:43', 'SLD', 3, 51917),
    ('09:46', 'BOT', 1, 51939), ('09:46', 'BOT', 1, 51939), ('09:46', 'BOT', 1, 51939), ('09:46', 'BOT', 1, 51939),
    ('09:48', 'SLD', 1, 52011), ('09:51', 'SLD', 2, 52075), ('09:51', 'SLD', 1, 52075),
    ('09:53', 'BOT', 1, 52018), ('09:55', 'BOT', 1, 51963), ('09:55', 'BOT', 1, 51963), ('09:55', 'BOT', 1, 51963),
    ('09:56', 'SLD', 4, 51934),
    ('10:01', 'BOT', 1, 51962), ('10:01', 'BOT', 1, 51962), ('10:01', 'BOT', 2, 51962),
    ('10:04', 'SLD', 1, 52021), ('10:10', 'SLD', 3, 52079),
    ('10:13', 'BOT', 1, 52121), ('10:13', 'BOT', 3, 52121),
    ('10:16', 'SLD', 3, 52102), ('10:16', 'SLD', 1, 52102),
    ('10:17', 'BOT', 4, 52155),
    ('10:27', 'SLD', 2, 52173), ('10:27', 'SLD', 1, 52173), ('10:27', 'SLD', 1, 52173),
    ('10:37', 'BOT', 3, 52153), ('10:37', 'BOT', 1, 52153),
    ('10:40', 'SLD', 3, 52110), ('10:40', 'SLD', 1, 52108),
    ('10:49', 'BOT', 3, 52127), ('10:49', 'BOT', 1, 52127),
    ('11:07', 'SLD', 4, 52136),
    ('11:19', 'BOT', 1, 52068), ('11:36', 'BOT', 2, 52098), ('11:36', 'BOT', 1, 52098),
    ('11:58', 'SLD', 1, 52154),
    ('13:18', 'SLD', 1, 52223), ('13:18', 'SLD', 2, 52223),
    ('13:22', 'BOT', 2, 52246), ('13:22', 'BOT', 2, 52246),
    ('13:30', 'SLD', 2, 52238), ('13:30', 'SLD', 2, 52235),
    ('13:35', 'BOT', 2, 52254), ('13:35', 'BOT', 2, 52254),
    ('13:52', 'SLD', 1, 52221), ('13:52', 'SLD', 3, 52221),
    ('13:56', 'BOT', 1, 52178), ('13:59', 'BOT', 3, 52185),
    ('14:08', 'SLD', 3, 52156), ('14:08', 'SLD', 1, 52155),
    ('14:41', 'BOT', 1, 52096), ('14:51', 'BOT', 3, 52087),
    ('15:06', 'SLD', 1, 52146), ('16:58', 'SLD', 1, 52122),
]

# === JUNE 24 FILLS ===
fills_0624 = [
    ('10:22', 'BOT', 2, 52256),
    ('10:25', 'SLD', 1, 52286),
    ('10:34', 'SLD', 1, 52306), ('10:34', 'SLD', 1, 52306), ('10:34', 'SLD', 1, 52306),
    ('10:44', 'BOT', 2, 52298), ('10:44', 'BOT', 1, 52298), ('10:44', 'BOT', 1, 52298),
    ('10:45', 'SLD', 1, 52354),
    ('10:47', 'SLD', 1, 52394), ('10:47', 'SLD', 1, 52394), ('10:47', 'SLD', 1, 52394),
    ('10:51', 'BOT', 4, 52403),
    ('10:57', 'SLD', 1, 52478),
    ('11:01', 'SLD', 3, 52502),
    ('11:11', 'BOT', 1, 52513), ('11:11', 'BOT', 1, 52513), ('11:11', 'BOT', 2, 52513),
    ('11:13', 'SLD', 4, 52479),
    ('11:17', 'BOT', 4, 52538),
    ('11:21', 'SLD', 1, 52590),
    ('11:39', 'SLD', 1, 52640), ('11:39', 'SLD', 2, 52640),
    ('11:46', 'BOT', 1, 52590),
    ('11:51', 'BOT', 3, 52614),
    ('12:01', 'SLD', 3, 52555), ('12:01', 'SLD', 1, 52555),
    ('12:16', 'BOT', 3, 52572), ('12:16', 'BOT', 1, 52572),
    ('12:19', 'SLD', 4, 52551),
    ('12:23', 'BOT', 1, 52588), ('12:23', 'BOT', 1, 52588), ('12:23', 'BOT', 2, 52588),
    ('12:38', 'SLD', 2, 52547), ('12:38', 'SLD', 2, 52547),
    ('12:44', 'BOT', 1, 52494),
    ('13:34', 'BOT', 3, 52227),
    ('13:56', 'SLD', 1, 52280),
]

# Compute
pl_0623, open_l_23, open_s_23 = fifo_pl(fills_0623)
pl_0624, open_l_24, open_s_24 = fifo_pl(fills_0624)

# Run backtests
bt_0623, bt_trades_0623 = run_backtest_day("2026-06-23")
bt_0624, bt_trades_0624 = run_backtest_day("2026-06-24")

print("=" * 70)
print("P/L SUMMARY")
print("=" * 70)
print(f"\n{'Date':<12} {'IB Fills P/L':>14} {'Backtest P/L':>14} {'Slippage':>10} {'Open Pos':>10}")
print("-" * 70)
print(f"{'06/23':<12} {pl_0623:>+14.0f} {bt_0623:>+14.0f} {bt_0623-pl_0623:>+10.0f} {'flat':>10}")
print(f"{'06/24':<12} {pl_0624:>+14.0f} {bt_0624 if bt_0624 else 'N/A':>14} {(bt_0624-pl_0624) if bt_0624 else 0:>+10.0f} {'L'+str(open_l_24) if open_l_24 else 'S'+str(open_s_24) if open_s_24 else 'flat':>10}")
print("-" * 70)
print(f"{'TOTAL':<12} {pl_0623+pl_0624:>+14.0f} {(bt_0623 or 0)+(bt_0624 or 0):>+14.0f}")

# Trade comparison
print("\n" + "=" * 70)
print("TRADE COMPARISON: 06/23")
print("=" * 70)

# IB signal trades (from log signals)
ib_signals_0623 = [
    ("09:33", "SELL", 51758), ("09:38", "BUY", 51791), ("09:42", "SELL", 51932),
    ("09:45", "BUY", 51942), ("09:50", "SELL", 52077), ("09:54", "BUY", 51975),
    ("09:55", "SELL", 51938), ("10:00", "BUY", 51948), ("10:09", "SELL", 52068),
    ("10:12", "BUY", 52127), ("10:15", "SELL", 52100), ("10:16", "BUY", 52155),
    ("10:26", "SELL", 52164), ("10:36", "BUY", 52141), ("10:39", "SELL", 52100),
    ("10:48", "BUY", 52119), ("11:06", "SELL", 52140), ("11:35", "BUY", 52098),
    ("13:17", "SELL", 52221), ("13:21", "BUY", 52252), ("13:29", "SELL", 52236),
    ("13:34", "BUY", 52248), ("13:51", "SELL", 52228), ("13:58", "BUY", 52180),
    ("14:07", "SELL", 52159), ("14:50", "BUY", 52089),
]

ib_signals_0624 = [
    ("10:21", "BUY", 52239), ("10:33", "SELL", 52300), ("10:43", "BUY", 52290),
    ("10:46", "SELL", 52398), ("10:50", "BUY", 52411), ("11:00", "SELL", 52502),
    ("11:10", "BUY", 52504), ("11:12", "SELL", 52478), ("11:16", "BUY", 52537),
    ("11:38", "SELL", 52642), ("11:50", "BUY", 52608), ("12:00", "SELL", 52556),
    ("12:15", "BUY", 52581), ("12:18", "SELL", 52554), ("12:22", "BUY", 52585),
    ("12:37", "SELL", 52551), ("13:33", "BUY", 52218),
]

print(f"\n{'#':<3} {'Time':<6} {'IB Signal':<12} {'Algo Signal':<15} {'Match':<6}")
print("-" * 50)
for i, (t, sig, p) in enumerate(ib_signals_0623):
    if i < len(bt_trades_0623):
        at, asig, ap = bt_trades_0623[i]
        match = "YES" if sig == asig and at == t else f"time:{at}" if sig == asig else "NO"
        print(f"{i+1:<3} {t:<6} {sig+' @'+str(p):<12} {asig+' @'+str(int(ap)):<15} {match:<6}")
    else:
        print(f"{i+1:<3} {t:<6} {sig+' @'+str(p):<12} {'---':<15} {'EXTRA':<6}")

print(f"\nIB signals: {len(ib_signals_0623)}, Algo trades: {len(bt_trades_0623)}")

print("\n" + "=" * 70)
print("TRADE COMPARISON: 06/24")
print("=" * 70)
print(f"\n{'#':<3} {'Time':<6} {'IB Signal':<12} {'Algo Signal':<15} {'Match':<6}")
print("-" * 50)
for i, (t, sig, p) in enumerate(ib_signals_0624):
    if i < len(bt_trades_0624):
        at, asig, ap = bt_trades_0624[i]
        match = "YES" if sig == asig and at == t else f"time:{at}" if sig == asig else "NO"
        print(f"{i+1:<3} {t:<6} {sig+' @'+str(p):<12} {asig+' @'+str(int(ap)):<15} {match:<6}")
    else:
        print(f"{i+1:<3} {t:<6} {sig+' @'+str(p):<12} {'---':<15} {'EXTRA':<6}")

# Check if algo has extra trades not in IB
if len(bt_trades_0624) > len(ib_signals_0624):
    for i in range(len(ib_signals_0624), len(bt_trades_0624)):
        at, asig, ap = bt_trades_0624[i]
        print(f"{i+1:<3} {'---':<6} {'---':<12} {asig+' @'+str(int(ap)):<15} {'MISSED':<6}")

print(f"\nIB signals: {len(ib_signals_0624)}, Algo trades: {len(bt_trades_0624)}")
print(f"Note: 06/24 Fred started late at 10:12 (missed 09:30-10:12 window)")
