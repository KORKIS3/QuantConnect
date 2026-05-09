import asyncio
asyncio.set_event_loop(asyncio.new_event_loop())

from ib_insync import IB, Future

ib = IB()
print('Attempting to connect to IB Gateway...')
print('Trying port 4002 (paper trading)...')
try:
    ib.connect('127.0.0.1', 4002, clientId=50)
    print('Connected to port 4002')
except Exception as e:
    print(f'Port 4002 failed: {e}')
    print('Trying port 4001 (live trading)...')
    try:
        ib.connect('127.0.0.1', 4001, clientId=50)
        print('Connected to port 4001')
    except Exception as e2:
        print(f'Port 4001 failed: {e2}')
        print('Could not connect to IB Gateway')
        exit(1)

contract = Future('MYM', '20260618', 'CBOT')
ib.qualifyContracts(contract)

positions = ib.positions()
print('=== IB CONNECTION STATUS ===')
print('Connected:', ib.isConnected())

print('\n=== POSITIONS ===')
mym_pos = [p for p in positions if 'MYM' in p.contract.symbol]
if mym_pos:
    print(f'MYM Position: {mym_pos[0].position} contracts @ avg cost {mym_pos[0].avgCost}')
else:
    print('MYM Position: FLAT (0 contracts)')

print('\n=== ACCOUNT ===')
account_values = ib.accountValues()
pnl = [v for v in account_values if v.tag == 'RealizedPnL' and v.currency == 'USD']
if pnl:
    print(f'Realized P/L: ${pnl[0].value}')

ib.disconnect()
