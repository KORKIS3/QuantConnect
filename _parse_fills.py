import re

log_path = r'C:\Users\Administrator\Desktop\IB_Live\logs\fred_ib_20260427.log'
text = open(log_path, encoding='utf-8', errors='ignore').read()

pattern = r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*?execDetails Execution\(execId=\'([^\']+)\'.*?side=\'(BOT|SLD)\', shares=([\d.]+), price=([\d.]+).*?clientId=1,'
rows = {}
for m in re.finditer(pattern, text):
    eid = m.group(2)
    if eid in rows: continue
    side = 'BUY' if m.group(3) == 'BOT' else 'SELL'
    rows[eid] = (m.group(1), side, float(m.group(4)), float(m.group(5)))

if not rows:
    print('No fills found for clientId=1')
else:
    sorted_rows = sorted(rows.values(), key=lambda x: x[0])
    print(f'Found {len(sorted_rows)} fills on 2026-04-27:\n')
    print(f"{'Time':<22} {'Side':<6} {'Qty':>5} {'Price':>8}")
    print('-' * 45)
    pos = 0; ep = 0.0; total_pl = 0.0
    for ts, side, qty, price in sorted_rows:
        print(f"{ts:<22} {side:<6} {qty:>5.0f} {price:>8.0f}")
        if side == 'BUY':
            if pos < 0:
                pl = (ep - price) * min(qty, abs(pos))
                total_pl += pl
                print(f"  -> closed short: {pl:+.0f} pts")
            pos += qty; ep = price
        else:
            if pos > 0:
                pl = (price - ep) * min(qty, pos)
                total_pl += pl
                print(f"  -> closed long:  {pl:+.0f} pts")
            pos -= qty; ep = price
    print(f"\nTotal realized: {total_pl:+.0f} pts  /  ${total_pl*0.5:+,.2f} (MYM @$0.50/pt)")
