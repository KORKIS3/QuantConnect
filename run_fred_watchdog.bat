@echo off
:: ============================================================
:: FRED WATCHDOG — Auto-restart wrapper for the trading bot.
::
:: Purpose: Keeps Fred alive during the trading session by
::          automatically restarting it if it crashes (non-zero
::          exit code). Stops gracefully when:
::            - Fred exits cleanly (exit code 0 = duration expired)
::            - A FRED_STOP sentinel file is detected (manual kill)
::
:: Usage:   run_fred_watchdog.bat [port] [client-id] [account-id] [duration]
::          Called by run_fred_multi.bat with: 4002 1 DUO158495 445
::
:: Defaults match run_fred_multi.bat Account 1 settings.
:: ============================================================

setlocal

:: --- Parse command-line arguments (positional) ---
:: %1 = IB Gateway port (4002=paper, 4001=live)
set PORT=%1
if "%PORT%"=="" set PORT=4002

:: %2 = IB client ID (unique per connection to same gateway)
set CLIENT_ID=%2
if "%CLIENT_ID%"=="" set CLIENT_ID=1

:: %3 = IB account ID (used for logging/display only here)
set ACCOUNT_ID=%3
if "%ACCOUNT_ID%"=="" set ACCOUNT_ID=DUO158495

:: %4 = Session duration in MINUTES (445 min = ~7h 25m, covers full RTH + buffer)
set DURATION=%4
if "%DURATION%"=="" set DURATION=445

:: --- Paths ---
:: Full path to Python 3.11 interpreter
set PYTHON=C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe
:: Directory where this .bat file lives (trailing backslash included)
set SCRIPT_DIR=%~dp0

:: --- Startup banner ---
echo ==========================================
echo   Fred Watchdog - Auto-Restart on Crash
echo   Account: %ACCOUNT_ID%
echo   Port: %PORT%  Client: %CLIENT_ID%
echo   Duration: %DURATION% minutes
echo ==========================================

:: === MAIN LOOP — restarts Fred on crash ===
:loop
echo.
echo [%date% %time%] Starting Fred...

:: Launch Fred trading bot; blocks here until Fred exits
"%PYTHON%" "%SCRIPT_DIR%run_fred.py" --port %PORT% --client-id %CLIENT_ID% --duration %DURATION%

:: Capture Fred's exit code immediately (before any other command overwrites it)
set EXIT_CODE=%ERRORLEVEL%

:: --- Check 1: Was Fred manually stopped via sentinel file? ---
:: _flatten_position.py or manual intervention drops this file to signal "don't restart"
if exist "%USERPROFILE%\Desktop\IB_Live\FRED_STOP" (
    echo [%date% %time%] FRED_STOP detected — not restarting.
    goto :end
)

:: --- Check 2: Did Fred exit cleanly? (exit code 0 = session duration expired normally) ---
if %EXIT_CODE%==0 (
    echo [%date% %time%] Fred exited normally (session complete).
    goto :end
)

:: --- Otherwise: Fred crashed — wait 10s then restart ---
:: Common crash reasons: IB disconnect, unhandled exception, network blip
echo [%date% %time%] Fred crashed with exit code %EXIT_CODE% — restarting in 10 seconds...
timeout /t 10 /nobreak
goto :loop

:: === END — watchdog stops here ===
:end
echo [%date% %time%] Watchdog exiting.
pause
