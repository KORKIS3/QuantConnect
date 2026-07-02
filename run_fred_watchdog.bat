@echo off
:: Watchdog for Fred - restarts the process if it crashes.
:: Usage: run_fred_watchdog.bat [port] [client-id] [account-id] [duration]
::
:: Defaults match run_fred_multi.bat Account 1 settings.
:: The watchdog will keep restarting until the session duration expires
:: or a FRED_STOP file is detected.

setlocal
set PORT=%1
if "%PORT%"=="" set PORT=4002
set CLIENT_ID=%2
if "%CLIENT_ID%"=="" set CLIENT_ID=1
set ACCOUNT_ID=%3
if "%ACCOUNT_ID%"=="" set ACCOUNT_ID=DUO158495
set DURATION=%4
if "%DURATION%"=="" set DURATION=445

set PYTHON=C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe
set SCRIPT_DIR=%~dp0

echo ==========================================
echo   Fred Watchdog - Auto-Restart on Crash
echo   Account: %ACCOUNT_ID%
echo   Port: %PORT%  Client: %CLIENT_ID%
echo   Duration: %DURATION% minutes
echo ==========================================

:loop
echo.
echo [%date% %time%] Starting Fred...
"%PYTHON%" "%SCRIPT_DIR%run_fred.py" --port %PORT% --client-id %CLIENT_ID% --duration %DURATION%
set EXIT_CODE=%ERRORLEVEL%

:: Check if session ended normally (exit code 0) or was stopped
if exist "%USERPROFILE%\Desktop\IB_Live\FRED_STOP" (
    echo [%date% %time%] FRED_STOP detected — not restarting.
    goto :end
)

:: If exit code is 0, session ended normally (duration expired)
if %EXIT_CODE%==0 (
    echo [%date% %time%] Fred exited normally (session complete).
    goto :end
)

:: Crashed — wait 10 seconds then restart
echo [%date% %time%] Fred crashed with exit code %EXIT_CODE% — restarting in 10 seconds...
timeout /t 10 /nobreak
goto :loop

:end
echo [%date% %time%] Watchdog exiting.
pause
