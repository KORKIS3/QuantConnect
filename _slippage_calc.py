"""Calculate slippage: algo signal prices vs actual IB execution prices for 6/23."""

# Algo signal prices (from backtest with live config) matched to
# IB actual execution prices (from execDetails in IB log).
#
# Signal trades only (excluding PARTIAL_TP and EOD flatten for clarity)

trades = [
    # (time, signal, algo_price, ib_exec_price)
    ("09:33", "SELL", 51758, 51771),    # initial entry
    ("09:38", "BUY",  51791, 51804),    # reverse
    ("09:42", "SELL", 51932, 51917),    # reverse
    ("09:45", "BUY",  51942, 51939),    # reverse
    ("09:50", "SELL", 52077, 52075),    # reverse
    ("09:54", "BUY",  51975, 51963),    # reverse
    ("09:55", "SELL", 51938, 51934),    # reverse
    ("10:00", "BUY",  51948, 51962),    # reverse
    ("10:09", "SELL", 52068, 52079),    # reverse
    ("10:12", "BUY",  52127, 52121),    # reverse
    ("10:15", "SELL", 52100, 52102),    # reverse
    ("10:16", "BUY",  52155, 52155),    # reverse
    ("10:26", "SELL", 52164, 52173),    # reverse
    ("10:36", "BUY",  52141, 52153),    # reverse
    ("10:39", "SELL", 52100, 52109),    # reverse (avg of 52110, 52108)
    ("10:48", "BUY",  52119, 52127),    # reverse
    ("11:06", "SELL", 52140, 52136),    # reverse
    ("11:35", "BUY",  52098, 52098),    # reverse
    ("13:17", "SELL", 52221, 52223),    # reverse
    ("13:21", "BUY",  52252, 52246),    # reverse
    ("13:29", "SELL", 52236, 52236),    # reverse (avg 52238, 52235 = 52236.5)
    ("13:34", "BUY",  52248, 52254),    # reverse
    ("13:51", "SELL", 52228, 52221),    # reverse
    ("13:58", "BUY",  52180, 52185),    # reverse
    ("14:07", "SELL", 52159, 52156),    # reverse (avg 52156, 52155)
    ("14:50", "BUY",  52089, 52087),    # reverse
]

print(f"{'Time':<6} {'Sig':<5} {'Algo':>7} {'IB':>7} {'Slip':>6} {'Dir':<9}")
print("-" * 50)

total_slip = 0
adverse_count = 0
favorable_count = 0
worst = 0
worst_trade = ""

for time, sig, algo, ib in trades:
    if sig == "BUY":
        slip = ib - algo   # positive = paid more = adverse
    else:
        slip = algo - ib   # positive = sold lower = adverse
    
    total_slip += slip
    if slip > 0.5:
        direction = "ADVERSE"
        adverse_count += 1
    elif slip < -0.5:
        direction = "FAVORABLE"
        favorable_count += 1
    else:
        direction = "~ZERO"
    
    if slip > worst:
        worst = slip
        worst_trade = f"{time} {sig}"
    
    print(f"{time:<6} {sig:<5} {algo:>7} {ib:>7} {slip:>+6.0f} {direction:<9}")

print("-" * 50)
print(f"\nSignal trades: {len(trades)}")
print(f"Total slippage: {total_slip:+.0f} pts")
print(f"Avg per trade: {total_slip/len(trades):+.1f} pts")
print(f"Adverse: {adverse_count} trades")
print(f"Favorable: {favorable_count} trades")
print(f"Zero: {len(trades) - adverse_count - favorable_count} trades")
print(f"Worst: {worst_trade} ({worst:+.0f} pts)")
print(f"\nBacktest P/L: 784 pts")
print(f"Slippage impact: {total_slip:.0f} pts")
print(f"Expected live: {784 - total_slip:.0f} pts")
print(f"Actual live (IB): 661 pts")
print(f"Remaining gap: {784 - total_slip - 661:.0f} pts (TP fill differences + EOD)")
