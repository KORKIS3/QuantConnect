@echo off
title Fred - YM Night Session
cd /d C:\Users\Administrator\source\repos\KORKIS3\QuantConnect
echo ==========================================
echo   Fred - YM Futures Trading Bot
echo   Session: 18:00 - 09:00 ET (overnight)
echo   Mode: PAPER TRADING
echo ==========================================
echo.
set LOGFILE=C:\Users\Administrator\Desktop\IB_Live\logs\fred_night_%date:~-4,4%%date:~-10,2%%date:~-7,2%.log
C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe run_fred.py --duration 900 --client-id 4 2>&1 | tee %LOGFILE%
echo.
echo Night session ended. Log saved to %LOGFILE%
echo Press any key to close.
pause
