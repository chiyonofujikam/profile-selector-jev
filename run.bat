@echo off
setlocal
title Jev Profile Selector
set "PROFILE_RUN_FILE=%~f0"

if /i "%~1"=="--help" goto help
if "%~1"=="/?" goto help

echo.
echo Jev Profile Selector
echo ====================
echo Start Docker Desktop before continuing.
echo Dependencies and the database will be prepared automatically.
echo Keep this window open while using the app. Press Ctrl+C to stop.
echo.

rem Run the PowerShell startup section stored in this same file.
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$code = (Get-Content -LiteralPath $env:PROFILE_RUN_FILE -Raw) -split '(?m)^:powershell\r?$', 2; & ([scriptblock]::Create($code[1]))" %*
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
echo Usage: run.bat [options]
echo.
echo Double-click run.bat to prepare and start the app.
echo Default app URL: http://127.0.0.1:5173
echo.
echo Options:
echo   -Demo                  Load the supplied filters and fictional profiles
echo   -SetupOnly             Prepare dependencies and database only
echo   -BackendPort 8000      Choose the backend port
echo   -FrontendPort 5173     Choose the frontend port
echo   --help                 Show this help
exit /b 0

:powershell
[CmdletBinding()]
param(
    [switch]$SetupOnly,
    [switch]$Demo,
    [ValidateRange(1, 65535)][int]$BackendPort = 8000,
    [ValidateRange(1, 65535)][int]$FrontendPort = 5173
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $env:PROFILE_RUN_FILE
$uvCommand = Get-Command uv -ErrorAction SilentlyContinue
$uvExecutable = if ($uvCommand) { $uvCommand.Source } else { $null }

if (-not $uvExecutable) {
    $uvCandidates = @(
        (Join-Path $env:USERPROFILE '.local/bin/uv.exe'),
        (Join-Path $env:USERPROFILE '.cargo/bin/uv.exe')
    )
    $pythonInstallRoot = Join-Path $env:LOCALAPPDATA 'Programs/Python'
    if (Test-Path -LiteralPath $pythonInstallRoot) {
        $uvCandidates += @(Get-ChildItem -Path (Join-Path $pythonInstallRoot 'Python*/Scripts/uv.exe') -File -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName)
    }
    $uvExecutable = $uvCandidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
}

if (-not $uvExecutable) {
    Write-Error 'uv was not found. Install uv, reopen the terminal, then run this launcher again.'
    exit 1
}

Push-Location -LiteralPath $projectRoot
try {
    Write-Host 'Installing/checking backend dependencies in backend/.venv...'
    & $uvExecutable sync --project backend --locked
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    $launchArguments = @('run', '--project', 'backend', '--locked', 'python', '-m', 'scripts.dev', '--backend-port', "$BackendPort", '--frontend-port', "$FrontendPort")
    if ($SetupOnly) { $launchArguments += '--setup-only' }
    if ($Demo) { $launchArguments += '--demo' }
    & $uvExecutable @launchArguments
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
