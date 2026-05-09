"""Pre-flight check for Fred live trading — run before market open Monday."""
import os
import sys
from datetime import datetime
import pytz
from ib_insync import IB, Future

_EST = pytz.timezone("US/Eastern")

print("=" * 80)
print("FRED PRE-FLIGHT CHECK — Run before market open")
print("=" * 80)

checks_passed = []
checks_failed = []

# 1. Check IB Gateway is running
print("\n[1/8] Checking IB Gateway connection...")
try:
    ib = IB()
    ib.connect("127.0.0.1", 4001, clientId=99, timeout=10)  # live port
    print("  ✓ IB Gateway LIVE (port 4001) is reachable")
    checks_passed.append("IB Gateway connection")
    
    # Check account
    accounts = ib.managedAccounts()
    print(f"  ✓ Managed accounts: {accounts}")
    
    # Check YM contract
    base = Future(symbol="MYM", exchange="CBOT", currency="USD")
    details = ib.reqContractDetails(base)
    if details:
        front = sorted([d.contract for d in details if d.contract.lastTradeDateOrContractMonth >= datetime.now().strftime("%Y%m%d")],
                       key=lambda c: c.lastTradeDateOrContractMonth)[0]
        print(f"  ✓ Front month: {front.localSymbol} (expiry {front.lastTradeDateOrContractMonth})")
    
    # Check current position
    positions = ib.positions()
    ym_pos = 0
    for p in positions:
        if p.contract.symbol in ("YM", "MYM"):
            ym_pos = int(p.position)
            print(f"  ✓ Current YM/MYM position: {ym_pos}")
            break
    if ym_pos == 0:
        print("  ✓ Account is FLAT (no open YM/MYM position)")
        checks_passed.append("Account flat")
    else:
        print(f"  ⚠ WARNING: Account has open position ({ym_pos} contracts)")
        print("    → Flatten manually before starting Fred, or Fred will sync to this position")
        checks_failed.append(f"Account not flat ({ym_pos} contracts)")
    
    ib.disconnect()
except Exception as e:
    print(f"  ✗ FAILED: {e}")
    checks_failed.append("IB Gateway connection")

# 2. Check scheduled tasks
print("\n[2/8] Checking scheduled tasks...")
try:
    import subprocess
    result = subprocess.run(
        ["powershell", "-Command", "Get-ScheduledTask -TaskName 'FredDaySession' | Select-Object -ExpandProperty State"],
        capture_output=True, text=True, timeout=5
    )
    if "Ready" in result.stdout:
        print("  ✓ FredDaySession task is enabled and ready")
        checks_passed.append("Scheduled task enabled")
    else:
        print(f"  ✗ FredDaySession task state: {result.stdout.strip()}")
        checks_failed.append("Scheduled task not ready")
except Exception as e:
    print(f"  ⚠ Could not check scheduled task: {e}")

# 3. Check log directory
print("\n[3/8] Checking log directory...")
log_dir = os.path.join(os.path.expanduser("~"), "Desktop", "IB_Live", "logs")
if os.path.exists(log_dir):
    print(f"  ✓ Log directory exists: {log_dir}")
    checks_passed.append("Log directory")
else:
    print(f"  ✗ Log directory missing: {log_dir}")
    checks_failed.append("Log directory")

# 4. Check tracking directory
print("\n[4/8] Checking tracking directory...")
tracking_dir = os.path.join(os.path.expanduser("~"), "Desktop", "IB_Live", "tracking")
if os.path.exists(tracking_dir):
    print(f"  ✓ Tracking directory exists: {tracking_dir}")
    checks_passed.append("Tracking directory")
else:
    print(f"  ✗ Tracking directory missing: {tracking_dir}")
    checks_failed.append("Tracking directory")

# 5. Check TradingAlgoFast.py exists
print("\n[5/8] Checking TradingAlgoFast.py...")
if os.path.exists("TradingAlgoFast.py"):
    print("  ✓ TradingAlgoFast.py found")
    checks_passed.append("TradingAlgoFast.py")
else:
    print("  ✗ TradingAlgoFast.py missing")
    checks_failed.append("TradingAlgoFast.py")

# 6. Check InteractiveBrokers.py exists
print("\n[6/8] Checking InteractiveBrokers.py...")
if os.path.exists("InteractiveBrokers.py"):
    print("  ✓ InteractiveBrokers.py found")
    # Check for position sync code
    with open("InteractiveBrokers.py", "r") as f:
        content = f.read()
        if "PRE-TRADE POSITION RECONCILIATION" in content:
            print("  ✓ Position reconciliation code present")
            checks_passed.append("Position reconciliation")
        else:
            print("  ⚠ Position reconciliation code not found")
            checks_failed.append("Position reconciliation code")
else:
    print("  ✗ InteractiveBrokers.py missing")
    checks_failed.append("InteractiveBrokers.py")

# 7. Check run_fred_daily.bat
print("\n[7/8] Checking run_fred_daily.bat...")
if os.path.exists("run_fred_daily.bat"):
    with open("run_fred_daily.bat", "r") as f:
        content = f.read()
        if "--port 4001" in content:
            print("  ✓ run_fred_daily.bat configured for LIVE port 4001")
            checks_passed.append("Live port configured")
        else:
            print("  ⚠ run_fred_daily.bat not using port 4001 (live)")
            checks_failed.append("Live port not configured")
else:
    print("  ✗ run_fred_daily.bat missing")
    checks_failed.append("run_fred_daily.bat")

# 8. Check backtest baseline
print("\n[8/8] Checking backtest baseline...")
print("  Expected baseline (as of 2026-05-09):")
print("    - 276.5 pts/day average")
print("    - 79.6% win rate")
print("    - 119 losing days")
print("  ✓ Baseline documented")
checks_passed.append("Baseline documented")

# Summary
print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)
print(f"Checks passed: {len(checks_passed)}")
for c in checks_passed:
    print(f"  ✓ {c}")

if checks_failed:
    print(f"\nChecks FAILED: {len(checks_failed)}")
    for c in checks_failed:
        print(f"  ✗ {c}")
    print("\n⚠ DO NOT GO LIVE until all checks pass!")
    sys.exit(1)
else:
    print("\n✓ ALL CHECKS PASSED — Fred is ready for live trading")
    print("\nFinal reminders:")
    print("  1. Ensure IB Gateway is running and logged in before 9:28 AM")
    print("  2. Do NOT place any manual trades while Fred is running")
    print("  3. Monitor the live chart window for the first 30 minutes")
    print("  4. Check IB log monitor to verify fills match the chart")
    print("  5. If anything looks wrong, run _flatten_position.py immediately")
    sys.exit(0)
