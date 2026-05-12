@echo off
REM Run Fred for Account 1 (DUO158495 on port 4002)
REM This runs as a separate process

python InteractiveBrokers.py --port 4002 --client-id 1 --account-id DUO158495 --duration 450

pause
