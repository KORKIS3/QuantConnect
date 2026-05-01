"""_watchdog.py — monitors Fred and restarts if IB Gateway goes down.

Checks every 60 seconds if Fred is running. If not, determines the correct
session (day or night) based on current ET time and restarts the appropriate bat.

Day session:   09:28 – 17:05 ET  → run_fred_daily.bat
Night session: 17:58 – 08:56 ET  → run_fred_night.bat

Usage:
    python _watchdog.py
"""

import subprocess
import time
import os
import sys
import logging
from datetime import datetime
import pytz

_EST = pytz.timezone("US/Eastern")
_CHECK_INTERVAL = 60   # seconds between checks
_FRED_PROCESS_NAME = "run_fred.py"
_WORKSPACE = os.path.dirname(os.path.abspath(__file__))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.join(_WORKSPACE, "fred_watchdog.log"), encoding="utf-8"),
    ]
)
log = logging.getLogger("watchdog")


def _is_fred_running() -> bool:
    """Check if run_fred.py is currently running as a process."""
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq python.exe", "/FO", "CSV"],
            capture_output=True, text=True
        )
        # Check if any python process has run_fred.py in its command line
        result2 = subprocess.run(
            ["wmic", "process", "where", "name='python.exe'", "get", "CommandLine", "/FORMAT:CSV"],
            capture_output=True, text=True
        )
        return _FRED_PROCESS_NAME in result2.stdout
    except Exception as e:
        log.error("Error checking process: %s", e)
        return False


def _current_session() -> str:
    """Return 'day', 'night', or 'none' based on current ET time."""
    now = datetime.now(_EST)
    hour = now.hour
    minute = now.minute
    total_minutes = hour * 60 + minute

    # Day session: 09:28 – 17:05
    day_start  = 9 * 60 + 28
    day_end    = 17 * 60 + 5

    # Night session: 17:58 – 08:56 (crosses midnight)
    night_start = 17 * 60 + 58
    night_end   = 8 * 60 + 56

    if day_start <= total_minutes <= day_end:
        return "day"
    if total_minutes >= night_start or total_minutes <= night_end:
        return "night"
    return "none"


def _start_fred(session: str) -> None:
    """Launch the appropriate bat file for the session."""
    if session == "day":
        bat = os.path.join(_WORKSPACE, "run_fred_daily.bat")
        log.info("Starting DAY session: %s", bat)
    elif session == "night":
        bat = os.path.join(_WORKSPACE, "run_fred_night.bat")
        log.info("Starting NIGHT session: %s", bat)
    else:
        log.info("Outside trading hours — not restarting.")
        return

    try:
        subprocess.Popen(
            ["cmd", "/c", "start", "", bat],
            cwd=_WORKSPACE,
            creationflags=subprocess.CREATE_NEW_CONSOLE
        )
        log.info("Fred started successfully.")
    except Exception as e:
        log.error("Failed to start Fred: %s", e)


def main():
    log.info("Fred Watchdog started — checking every %ds", _CHECK_INTERVAL)
    log.info("Workspace: %s", _WORKSPACE)

    consecutive_down = 0

    while True:
        try:
            session = _current_session()

            if session == "none":
                log.debug("Outside trading hours — skipping check.")
                consecutive_down = 0
                time.sleep(_CHECK_INTERVAL)
                continue

            running = _is_fred_running()

            if running:
                log.debug("Fred is running. Session: %s", session)
                consecutive_down = 0
            else:
                consecutive_down += 1
                log.warning("Fred NOT running (check %d). Session: %s", consecutive_down, session)

                # Wait 2 consecutive failures before restarting (avoids false positives)
                if consecutive_down >= 2:
                    log.warning("Fred down for %d checks — restarting...", consecutive_down)
                    _start_fred(session)
                    consecutive_down = 0
                    time.sleep(30)  # give Fred time to start before next check

        except KeyboardInterrupt:
            log.info("Watchdog stopped by user.")
            break
        except Exception as e:
            log.error("Watchdog error: %s", e)

        time.sleep(_CHECK_INTERVAL)


if __name__ == "__main__":
    main()
