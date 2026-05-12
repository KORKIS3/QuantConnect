@echo off
REM Run Fred for Account 2 (DUQ921172 on port 4003)
REM This runs as a separate process

python InteractiveBrokers.py --port 4003 --client-id 2 --duration 450

pause
