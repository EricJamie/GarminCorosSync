@echo off
:: Garmin - Coros Sync - Windows runner script
::
:: Usage:
::   sync.bat                 - Full bidirectional sync
::   sync.bat --garmin-only  - Only Garmin -> Coros
::   sync.bat --coros-only   - Only Coros -> Garmin
::   sync.bat --dry-run      - Preview without uploading
::
:: Environment variables (set in shell or .env):
::   COROS_EMAIL, COROS_PASSWORD, GARMIN_TOKEN_DIR

setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"
set "LOG_DIR=%SCRIPT_DIR%logs"

:: Create log directory if not exists
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

:: Load .env if exists
if exist "%SCRIPT_DIR%.env" (
    for /f "usebackq tokens=1,* delims==" %%a in ("%SCRIPT_DIR%.env") do (
        set "%%a=%%b"
    )
)

:: Generate log filename with timestamp
for /f "tokens=2 delims== " %%a in ('"powershell -Command "Get-Date -Format 'yyyyMMdd_HHmmss'""') do set "TS=%%a"
set "LOG_FILE=%LOG_DIR%\sync_%TS%.log"

echo [%date% %time%] Starting sync...
echo [%date% %time%] Starting sync... >> "%LOG_FILE%"

python "%SCRIPT_DIR%sync.py" %* >> "%LOG_FILE%" 2>&1

echo [%date% %time%] Sync finished
echo [%date% %time%] Sync finished >> "%LOG_FILE%"

endlocal
