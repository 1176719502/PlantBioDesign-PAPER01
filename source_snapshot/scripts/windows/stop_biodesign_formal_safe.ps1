[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$launcherModule = Join-Path $repoRoot 'scripts\windows\biodesign_formal_launcher.py'

function Get-BootstrapCommand {
    $candidates = @(
        @((Join-Path $repoRoot '.venv312\Scripts\python.exe')),
        @((Join-Path $repoRoot '.venv\Scripts\python.exe')),
        @('py', '-3.12'),
        @('py', '-3.11'),
        @('py', '-3.10'),
        @('python'),
        @('py')
    )
    foreach ($candidate in $candidates) {
        try {
            & $candidate[0] @($candidate | Select-Object -Skip 1) '-c' 'import sys' *> $null
            if ($LASTEXITCODE -eq 0) { return ,$candidate }
        } catch { }
    }
    throw 'No Python interpreter is available to run the formal stop helper.'
}

try {
    $bootstrap = Get-BootstrapCommand
    $output = & $bootstrap[0] @($bootstrap | Select-Object -Skip 1) $launcherModule 'stop' '--repo-root' $repoRoot
    $lines = @($output | Where-Object { $_ -and $_.ToString().Trim() })
    $lastLine = if ($lines.Count -gt 0) { $lines[-1] } else { '' }
    if ($LASTEXITCODE -ne 0) {
        try {
            $failure = $lastLine | ConvertFrom-Json
            Write-Host "BioDesign Studio: $($failure.message)" -ForegroundColor Red
        } catch {
            Write-Host "BioDesign Studio: $lastLine" -ForegroundColor Red
        }
        exit $LASTEXITCODE
    }
    $result = $lastLine | ConvertFrom-Json
    Write-Host ('BioDesign Studio: {0}' -f [string]$result.message)
    exit 0
} catch {
    Write-Host "BioDesign Studio: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
