@echo off
title Fred - YM Trading Session
cd /d C:\Users\Administrator\source\repos\KORKIS3\QuantConnect
echo ==========================================
echo   Fred - YM Futures Trading Bot
echo   Session: 9:30 - 17:00 ET
echo   Mode: PAPER TRADING
echo ==========================================
echo.
C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe run_fred.py --duration 450
echo.
echo Session ended. Press any key to close.
pause
