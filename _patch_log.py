"""_patch_log.py -- Write today's manual SELL 2 @ 49309 into Fred's log so the monitor sees it."""
import os, glob, datetime as _dt
import pytz

_EST = pytz.timezone("US/Eastern")
_LOG_DIR = os.path.join(os.path.expanduser("~"), "Desktop", "IB_Live", "logs")
today_key = _dt.datetime.now(_EST).strftime("%Y%m%d")

existing = sorted(glob.glob(os.path.join(_LOG_DIR, f"fred_ib_{today_key}*.log")))
if not existing:
    print("No log file found for today.")
    exit(1)

log_path = existing[-1]
print(f"Patching: {log_path}")

# Timestamp of the actual fill (12:46 ET)
ts = "2026-05-05 12:46:01"

entry = (
    f"{ts}  INFO      execDetails Execution(execId='manual_sell_124601', "
    f"time=datetime.datetime(2026, 5, 5, 16, 46, 1, tzinfo=datetime.timezone.utc), "
    f"acctNumber='DUO158495', exchange='CBOT', side='SLD', shares=2.0, price=49309.0, "
    f"permId=0, clientId=1, orderId=999, liquidation=0, cumQty=2.0, avgPrice=49309.0, "
    f"orderRef='manual', evRule='', evMultiplier=0.0, modelCode='', lastLiquidity=1)\n"
)

with open(log_path, "a", encoding="utf-8") as f:
    f.write(entry)

print(f"Done. Added SELL 2 @ 49309 to {os.path.basename(log_path)}")
