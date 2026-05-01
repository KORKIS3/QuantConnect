@echo off
title Fred Watchdog
cd /d C:\Users\Administrator\source\repos\KORKIS3\QuantConnect
echo ==========================================
echo   Fred Watchdog - Auto-restart monitor
echo   Checks every 60s, restarts if down
echo ==========================================
echo.
C:\Python314\python.exe _watchdog.py
pause
