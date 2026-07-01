"""Compare IB live signals vs algo backtest for 06/23 and 06/24."""
import pandas as pd, pytz, os
from TradingAlgoFast import AlgoConfig, run_trading_algo_fast

config = AlgoConfig(
    warmup_minutes=7, steep_angle_threshold=90.0, proximity_points=4.0,
    min_reversal_minutes=0, min_entry_angle=0.0, partial_tp_pts=50.0,
    spike_profit_pts=100.0, spike_profit_bars=9, wm_shield_distance=0.0,
    swing_anchor_threshold=10.0, num_contracts=2, cushion_points=0.0, limit_expiry_bars=5,
)
EST = pytz.timezone("US/Eastern")

def run_bt(date_str, start="09:30"):
    fpath = os.path.expanduser(f"~/Desktop/2YearsData/full_day/CBOT_MINI_YM1_{date_str}.csv")
    df = pd.read_csv(fpath, index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index, utc=True).tz_convert(EST)
    day_start = pd.Timestamp(f"{date_str} {start}", tz=EST)
    day_end = pd.Timestamp(f"{date_str} 16:59", tz=EST)
    day_data = df[(df.index >= day_start) & (df.index <= day_end)]
    algo_df = run_trading_algo_fast(day_data, date_str, start, "17:00", config=config)
    trades = []
    for idx, row in algo_df.iterrows():
        if row["signal"] in ("BUY", "SELL"):
            sig = row["signal"]
            price = row["buy_price"] if sig == "BUY" else row["sell_price"]
            trades.append((idx.strftime("%H:%M"), sig, int(price)))
    return float(algo_df["session_pl"].iloc[-1]), trades

# 06/23 IB signals (from log)
ib_0623 = [
    ("09:33","SELL",51758),("09:38","BUY",51791),("09:42","SELL",51932),
    ("09:45","BUY",51942),("09:50","SELL",52077),("09:54","BUY",51975),
    ("09:55","SELL",51938),("10:00","BUY",51948),("10:09","SELL",52068),
    ("10:12","BUY",52127),("10:15","SELL",52100),("10:16","BUY",52155),
    ("10:26","SELL",52164),("10:36","BUY",52141),("10:39","SELL",52100),
    ("10:48","BUY",52119),("11:06","SELL",52140),("11:35","BUY",52098),
    ("13:17","SELL",52221),("13:21","BUY",52252),("13:29","SELL",52236),
    ("13:34","BUY",52248),("13:51","SELL",52228),("13:58","BUY",52180),
    ("14:07","SELL",52159),("14:50","BUY",52089),
]

# 06/24 IB signals (from log - Fred started at 10:12)
ib_0624 = [
    ("10:21","BUY",52239),("10:33","SELL",52300),("10:43","BUY",52290),
    ("10:46","SELL",52398),("10:50","BUY",52411),("11:00","SELL",52502),
    ("11:10","BUY",52504),("11:12","SELL",52478),("11:16","BUY",52537),
    ("11:38","SELL",52642),("11:50","BUY",52608),("12:00","SELL",52556),
    ("12:15","BUY",52581),("12:18","SELL",52554),("12:22","BUY",52585),
    ("12:37","SELL",52551),("13:33","BUY",52218),
]

# Run backtests
pl_23, algo_23 = run_bt("2026-06-23")
pl_24, algo_24 = run_bt("2026-06-24", start="10:12")  # match Fred's late start

print("=" * 65)
print("P/L SUMMARY (from IB execution fills, FIFO)")
print("=" * 65)
print(f"  06/23: IB = +711 pts | Algo backtest = +{pl_23:.0f} pts | Gap = {pl_23-711:.0f} pts")
print(f"  06/24: IB = +502 pts | Algo backtest = +{pl_24:.0f} pts | Gap = {pl_24-502:.0f} pts")
print(f"  TOTAL: IB = +1213 pts ($6,065) | Algo = +{pl_23+pl_24:.0f} pts")

# Compare 06/23
print("\n" + "=" * 65)
print("06/23 TRADE COMPARISON")
print("=" * 65)
print(f"  IB: {len(ib_0623)} signals (includes warmup SELL@09:33)")
print(f"  Algo: {len(algo_23)} trades")
print()

# IB has extra initial SELL@09:33 that algo doesn't fire
# After that, they should match 1:1
print(f"  {'#':<3} {'IB':<20} {'Algo':<20} {'Match'}")
print(f"  {'-'*60}")
print(f"  1   SELL @51758 09:33  ---                  EXTRA (warmup)")

match_count = 0
for i, (at, asig, ap) in enumerate(algo_23):
    ib_idx = i + 1  # offset by 1 for the warmup signal
    if ib_idx < len(ib_0623):
        it, isig, ip = ib_0623[ib_idx]
        if it == at and isig == asig and ip == ap:
            status = "EXACT"
            match_count += 1
        elif isig == asig and ip == ap:
            status = f"time off ({it} vs {at})"
            match_count += 1
        else:
            status = f"DIFF: IB={isig}@{ip}"
    else:
        status = "NO IB MATCH"
    print(f"  {i+2:<3} {isig+' @'+str(ip)+' '+it:<20} {asig+' @'+str(ap)+' '+at:<20} {status}")

print(f"\n  Matched: {match_count}/{len(algo_23)} trades EXACT")

# Compare 06/24
print("\n" + "=" * 65)
print("06/24 TRADE COMPARISON (Fred started 10:12)")
print("=" * 65)
print(f"  IB: {len(ib_0624)} signals")
print(f"  Algo (from 10:12): {len(algo_24)} trades")
print()

print(f"  {'#':<3} {'IB':<20} {'Algo':<20} {'Match'}")
print(f"  {'-'*60}")

# Match by time proximity
algo_copy = list(algo_24)
match_count_24 = 0
for i, (it, isig, ip) in enumerate(ib_0624):
    best = None
    for j, (at, asig, ap) in enumerate(algo_copy):
        if isig == asig and at == it:
            best = (j, at, asig, ap)
            break
        # Allow 1 min tolerance
        ih = int(it.split(":")[0])*60 + int(it.split(":")[1])
        ah = int(at.split(":")[0])*60 + int(at.split(":")[1])
        if isig == asig and abs(ih - ah) <= 1:
            best = (j, at, asig, ap)
            break
    if best:
        j, at, asig, ap = best
        algo_copy.pop(j)
        if ip == ap:
            status = "EXACT"
        else:
            status = f"price: {ip} vs {ap}"
        match_count_24 += 1
        print(f"  {i+1:<3} {isig+' @'+str(ip)+' '+it:<20} {asig+' @'+str(ap)+' '+at:<20} {status}")
    else:
        print(f"  {i+1:<3} {isig+' @'+str(ip)+' '+it:<20} {'---':<20} NO ALGO MATCH")

if algo_copy:
    print(f"\n  Algo trades with no IB match:")
    for at, asig, ap in algo_copy:
        print(f"      {asig} @{ap} {at}")

print(f"\n  Matched: {match_count_24}/{len(ib_0624)} IB signals")
