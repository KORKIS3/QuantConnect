"""
QuantConnect Lean Engine - Local Build Setup & Jupyter Research Launcher
========================================================================
What this script does (in order):
  1. Verifies prerequisites: .NET SDK present on PATH.
  2. Builds the Lean solution with dotnet build.
  3. Installs required Python packages (pythonnet, jupyterlab, etc.).
  4. Writes a starter Python backtesting algorithm into Algorithm.Python/.
  5. Patches config.json to point at that algorithm.
  6. Launches Jupyter Lab with PYTHONPATH set to the Lean build output.

Run:
    python QuantConnectBackTestingSetup.py
"""

import subprocess
import sys
import os
import re
import shutil

# ---------------------------------------------------------------------------
# Paths  (Lean/ lives in the sibling QuantConnectBackTestingSetup repo)
# ---------------------------------------------------------------------------

SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
# Lean engine is in the sibling repo: ../../QuantConnectBackTestingSetup/Lean
LEAN_DIR     = os.path.join(SCRIPT_DIR, "..", "..", "QuantConnectBackTestingSetup", "Lean")
SOLUTION     = os.path.join(LEAN_DIR, "QuantConnect.Lean.sln")
BUILD_DIR    = os.path.join(LEAN_DIR, "Launcher", "bin", "Debug")
CONFIG_JSON  = os.path.join(LEAN_DIR, "Launcher", "config.json")
ALGO_DIR     = os.path.join(LEAN_DIR, "Algorithm.Python")
RESEARCH_DIR = os.path.join(LEAN_DIR, "Research")

ALGORITHM_NAME = "StarterAlgorithm"
ALGORITHM_FILE = os.path.join(ALGO_DIR, f"{ALGORITHM_NAME}.py")

TOTAL_STEPS = 5

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def step(n: int, msg: str) -> None:
    print(f"\n[{n}/{TOTAL_STEPS}] {msg}")


def run(cmd: list, cwd: str = None, check: bool = True) -> subprocess.CompletedProcess:
    print(f"  >> {' '.join(str(c) for c in cmd)}")
    return subprocess.run(cmd, cwd=cwd, check=check)


def pip_install(*packages: str) -> None:
    run([sys.executable, "-m", "pip", "install", "--quiet", "--upgrade", *packages])


def patch_json_key(text: str, key: str, value: str) -> str:
    """Replace a quoted JSON string value for *key*, preserving // comments."""
    return re.sub(
        rf'("{re.escape(key)}"\s*:\s*)"[^"]*"',
        rf'\1"{value}"',
        text,
    )

# ---------------------------------------------------------------------------
# Step 1 - Verify / install .NET SDK
# ---------------------------------------------------------------------------

DOTNET_WINGET_ID = "Microsoft.DotNet.SDK.10"  # Lean targets net10.0


def _refresh_path() -> None:
    """Pull the current Machine + User PATH into this process after an install."""
    import winreg
    paths = []
    for hive, sub in [
        (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
        (winreg.HKEY_CURRENT_USER,  r"Environment"),
    ]:
        try:
            key = winreg.OpenKey(hive, sub)
            value, _ = winreg.QueryValueEx(key, "PATH")
            paths.append(value)
            winreg.CloseKey(key)
        except FileNotFoundError:
            pass
    os.environ["PATH"] = os.pathsep.join(paths)


def check_dotnet() -> None:
    step(1, "Checking .NET SDK (need >= 10) ...")

    if shutil.which("dotnet"):
        result = subprocess.run(["dotnet", "--version"], capture_output=True, text=True)
        version = result.stdout.strip()
        major = int(version.split(".")[0]) if version else 0
        if major >= 10:
            print(f"  .NET SDK {version} detected.")
            return
        print(f"  .NET SDK {version} found but Lean requires >= 10 - installing .NET 10 via winget ...")
    else:
        print("  'dotnet' not found on PATH - attempting install via winget ...")

    if not shutil.which("winget"):
        print(
            "\n  ERROR: winget is also unavailable.\n"
            "  Install the .NET 10 SDK manually: https://dotnet.microsoft.com/download\n"
            "  then re-run this script.\n"
        )
        sys.exit(1)

    result = subprocess.run(
        ["winget", "install", "--id", DOTNET_WINGET_ID,
         "--silent", "--accept-package-agreements", "--accept-source-agreements"],
        check=False,
    )
    if result.returncode != 0:
        print(
            "\n  ERROR: winget install failed.\n"
            "  Install the .NET 10 SDK manually: https://dotnet.microsoft.com/download\n"
        )
        sys.exit(1)

    _refresh_path()

    if not shutil.which("dotnet"):
        print(
            "\n  .NET SDK installed but 'dotnet' is still not on PATH.\n"
            "  Please open a new terminal and re-run this script.\n"
        )
        sys.exit(1)

    result = subprocess.run(["dotnet", "--version"], capture_output=True, text=True)
    print(f"  .NET SDK {result.stdout.strip()} installed and ready.")

# ---------------------------------------------------------------------------
# Step 2 - Build Lean
# ---------------------------------------------------------------------------

def build_lean() -> None:
    step(2, "Building Lean solution ...")
    if not os.path.exists(SOLUTION):
        print(f"  ERROR: Solution file not found:\n  {SOLUTION}")
        sys.exit(1)

    # Build only the Launcher and Research projects — this compiles the full
    # engine dependency chain while skipping the Tests project.
    targets = [
        os.path.join(LEAN_DIR, "Launcher",  "QuantConnect.Lean.Launcher.csproj"),
        os.path.join(LEAN_DIR, "Research",   "QuantConnect.Research.csproj"),
    ]

    print("  Restoring NuGet packages ...")
    for t in targets:
        run(["dotnet", "restore", t, "--verbosity", "minimal"], cwd=LEAN_DIR)

    print("  Compiling ...")
    for t in targets:
        result = subprocess.run(
            [
                "dotnet", "build", t,
                "--configuration", "Debug",
                "--no-restore",
                "--verbosity", "minimal",
            ],
            cwd=LEAN_DIR,
        )
        if result.returncode != 0:
            print("\n  ERROR: Build failed. Review the output above for details.")
            sys.exit(1)
    print("  Build succeeded.")

# ---------------------------------------------------------------------------
# Step 3 - Python packages
# ---------------------------------------------------------------------------

REQUIRED_PACKAGES = [
    "pythonnet",   # .NET/Python CLR bridge used by Lean research kernel
    "clr-loader",  # required by pythonnet on .NET 6+
    "jupyterlab",  # Jupyter Lab UI
    "notebook",    # classic notebook kernel
    "pandas",
    "matplotlib",
    "numpy",
]


def install_python_packages() -> None:
    step(3, "Installing Python packages ...")
    pip_install(*REQUIRED_PACKAGES)
    print("  All packages ready.")

# ---------------------------------------------------------------------------
# Step 4 - Starter algorithm + config.json
# ---------------------------------------------------------------------------

ALGORITHM_SOURCE = '''\
from AlgorithmImports import *


class StarterAlgorithm(QCAlgorithm):
    """Simple SPY buy-and-hold starter algorithm."""

    def initialize(self) -> None:
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2023, 12, 31)
        self.set_cash(100_000)
        self.add_equity("SPY", Resolution.DAILY)
        self.set_benchmark("SPY")

    def on_data(self, data: Slice) -> None:
        if not self.portfolio.invested:
            self.set_holdings("SPY", 1.0)
'''


def setup_algorithm() -> None:
    step(4, "Writing starter algorithm and updating config.json ...")

    os.makedirs(ALGO_DIR, exist_ok=True)
    if not os.path.exists(ALGORITHM_FILE):
        with open(ALGORITHM_FILE, "w", encoding="utf-8") as fh:
            fh.write(ALGORITHM_SOURCE)
        print(f"  Written: {ALGORITHM_FILE}")
    else:
        print("  Algorithm file already exists - skipping.")

    if not os.path.exists(CONFIG_JSON):
        print(f"  WARNING: config.json not found at {CONFIG_JSON}")
        return

    raw = open(CONFIG_JSON, encoding="utf-8").read()
    raw = patch_json_key(raw, "algorithm-type-name", ALGORITHM_NAME)
    raw = patch_json_key(raw, "algorithm-language",  "Python")
    raw = patch_json_key(raw, "algorithm-location",
                         f"../../../Algorithm.Python/{ALGORITHM_NAME}.py")
    raw = patch_json_key(raw, "environment", "backtesting")

    with open(CONFIG_JSON, "w", encoding="utf-8") as fh:
        fh.write(raw)
    print("  config.json patched for Python backtesting.")

# ---------------------------------------------------------------------------
# Step 5 - Launch Jupyter Lab
# ---------------------------------------------------------------------------

def launch_jupyter() -> None:
    step(5, "Launching Jupyter Lab ...")

    if not os.path.isdir(BUILD_DIR):
        print(
            f"\n  ERROR: Build output directory not found:\n  {BUILD_DIR}\n"
            "  Ensure Step 2 (build Lean) completed without errors."
        )
        sys.exit(1)

    # Copy Research notebooks into the build output so they sit alongside
    # start.py, allowing `%run start.py` to resolve without path changes.
    for nb in os.listdir(RESEARCH_DIR):
        if nb.endswith(".ipynb") or nb in ("start.py",):
            src = os.path.join(RESEARCH_DIR, nb)
            dst = os.path.join(BUILD_DIR, nb)
            if not os.path.exists(dst):
                shutil.copy2(src, dst)
                print(f"  Copied {nb} -> build output")

    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    # Lean assemblies must be on PYTHONPATH for pythonnet / start.py to work
    env["PYTHONPATH"] = f"{BUILD_DIR}{os.pathsep}{existing}" if existing else BUILD_DIR

    print(f"  PYTHONPATH  : {BUILD_DIR}")
    print(f"  Notebook dir: {BUILD_DIR}")
    print("  URL         : http://localhost:8888/lab")
    print("  Press Ctrl+C to stop the server.\n")

    subprocess.run(
        [
            sys.executable, "-m", "jupyterlab",
            "--notebook-dir", BUILD_DIR,
            "--port", "8888",
            "--no-browser",
        ],
        env=env,
        check=False,
    )

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("  QuantConnect Lean  -  Setup & Jupyter Launcher")
    print("=" * 60)
    check_dotnet()
    build_lean()
    install_python_packages()
    setup_algorithm()
    launch_jupyter()
