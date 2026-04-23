@echo off
title Fred - YM Trading Session
cd /d C:\Users\Administrator\source\repos\KORKIS3\QuantConnect
echo ==========================================
echo   Fred - YM Futures Trading Bot
echo   Session: 9:30 - 17:00 ET
echo   Mode: PAPER TRADING
echo ==========================================
echo.
set LOGFILE=C:\Users\Administrator\Desktop\IB_Live\logs\fred_day_%date:~-4,4%%date:~-10,2%%date:~-7,2%.log
C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe run_fred.py --duration 450 2>&1 | tee %LOGFILE%
echo.
echo Session ended. Log saved to %LOGFILE%
echo Press any key to close.
pause
