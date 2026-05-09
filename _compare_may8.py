"""Compare May 8th backtest vs actual IB fills."""
import pandas as pd
from datetime import datetime

print("=" * 100)
print("MAY 8TH 2026 — ALGO BACKTEST vs ACTUAL IB FILLS")
print("=" * 100)

# ALGO BACKTEST (what should have happened)
print("\n### ALGO BACKTEST (what should have happened) ###")
print("Final P/L: +231 pts ($1,155)")
print("\nTrades:")
algo_trades = [
    ("09:45", "SELL", 49759, "short", 0.00),
    ("10:40", "SELL", 49852, "flat", 75.00),   # liquidation, partial TP
    ("10:50", "SELL", 49789, "short", 75.00),
    ("11:32", "BUY", 49701, "flat", 215.00),   # liquidation
    ("11:43", "SELL", 49716, "short", 215.00),
    ("11:47", "BUY", 49745, "long", 186.00),   # reversal
    ("14:47", "SELL", 49647, "short", 88.00),  # reversal
    ("15:37", "BUY", 49683, "long", 109.00),   # reversal
    ("16:54", "SELL", 49744, "flat", 231.00),  # session end flatten
]
for time, side, price, pos, pl in algo_trades:
    print(f"  {time} {side:4s} @ {price} → {pos:5s}, session_pl={pl:+.2f}")

# ACTUAL IB FILLS (what really happened)
print("\n\n### ACTUAL IB FILLS (what really happened) ###")
print("Note: Times shown are ET (log line timestamp when Fred received the fill)")
print("\nPre-Fred manual trades (clientId 98, 99):")
manual_fills = [
    ("11:27", "BUY", 2, 49929, 99, "manual"),
    ("11:27", "SELL", 2, 49801, 98, "manual"),
    ("11:27", "SELL", 2, 49851, 1, "Fred"),
    ("11:27", "BUY", 4, 49802, 99, "manual"),
]
for time, side, qty, price, cid, who in manual_fills:
    print(f"  {time} {side:4s} {qty} @ {price} (clientId={cid}) [{who}]")

print("\nFred's trades after startup:")
fred_fills = [
    ("11:33", "BUY", 2, 49704, 1),
    ("11:44", "SELL", 4, 49715, 1),  # 3 fills: 1+1+2
    ("12:00", "BUY", 4, 49755, 1),   # 2 fills: 2+2
    ("14:48", "SELL", 4, 49642, 1),
    ("14:56", "BUY", 1, 49594, 1),   # partial TP
    ("15:38", "BUY", 3, 49681, 1),
    ("16:55", "SELL", 4, 49746, 1),  # 2 fills: 2+2 (session end)
    ("16:55", "BUY", 2, 49751, 1),   # mystery trade
]
for time, side, qty, price, cid in fred_fills:
    print(f"  {time} {side:4s} {qty} @ {price} (clientId={cid})")

# ANALYSIS
print("\n\n### POSITION TRACKING ANALYSIS ###")
print("\nFred's internal position tracker got out of sync due to manual trades (clientId 98, 99)")
print("before Fred started. Fred didn't know about these fills, so his _ib_position was wrong.")
print("\nTimeline:")
print("  11:27 AM: Manual trades executed BEFORE Fred started")
print("            - BUY 2 @ 49929 (cid=99)")
print("            - SELL 2 @ 49801 (cid=98)")
print("            - Fred SELL 2 @ 49851 (cid=1)")
print("            - BUY 4 @ 49802 (cid=99)")
print("            → Actual IB position: +4 long")
print("            → Fred thought: -2 short (only knew about his own SELL 2)")
print("")
print("  11:33 AM: Fred BUY 2 @ 49704")
print("            → Fred thought: -2 → flat (liquidation)")
print("            → Actually: +4 → +6 long")
print("")
print("  11:44 AM: Fred SELL 4 @ 49715")
print("            → Fred thought: flat → -2 short (new position)")
print("            → Actually: +6 → +2 long")
print("")
print("  12:00 PM: Fred BUY 4 @ 49755")
print("            → Fred thought: -2 → +2 long (reversal)")
print("            → Actually: +2 → +6 long")
print("")
print("  And so on... position stayed out of sync all day")
print("")
print("  16:55 PM: Fred SELL 4 @ 49746 (session end flatten)")
print("            → Fred thought: +2 → flat")
print("            → Actually: +6 → +2 long (still not flat!)")
print("")
print("  16:55 PM: Fred BUY 2 @ 49751 (mystery trade)")
print("            → Unknown reason, possibly another flatten attempt")
print("            → Actually: +2 → +4 long")

print("\n\n### ROOT CAUSE ###")
print("Manual trades with different clientIds (98, 99) before Fred started threw off")
print("Fred's internal position tracker. Fred only tracks fills from his own clientId (1).")
print("\nThe liquidation bug (fixed yesterday) made it worse by placing orders in the")
print("wrong direction, but the root cause was position sync at startup.")

print("\n\n### SOLUTION ###")
print("1. Fred needs to query actual IB position on startup and sync _ib_position")
print("2. Fred should reconcile position before each trade (safety check)")
print("3. Never place manual trades while Fred is running or about to start")
print("4. If manual trades are needed, restart Fred after to force position sync")

print("\n" + "=" * 100)
