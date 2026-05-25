@echo off
cd /d C:\Users\Administrator\source\repos\KORKIS3\QuantConnect
echo ==========================================
echo   Fred Cushion Strategy - Both Accounts
echo   Cushion=40, TP=+60, SL=-50
echo ==========================================
start "Fred - Account 1 (DUO158495) Port 4002" cmd /k "C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe" InteractiveBrokers.py --port 4002 --client-id 1 --account-id DUO158495 --duration 450
timeout /t 3 /nobreak
start "Fred - Account 2 (DUQ921172) Port 4003" cmd /k "C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe" InteractiveBrokers.py --port 4003 --client-id 2 --account-id DUQ921172 --duration 450
pause
