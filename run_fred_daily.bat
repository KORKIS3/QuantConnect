@echo off
title Fred - YM Trading Session
cd /d C:\Users\Administrator\source\repos\KORKIS3\QuantConnect
echo ==========================================
echo   Fred - YM Futures Trading Bot
echo   Session: 9:30 - 17:00 ET
echo   Mode: DRY RUN (no real orders)
echo ==========================================
echo.
python run_fred.py --dry-run --duration 450
echo.
echo Session ended. Press any key to close.
pause
