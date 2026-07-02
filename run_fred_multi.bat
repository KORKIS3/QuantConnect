@echo off
cd /d C:\Users\Administrator\source\repos\KORKIS3\Fred-Production

:: Pull latest production code
echo Pulling latest production...
git pull origin production -q

echo ==========================================
echo   Fred Multi - Account 1 + Mirror
echo   Account 1: DUO158495 (trading w/ watchdog)
echo   Account 2: DUQ921172 (mirroring)
echo   Branch: production
echo   Folder: Fred-Production
echo ==========================================
start "Fred - Account 1 (DUO158495) WATCHDOG" cmd /k run_fred_watchdog.bat 4002 1 DUO158495 445
timeout /t 5 /nobreak
start "Fred - Account 2 Mirror (DUQ921172) Port 4003" cmd /k "C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe" _mirror_account.py
pause
