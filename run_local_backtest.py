"""
run_local_backtest.py
=====================
Runs QuantConnectLocal.py through the locally-built Lean engine.
No Docker required.

Before running:
  1. Fill in your QuantConnect credentials below (get them from
     https://www.quantconnect.com/account  ->  "My API Credentials").
  2. Run:  python run_local_backtest.py

How it works:
  - Copies QuantConnectLocal.py into the Lean Algorithm.Python directory.
  - Patches Lean's config.json to point at the algorithm and to use the
    QuantConnect ApiDataProvider (downloads YM futures data on demand).
  - Launches QuantConnect.Lean.Launcher.exe directly (pure .NET, no Docker).
"""

import os
import re
import shutil
import subprocess
import sys
import glob

# ---------------------------------------------------------------------------
# QuantConnect API credentials
# Get these from https://www.quantconnect.com/account
# ---------------------------------------------------------------------------
QC_USER_ID     = "446417"
QC_API_TOKEN   = "e94d4e1022e70b6d1940194f2ae2e1540a2edd7e84454bb6900fccb1de66d0d0"

# ---------------------------------------------------------------------------
# Paths  (edit LEAN_DIR if your Lean clone lives elsewhere)
# ---------------------------------------------------------------------------
SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
LEAN_DIR    = os.path.normpath(
    os.path.join(SCRIPT_DIR, "..", "..", "QuantConnectBackTestingSetup", "Lean")
)
BUILD_DIR   = os.path.join(LEAN_DIR, "Launcher", "bin", "Debug")
LAUNCHER    = os.path.join(BUILD_DIR, "QuantConnect.Lean.Launcher.exe")
CONFIG_JSON = os.path.join(LEAN_DIR, "Launcher", "config.json")
ALGO_DIR    = os.path.join(LEAN_DIR, "Algorithm.Python")

ALGO_SRC    = os.path.join(SCRIPT_DIR, "QuantConnectLocal.py")
ALGO_CLASS  = "PensiveLightBrownWolf"
ALGO_DEST   = os.path.join(ALGO_DIR, f"{ALGO_CLASS}.py")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def patch_json_key(text: str, key: str, value: str) -> str:
    """Replace a quoted JSON string value for *key*, skipping // commented lines."""
    return re.sub(
        rf'^(\s*"{ re.escape(key) }"\s*:\s*)"[^"]*"',
        rf'\1"{value}"',
        text,
        flags=re.MULTILINE,
    )


def patch_json_bool(text: str, key: str, value: bool) -> str:
    """Replace a JSON boolean value for *key* (true/false, no quotes)."""
    bool_str = "true" if value else "false"
    return re.sub(
        rf'^(\s*"{ re.escape(key) }"\s*:\s*)(?:true|false)',
        rf'\1{bool_str}',
        text,
        flags=re.MULTILINE,
    )


def find_python_dll() -> str:
    """Return the path to the versioned Python DLL (e.g. python311.dll)."""
    py_dir = os.path.dirname(sys.executable)
    # Look for the versioned DLL (python3XX.dll), not the stub python3.dll
    pattern = os.path.join(py_dir, "python3[0-9][0-9].dll")
    matches = glob.glob(pattern)
    if matches:
        return matches[0]
    # Fallback: any python*.dll in the Python directory
    for name in os.listdir(py_dir):
        if re.match(r'python3\d+\.dll', name, re.IGNORECASE):
            return os.path.join(py_dir, name)
    return ""


def check_prerequisites() -> None:
    print("[1/4] Checking prerequisites ...")

    if not os.path.isfile(LAUNCHER):
        print(f"  ERROR: Lean launcher not found at:\n  {LAUNCHER}")
        print("  Run QuantConnectBackTestingSetup.py first to build Lean.")
        sys.exit(1)
    print(f"  Lean launcher : {LAUNCHER}")

    if not os.path.isfile(ALGO_SRC):
        print(f"  ERROR: Algorithm source not found:\n  {ALGO_SRC}")
        sys.exit(1)
    print(f"  Algorithm     : {ALGO_SRC}")

    if not QC_USER_ID or not QC_API_TOKEN:
        print(
            "\n  WARNING: QC_USER_ID / QC_API_TOKEN are not set.\n"
            "  YM futures data will NOT be downloaded automatically.\n"
            "  Edit run_local_backtest.py and fill in your credentials from\n"
            "  https://www.quantconnect.com/account\n"
        )


def deploy_algorithm() -> None:
    print("[2/4] Copying algorithm to Lean ...")
    os.makedirs(ALGO_DIR, exist_ok=True)
    shutil.copy2(ALGO_SRC, ALGO_DEST)
    print(f"  Written: {ALGO_DEST}")


def patch_config() -> None:
    print("[3/4] Patching config.json ...")

    if not os.path.isfile(CONFIG_JSON):
        print(f"  ERROR: config.json not found at {CONFIG_JSON}")
        sys.exit(1)

    raw = open(CONFIG_JSON, encoding="utf-8").read()

    raw = patch_json_key(raw, "algorithm-type-name", ALGO_CLASS)
    raw = patch_json_key(raw, "algorithm-language",  "Python")
    raw = patch_json_key(raw, "algorithm-location",
                         f"../../../Algorithm.Python/{ALGO_CLASS}.py")
    raw = patch_json_key(raw, "environment", "backtesting")

    if QC_USER_ID and QC_API_TOKEN:
        raw = patch_json_key(
            raw, "data-provider",
            "QuantConnect.Lean.Engine.DataFeeds.ApiDataProvider"
        )
        raw = patch_json_key(raw, "job-user-id",      QC_USER_ID)
        raw = patch_json_key(raw, "api-access-token", QC_API_TOKEN)
        print("  Data provider : ApiDataProvider (cloud download)")
    else:
        raw = patch_json_key(
            raw, "data-provider",
            "QuantConnect.Lean.Engine.DataFeeds.DefaultDataProvider"
        )
        print("  Data provider : DefaultDataProvider (local files only)")

    raw = patch_json_bool(raw, "show-missing-data-logs", False)

    with open(CONFIG_JSON, "w", encoding="utf-8") as fh:
        fh.write(raw)
    print("  config.json patched.")


def run_lean() -> None:
    print("[4/4] Launching Lean backtest ...")

    # pythonnet requires PYTHONNET_PYDLL to point to the versioned Python DLL
    # (e.g. python311.dll) so the .NET runtime can embed Python.
    env = os.environ.copy()
    if "PYTHONNET_PYDLL" not in env:
        dll = find_python_dll()
        if dll:
            env["PYTHONNET_PYDLL"] = dll
            print(f"  PYTHONNET_PYDLL : {dll}")
        else:
            print("  WARNING: Could not auto-detect python3XX.dll. "
                  "Set PYTHONNET_PYDLL manually if the backtest fails.")
    else:
        print(f"  PYTHONNET_PYDLL : {env['PYTHONNET_PYDLL']} (from environment)")

    print(f"  Working dir     : {BUILD_DIR}\n")
    print("=" * 60)

    result = subprocess.run(
        [LAUNCHER],
        cwd=BUILD_DIR,
        env=env,
    )

    print("=" * 60)
    if result.returncode == 0:
        print("\nBacktest completed successfully.")
    else:
        print(f"\nLean exited with code {result.returncode}.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("  YM Trendline Strategy  -  Local Lean Backtest")
    print("=" * 60)

    check_prerequisites()
    deploy_algorithm()
    patch_config()
    run_lean()
