[CmdletBinding()]
param(
    [switch]$SetupOnly,
    [switch]$Demo,
    [ValidateRange(1, 65535)][int]$BackendPort = 8000,
    [ValidateRange(1, 65535)][int]$FrontendPort = 5173
)

$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
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
