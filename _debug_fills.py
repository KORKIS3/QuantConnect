import os, re
import pandas as pd
import pytz
_EST = pytz.timezone('US/Eastern')
log_path = os.path.expanduser('~/Desktop/IB_Live/logs/fred_ib_20260430.log')
log = open(log_path, encoding='utf-8', errors='ignore').read()
pattern = r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*?execDetails Execution\(execId='([^']+)'.*?side='(BOT|SLD)', shares=([\d.]+), price=([\d.]+).*?clientId=1,"
rows = {}
for m in re.finditer(pattern, log):
    eid = m.group(2)
    if eid in rows: continue
    side = 'BUY' if m.group(3) == 'BOT' else 'SELL'
    ts = pd.Timestamp(m.group(1), tz=_EST)
    rows[eid] = {'ts': ts, 'side': side, 'qty': float(m.group(4)), 'price': float(m.group(5))}
fills = pd.DataFrame(rows.values()).sort_values('ts').reset_index(drop=True)
pos = 0; ep = 0.0; realized = 0.0
print(f"{'Time':<8} {'Side':<5} {'Qty':>3}  {'Price':>6}  {'Pos':>4}  {'Realized':>8}")
print('-'*50)
for _, r in fills.iterrows():
    qty, price, side = r['qty'], r['price'], r['side']
    if side == 'BUY':
        if pos < 0:
            cq = min(qty, abs(pos)); realized += (ep - price) * cq; pos += cq; qty -= cq
        if qty > 0:
            ep = (ep * pos + price * qty) / (pos + qty) if pos + qty > 0 else price; pos += qty
    else:
        if pos > 0:
            cq = min(qty, pos); realized += (price - ep) * cq; pos -= cq; qty -= cq
        if qty > 0:
            ep = (ep * abs(pos) + price * qty) / (abs(pos) + qty) if abs(pos) + qty > 0 else price; pos -= qty
    t = r['ts'].strftime('%H:%M')
    print(f"{t:<8} {side:<5} {int(r['qty']):>3}  {price:>6.0f}  {pos:>+4.0f}  {realized:>+8.1f}")
print(f"\nFinal pos: {pos:+.0f}  Realized: {realized:+.1f} pts")
