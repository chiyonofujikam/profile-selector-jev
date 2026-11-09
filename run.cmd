@echo off
setlocal
title Jev Profile Selector

if /i "%~1"=="--help" goto help
if "%~1"=="/?" goto help

echo.
echo Jev Profile Selector
echo ====================
echo Start Docker Desktop before continuing.
echo Dependencies and the database will be prepared automatically.
echo Keep this window open while using the app. Press Ctrl+C to stop.
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run.ps1" %*
set "launchExitCode=%errorlevel%"

if not "%launchExitCode%"=="0" (
    echo.
    echo The app could not start. Check the error above.
    echo Required: Python 3.13, uv, Node.js, and a running Docker Desktop.
    echo.
    pause
)
exit /b %launchExitCode%

:help
echo Usage: run.cmd [options]
echo.
echo Double-click run.cmd to prepare and start the app.
echo Default app URL: http://127.0.0.1:5173
echo.
echo Options:
echo   -Demo                  Load the supplied filters and fictional profiles
echo   -SetupOnly             Prepare dependencies and database only
echo   -BackendPort 8000      Choose the backend port
echo   -FrontendPort 5173     Choose the frontend port
echo   --help                 Show this help
exit /b 0
