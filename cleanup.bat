@echo off
setlocal
set "CLEANUP_FILE=%~f0"
set "CLEANUP_PREVIEW="
if /i "%~1"=="-WhatIf" set "CLEANUP_PREVIEW=1"

rem Run the PowerShell section stored below in this same file.
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$code = (Get-Content -LiteralPath $env:CLEANUP_FILE -Raw) -split '(?m)^:powershell\r?$', 2; & ([scriptblock]::Create($code[1])) -WhatIf:([bool]$env:CLEANUP_PREVIEW)"
exit /b %errorlevel%

:powershell
# Clear project caches and frontend output, then clear uv's shared cache.
[CmdletBinding(SupportsShouldProcess)]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = [System.IO.Path]::GetFullPath((Split-Path -Parent $env:CLEANUP_FILE))
$cacheNames = @(
    '__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache',
    '.uv-cache', '.vite', '.vite-temp', '.vitest', '.cache', '.hypothesis',
    '.pytype', '.npm', '.pnpm-store'
)
$frontendRoot = Join-Path $projectRoot 'frontend'
$frontendOutputNames = @('dist', 'build', 'coverage', 'playwright-report', 'test-results', 'blob-report')

# Walk from this project, regardless of where cleanup.bat was launched.
# Skip Git metadata and links so cleanup stays inside the project.
$folders = [System.Collections.Generic.Stack[string]]::new()
$folders.Push($projectRoot)
while ($folders.Count -gt 0) {
    $folder = $folders.Pop()
    foreach ($item in Get-ChildItem -LiteralPath $folder -Force) {
        if ($item.Name -eq '.git' -or ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint)) {
            continue
        }

        $cacheFolder = $item.PSIsContainer -and $item.Name -in $cacheNames
        # Remove these only directly under frontend, never inside dependencies.
        $frontendOutput = $item.PSIsContainer -and $item.Parent.FullName -eq $frontendRoot -and $item.Name -in $frontendOutputNames
        $cacheFile = -not $item.PSIsContainer -and (
            $item.Extension -in @('.pyc', '.pyo', '.tsbuildinfo') -or
            $item.Name -in @('.coverage', '.eslintcache', '.stylelintcache') -or
            $item.Name -like '.coverage.*'
        )

        if ($cacheFolder -or $cacheFile -or $frontendOutput) {
            $target = [System.IO.Path]::GetFullPath($item.FullName)
            if (-not $target.StartsWith($projectRoot + '\', [System.StringComparison]::OrdinalIgnoreCase)) {
                throw "Refusing to delete outside the project: $target"
            }
            if ($PSCmdlet.ShouldProcess($target, 'Delete project cache')) {
                Remove-Item -LiteralPath $target -Recurse -Force
            }
        } elseif ($item.PSIsContainer) {
            $folders.Push($item.FullName)
        }
    }
}

# Find uv in PATH or the same common install locations used by run.bat.
$uvCommand = Get-Command uv -ErrorAction SilentlyContinue
$uvExecutable = if ($uvCommand) { $uvCommand.Source } else { $null }
if (-not $uvExecutable) {
    $candidates = @(
        (Join-Path $env:USERPROFILE '.local/bin/uv.exe'),
        (Join-Path $env:USERPROFILE '.cargo/bin/uv.exe')
    )
    $pythonRoot = Join-Path $env:LOCALAPPDATA 'Programs/Python'
    if (Test-Path -LiteralPath $pythonRoot) {
        $candidates += @(Get-ChildItem -Path (Join-Path $pythonRoot 'Python*/Scripts/uv.exe') -File -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName)
    }
    $uvExecutable = $candidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
}

if ($uvExecutable) {
    if ($PSCmdlet.ShouldProcess('uv shared cache (used by all projects)', 'Run uv cache clean')) {
        & $uvExecutable cache clean
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
} else {
    Write-Warning 'Project caches were checked, but uv was not found. Run uv cache clean when uv is available.'
    exit 1
}

Write-Host 'Cleanup complete. Dependencies, settings, and project data were kept.'
