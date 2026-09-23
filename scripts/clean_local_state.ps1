<#
.SYNOPSIS
    Cleans temporary local state, session databases, event logs, cache, and build artifacts.
.DESCRIPTION
    Requires -Force switch to prevent accidental deletion.
    Preserves all seed catalog data (data/listings.json, data/showings.json, data/benchmark_utterances.json).
#>

[CmdletBinding()]
param(
    [switch]$Force = $false,
    [switch]$CleanFrontend = $false
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
Set-Location $ProjectRoot

if (-not $Force) {
    Write-Host "SAFETY GUARD TRIGGERED: -Force switch is required to clean local state." -ForegroundColor Yellow
    Write-Host "Usage: .\scripts\clean_local_state.ps1 -Force [-CleanFrontend]"
    Write-Host "This operation will safely remove:"
    Write-Host "  - Runtime databases (data/*.db, data/*.sqlite)"
    Write-Host "  - Session event journals (data/events.jsonl) and logs"
    Write-Host "  - Python __pycache__, .pytest_cache, and test failure dumps"
    Write-Host "  - (Optional) Frontend build output (frontend/dist/) if -CleanFrontend is passed"
    Write-Host "Catalog fixtures (listings.json, showings.json) are NEVER deleted."
    exit 1
}

Write-Host "Cleaning PropRelay runtime state..." -ForegroundColor Cyan

# 1. Clean runtime state databases and transient journals (leave JSON fixtures intact)
$DbFiles = Get-ChildItem -Path "data" -Include "*.db", "*.sqlite", "*.sqlite3", "*.log" -Recurse -ErrorAction SilentlyContinue
foreach ($f in $DbFiles) {
    Write-Host "Removing runtime database/log: $($f.FullName)"
    Remove-Item $f.FullName -Force
}

if (Test-Path "data/events.jsonl") {
    Write-Host "Resetting transient event journal: data/events.jsonl"
    Remove-Item "data/events.jsonl" -Force
}

# 2. Clean temporary failure fixtures if any
if (Test-Path "reports/evaluation/failures") {
    $Failures = Get-ChildItem -Path "reports/evaluation/failures" -Filter "*.json" -ErrorAction SilentlyContinue
    foreach ($f in $Failures) {
        Remove-Item $f.FullName -Force
    }
}

# 3. Clean Python cache
Get-ChildItem -Path . -Include "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache" -Recurse -Directory -ErrorAction SilentlyContinue | ForEach-Object {
    Write-Host "Removing cache directory: $($_.FullName)"
    Remove-Item $_.FullName -Recurse -Force
}

# 4. Clean Frontend build output (only if requested)
if ($CleanFrontend -and (Test-Path "frontend/dist")) {
    Write-Host "Removing frontend/dist build directory..."
    Remove-Item "frontend/dist" -Recurse -Force
}

Write-Host "PropRelay local runtime state cleaned successfully." -ForegroundColor Green
Write-Host "Seed catalog fixtures preserved in data/ (listings.json, showings.json)."
