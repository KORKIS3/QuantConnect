"""Compare Algo signal prices vs IB fill prices with running P/L for both.
Uses actual IB fill prices and quantities from execDetails (final cumQty per orderId).
"""
import re

log_path = r'C:\Users\Administrator\Desktop\IB_Live\logs\fred_ib_DUO158495_20260610_0956.log'

order_signal = re.compile(r'(\d{2}:\d{2}:\d{2}).*\[ORDER\]\s+MARKET\s+(\w+)\s+\(signal=([\d.]+)\)')
order_placed = re.compile(r'(\d{2}:\d{2}:\d{2}).*\[ORDER placed\]\s+(\S+)\s+qty=(\d+).*orderId=(\d+)')
pos_sync = re.compile(r'(\d{2}:\d{2}:\d{2}).*\[PositionSync\] IB fill confirmed: _ib_position (\S+) -> (\S+)')
exec_detail = re.compile(r"execDetails.*?side='(\w+)'.*?price=([\d.]+).*?orderId=(\d+).*?cumQty=([\d.]+).*?avgPrice=([\d.]+)")

signals_list = []
placed_orders = []
position_syncs = []
execs_by_order = {}

with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
    for line in f:
        m = exec_detail.search(line)
        if m:
            side, price, oid, cumqty, avgprice = m.groups()
            oid_i = int(oid)
            cq = float(cumqty)
            if oid_i not in execs_by_order or cq > execs_by_order[oid_i]['cum_qty']:
                execs_by_order[oid_i] = {'side': side, 'price': float(avgprice), 'cum_qty': cq}
        m2 = order_signal.search(line)
        if m2:
            signals_list.append({'time': m2.group(1), 'side': m2.group(2), 'price': float(m2.group(3))})
        m3 = order_placed.search(line)
        if m3:
            placed_orders.append({'time': m3.group(1), 'tag': m3.group(2), 'qty': int(m3.group(3)), 'orderId': int(m3.group(4))})
        m4 = pos_sync.search(line)
        if m4:
            position_syncs.append({'time': m4.group(1), 'from': int(m4.group(2)), 'to': int(m4.group(3))})

sig_idx = 0
trades = []
for p in placed_orders:
    oid = p['orderId']
    ip = execs_by_order[oid]['price'] if oid in execs_by_order else 0.0
    iq = int(execs_by_order[oid]['cum_qty']) if oid in execs_by_order else p['qty']
    iside = execs_by_order[oid]['side'] if oid in execs_by_order else ''
    ap = None
    aside = None
    if p['tag'] in ('BUY', 'SELL') and sig_idx < len(signals_list):
        if signals_list[sig_idx]['time'] <= p['time']:
            ap = signals_list[sig_idx]['price']
            aside = signals_list[sig_idx]['side']
            sig_idx += 1
    trades.append({'time': p['time'], 'tag': p['tag'], 'aside': aside, 'ap': ap,
                   'iside': iside, 'ip': ip, 'iq': iq})

# P/L calculation
algo_pos = 0; algo_entry = 0.0; algo_pl = 0.0
ib_pos = 0; ib_entry = 0.0; ib_pl = 0.0

header = f"{'TIME':<9}{'TYPE':<12}{'ALGO SIGNAL':<16}{'IB FILL':<16}{'ALGO P/L':<11}{'IB P/L':<11}{'SLIP':<6}"
print(header)
print('-' * 85)

for t in trades:
    ap, ip, tag, iq, iside = t['ap'], t['ip'], t['tag'], t['iq'], t['iside']

    # ALGO P/L (2-contract system)
    if tag == 'BUY' and ap:
        if algo_pos < 0:
            algo_pl += (algo_entry - ap) * abs(algo_pos)
        algo_pos = 2; algo_entry = ap
    elif tag == 'SELL' and ap:
        if algo_pos > 0:
            algo_pl += (ap - algo_entry) * algo_pos
        algo_pos = -2; algo_entry = ap
    elif tag == 'PARTIAL_TP':
        if algo_pos > 0:
            algo_pl += (ip - algo_entry) * 1
            algo_pos = 1
        elif algo_pos < 0:
            algo_pl += (algo_entry - ip) * 1
            algo_pos = -1
    elif tag == 'LIQUIDATE':
        if algo_pos > 0:
            algo_pl += (ip - algo_entry) * abs(algo_pos)
        elif algo_pos < 0:
            algo_pl += (algo_entry - ip) * abs(algo_pos)
        algo_pos = 0

    # IB P/L (actual fill quantities)
    if iside == 'BOT':
        if ib_pos < 0:
            contracts_closed = min(abs(ib_pos), iq)
            ib_pl += (ib_entry - ip) * contracts_closed
            ib_pos += iq
            if ib_pos > 0:
                ib_entry = ip
            elif ib_pos == 0:
                ib_entry = 0.0
        elif ib_pos >= 0:
            if ib_pos == 0:
                ib_entry = ip
            ib_pos += iq
    elif iside == 'SLD':
        if ib_pos > 0:
            contracts_closed = min(ib_pos, iq)
            ib_pl += (ip - ib_entry) * contracts_closed
            ib_pos -= iq
            if ib_pos < 0:
                ib_entry = ip
            elif ib_pos == 0:
                ib_entry = 0.0
        elif ib_pos <= 0:
            if ib_pos == 0:
                ib_entry = ip
            ib_pos -= iq

    slip = ''
    if ap and ip:
        slip = f'{ip - ap:+.0f}' if iside == 'BOT' else f'{ap - ip:+.0f}'
    a_str = f'{t["aside"] or ""} {ap:.0f}' if ap else ''
    i_str = f'{iside} {iq}x{ip:.0f}'
    print(f"{t['time']:<9}{tag:<12}{a_str:<16}{i_str:<16}{algo_pl:<+11.0f}{ib_pl:<+11.0f}{slip:<6}")

print('-' * 85)
print(f"\nALGO P/L:  {algo_pl:+.0f} pts  (final pos: {algo_pos})")
print(f"IB P/L:    {ib_pl:+.0f} pts  (final pos: {ib_pos})")
print(f"DIFF:      {ib_pl - algo_pl:+.0f} pts")
