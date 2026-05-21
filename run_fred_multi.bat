@echo off
cd /d C:\Users\Administrator\source\repos\KORKIS3\QuantConnect
start "Fred - Account 1 (DUO158495) MASTER" cmd /k "C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe" InteractiveBrokers.py --port 4002 --client-id 1 --account-id DUO158495 --duration 450
timeout /t 1 /nobreak
start "Fred - Account 2 (DUQ921172) MIRROR" cmd /k "C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe" _mirror_account.py
pause
