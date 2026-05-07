@echo off
title Fred - YM Night Session
cd /d C:\Users\Administrator\source\repos\KORKIS3\QuantConnect
echo ==========================================
echo   Fred - YM Futures Trading Bot
echo   Session: 03:00 - 09:00 ET (overnight)
echo   Mode: PAPER TRADING
echo ==========================================
echo.
C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe run_fred.py --start-time 03:00 --duration 360 --client-id 4
echo.
echo Night session ended. Press any key to close.
pause
