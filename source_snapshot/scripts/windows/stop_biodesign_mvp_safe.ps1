[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$launcherModule = Join-Path $repoRoot 'scripts\windows\biodesign_mvp_launcher.py'

try {
    $python = Get-Command python -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -eq $python) { $python = Get-Command py -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1 }
    if ($null -eq $python) { throw 'No Python interpreter is available to run the stop helper.' }
    & $python.Source $launcherModule 'stop' '--repo-root' $repoRoot
    exit $LASTEXITCODE
} catch { Write-Host "BioDesign MVP: $($_.Exception.Message)" -ForegroundColor Red; exit 1 }
