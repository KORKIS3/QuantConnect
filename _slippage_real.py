"""Compute exact P/L from all IB execution fills using FIFO matching."""
from collections import deque

fills = [
    # (time, side, qty, price) - from execDetails in IB log
    ('09:34', 'SLD', 2, 51771),
    ('09:36', 'BOT', 1, 51707),
    ('09:39', 'BOT', 1, 51804),
    ('09:39', 'BOT', 1, 51804),
    ('09:39', 'BOT', 1, 51804),
    ('09:42', 'SLD', 1, 51868),
    ('09:43', 'SLD', 3, 51917),
    ('09:46', 'BOT', 1, 51939),
    ('09:46', 'BOT', 1, 51939),
    ('09:46', 'BOT', 1, 51939),
    ('09:46', 'BOT', 1, 51939),
    ('09:48', 'SLD', 1, 52011),
    ('09:51', 'SLD', 2, 52075),
    ('09:51', 'SLD', 1, 52075),
    ('09:53', 'BOT', 1, 52018),
    ('09:55', 'BOT', 1, 51963),
    ('09:55', 'BOT', 1, 51963),
    ('09:55', 'BOT', 1, 51963),
    ('09:56', 'SLD', 4, 51934),
    ('10:01', 'BOT', 1, 51962),
    ('10:01', 'BOT', 1, 51962),
    ('10:01', 'BOT', 2, 51962),
    ('10:04', 'SLD', 1, 52021),
    ('10:10', 'SLD', 3, 52079),
    ('10:13', 'BOT', 1, 52121),
    ('10:13', 'BOT', 3, 52121),
    ('10:16', 'SLD', 3, 52102),
    ('10:16', 'SLD', 1, 52102),
    ('10:17', 'BOT', 4, 52155),
    ('10:27', 'SLD', 2, 52173),
    ('10:27', 'SLD', 1, 52173),
    ('10:27', 'SLD', 1, 52173),
    ('10:37', 'BOT', 3, 52153),
    ('10:37', 'BOT', 1, 52153),
    ('10:40', 'SLD', 3, 52110),
    ('10:40', 'SLD', 1, 52108),
    ('10:49', 'BOT', 3, 52127),
    ('10:49', 'BOT', 1, 52127),
    ('11:07', 'SLD', 4, 52136),
    ('11:19', 'BOT', 1, 52068),
    ('11:36', 'BOT', 2, 52098),
    ('11:36', 'BOT', 1, 52098),
    ('11:58', 'SLD', 1, 52154),
    ('13:18', 'SLD', 1, 52223),
    ('13:18', 'SLD', 2, 52223),
    ('13:22', 'BOT', 2, 52246),
    ('13:22', 'BOT', 2, 52246),
    ('13:30', 'SLD', 2, 52238),
    ('13:30', 'SLD', 2, 52235),
    ('13:35', 'BOT', 2, 52254),
    ('13:35', 'BOT', 2, 52254),
    ('13:52', 'SLD', 1, 52221),
    ('13:52', 'SLD', 3, 52221),
    ('13:56', 'BOT', 1, 52178),
    ('13:59', 'BOT', 3, 52185),
    ('14:08', 'SLD', 3, 52156),
    ('14:08', 'SLD', 1, 52155),
    ('14:41', 'BOT', 1, 52096),
    ('14:51', 'BOT', 3, 52087),
    ('15:06', 'SLD', 1, 52146),
    # EOD flatten
    ('16:58', 'SLD', 1, 52122),
]

# FIFO P/L
long_entries = deque()
short_entries = deque()
realized_pl_pts = 0.0
trade_log = []

for time, side, qty, price in fills:
    remaining = qty
    if side == 'BOT':
        while remaining > 0 and short_entries:
            entry_qty, entry_price = short_entries[0]
            close_qty = min(remaining, entry_qty)
            pl = (entry_price - price) * close_qty
            realized_pl_pts += pl
            trade_log.append((time, 'BOT', close_qty, price, entry_price, pl))
            remaining -= close_qty
            if close_qty == entry_qty:
                short_entries.popleft()
            else:
                short_entries[0] = (entry_qty - close_qty, entry_price)
        if remaining > 0:
            long_entries.append((remaining, price))
    elif side == 'SLD':
        while remaining > 0 and long_entries:
            entry_qty, entry_price = long_entries[0]
            close_qty = min(remaining, entry_qty)
            pl = (price - entry_price) * close_qty
            realized_pl_pts += pl
            trade_log.append((time, 'SLD', close_qty, price, entry_price, pl))
            remaining -= close_qty
            if close_qty == entry_qty:
                long_entries.popleft()
            else:
                long_entries[0] = (entry_qty - close_qty, entry_price)
        if remaining > 0:
            short_entries.append((remaining, price))

print("=== FIFO P/L FROM ACTUAL IB EXECUTIONS (6/23) ===\n")
print(f"{'Time':<6} {'Side':<4} {'Qty':>3} {'Exit':>7} {'Entry':>7} {'P/L':>7}")
print("-" * 45)
for time, side, qty, exit_p, entry_p, pl in trade_log:
    print(f"{time:<6} {side:<4} {qty:>3} {exit_p:>7} {entry_p:>7} {pl:>+7.0f}")

print("-" * 45)
print(f"\nTotal realized P/L (IB fills): {realized_pl_pts:+.0f} pts")
print(f"Total realized USD:            ${realized_pl_pts * 5:+,.0f}")
print(f"Open longs remaining:          {sum(q for q,p in long_entries)}")
print(f"Open shorts remaining:         {sum(q for q,p in short_entries)}")
print(f"\n--- COMPARISON ---")
print(f"Algo backtest P/L:  784 pts")
print(f"IB execution P/L:   {realized_pl_pts:+.0f} pts")
print(f"Gap:                {784 - realized_pl_pts:+.0f} pts")
