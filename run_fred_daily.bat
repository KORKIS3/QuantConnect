@echo off
title Fred - YM Trading Session
cd /d C:\Users\Administrator\source\repos\KORKIS3\QuantConnect
echo ==========================================
echo   Fred - YM Futures Trading Bot
echo   Session: 9:30 - 17:00 ET
echo   Mode: PAPER TRADING
echo ==========================================
echo.

:: Launch IB log monitor in a separate window
start "Fred IB Monitor" C:\Python314\python.exe _ib_log_monitor.py

:: Launch Fred with live chart (Python311 required for ib_insync)
C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe run_fred.py --duration 450

echo.
echo Session ended.
pause
