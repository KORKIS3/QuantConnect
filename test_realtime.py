"""
Quick test: connect to IB Gateway on port 4002 and print real-time 5-second bars.
Usage: python test_realtime.py
"""
from ib_insync import *
import sys

def on_bar(bars, hasNewBar):
    if hasNewBar:
        b = bars[-1]
        print(f"  BAR {b.time}  O={b.open_}  H={b.high}  L={b.low}  C={b.close}  V={b.volume}")

def on_error(reqId, errorCode, errorString, *args):
    print(f"  [ERR {errorCode}] {errorString}")

ib = IB()
ib.RequestTimeout = 30  # increase from default 4s to avoid reqExecutions timeout
ib.errorEvent += on_error

print("Connecting to 127.0.0.1:4002 ...")
try:
    ib.connect("127.0.0.1", 4002, clientId=10, timeout=30)
except Exception as e:
    print(f"FAILED to connect: {e}")
    sys.exit(1)

print(f"Connected. Accounts: {ib.managedAccounts()}")

contract = Future("MYM", "20260618", "CBOT")
ib.qualifyContracts(contract)
print(f"Contract: {contract.localSymbol} (conId={contract.conId})")

print("Subscribing to real-time bars... (Ctrl+C to stop)\n")
bars = ib.reqRealTimeBars(contract, 5, "TRADES", False)
bars.updateEvent += on_bar

try:
    ib.run()
except KeyboardInterrupt:
    pass
finally:
    print("\nDisconnecting...")
    ib.cancelRealTimeBars(bars)
    ib.disconnect()
    print("Done.")
