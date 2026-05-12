@echo off
start "Fred - Account 1 (DUO158495) MASTER" cmd /k python InteractiveBrokers.py --port 4002 --client-id 1 --account-id DUO158495 --duration 450
timeout /t 10 /nobreak
start "Fred - Account 2 (DUQ921172) MIRROR" cmd /k python _mirror_account.py
pause
