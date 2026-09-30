[CmdletBinding()]
param([switch]$NoBrowser)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$launcherModule = Join-Path $repoRoot 'scripts\windows\biodesign_mvp_launcher.py'
$statePath = Join-Path $repoRoot '.runtime\mvp_runtime.json'

function Get-BootstrapCommand {
    # This only runs the selector. Keep the venv last so it cannot shadow the system `python` candidate via PATH.
    $candidates = @(@('python'), @('py', '-3.12'), @('py', '-3.11'), @('py'), @((Join-Path $repoRoot '.venv\Scripts\python.exe')))
    foreach ($candidate in $candidates) {
        try {
            & $candidate[0] @($candidate | Select-Object -Skip 1) '-c' 'import sys' *> $null
            if ($LASTEXITCODE -eq 0) { return ,$candidate }
        } catch { }
    }
    throw 'No Python interpreter is available to run the launcher.'
}

try {
    $bootstrap = Get-BootstrapCommand
    $output = & $bootstrap[0] @($bootstrap | Select-Object -Skip 1) $launcherModule 'start' '--repo-root' $repoRoot
    $lines = @($output | Where-Object { $_ -and $_.ToString().Trim() })
    $lastLine = if ($lines.Count -gt 0) { $lines[-1] } else { '' }
    if ($LASTEXITCODE -ne 0) {
        try {
            $failure = $lastLine | ConvertFrom-Json
            Write-Host "BioDesign MVP: $($failure.message)" -ForegroundColor Red
        } catch {
            Write-Host "BioDesign MVP: $lastLine" -ForegroundColor Red
        }
        exit $LASTEXITCODE
    }
    $result = $lastLine | ConvertFrom-Json
    $state = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json

    Write-Host ''
    Write-Host 'BioDesign MVP compatibility runtime'
    Write-Host ('State       : {0}' -f ($(if ($result.reused) { 'already running' } else { 'started new process' })))
    Write-Host ('Python path : {0}' -f [string]$state.python_executable)
    Write-Host ('Python ver  : {0}' -f [string]$state.python_version)
    Write-Host ('Entry       : {0}' -f [string]$state.mvp_entry_path)
    Write-Host ('Port        : {0}' -f [string]$state.port)
    Write-Host ('Workdir     : {0}' -f [string]$state.repository_root)
    Write-Host ('URL         : {0}' -f [string]$state.url)
    Write-Host ''

    if (-not $NoBrowser) {
        Start-Process ([string]$state.url)
    }
    exit 0
} catch { Write-Host "BioDesign MVP: $($_.Exception.Message)" -ForegroundColor Red; exit 1 }
