<#
.SYNOPSIS
    PropRelay Local CI Pipeline
.DESCRIPTION
    Runs the complete continuous integration validation locally without external cloud dependencies:
    - Code quality & format check (ruff)
    - Strict static type checking (mypy)
    - Security scanner (bandit)
    - Claims scanner
    - Secrets scanner
    - Unit and security test suite (pytest)
    - Behavioral evaluation suite (runner)
#>

[CmdletBinding()]
param(
    [switch]$Quick = $false
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
Set-Location $ProjectRoot

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "        PropRelay Local CI Pipeline       " -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

Write-Host "`n[1/7] Running Ruff Lint & Format Checks..." -ForegroundColor Yellow
uv run ruff check .
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "`n[2/7] Running Mypy Static Type Checks..." -ForegroundColor Yellow
uv run mypy proprelay tests
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "`n[3/7] Running Bandit Security Scan..." -ForegroundColor Yellow
uv run bandit -c pyproject.toml -r proprelay
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "`n[4/7] Running Claims Truthfulness Scan..." -ForegroundColor Yellow
uv run python scripts/scan_claims.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "`n[5/7] Running Secrets Scan..." -ForegroundColor Yellow
uv run python scripts/scan_secrets.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "`n[6/7] Running Pytest Unit & Security Test Suite..." -ForegroundColor Yellow
uv run pytest tests/unit -v
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if (-not $Quick) {
    Write-Host "`n[7/7] Running 25 Behavioral Evaluation Scenarios..." -ForegroundColor Yellow
    uv run python -m proprelay.evaluation.runner --all
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} else {
    Write-Host "`n[7/7] Skipping Evaluation Scenarios (-Quick specified)" -ForegroundColor Gray
}

Write-Host "`n==========================================" -ForegroundColor Green
Write-Host "   LOCAL CI PASSED: ALL CHECKS GREEN      " -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
exit 0
