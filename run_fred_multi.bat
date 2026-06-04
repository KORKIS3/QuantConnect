@echo off
cd /d C:\Users\Administrator\source\repos\KORKIS3\QuantConnect
echo ==========================================
echo   Fred Multi - Account 1 + Mirror
echo   Account 1: DUO158495 (trading)
echo   Account 2: DUQ921172 (mirroring)
echo ==========================================
start "Fred - Account 1 (DUO158495) Port 4002" cmd /k "C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe" InteractiveBrokers.py --port 4002 --client-id 1 --account-id DUO158495 --duration 450
timeout /t 5 /nobreak
start "Fred - Account 2 Mirror (DUQ921172) Port 4003" cmd /k "C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe" _mirror_account.py
pause
