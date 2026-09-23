<#
.SYNOPSIS
    PropRelay Authoritative Release Gate Verification Script
.DESCRIPTION
    Executes all code quality, static typing, security, claim integrity, invariant tests,
    behavioral scenario evaluations, and frontend build checks.
    Fails fast if any release invariant is breached.
#>

[CmdletBinding()]
param(
    [switch]$SkipFrontend = $false,
    [switch]$VerboseOutput = $false
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
Set-Location $ProjectRoot

Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host "       PROPRELAY PHASE 7 AUTHORITATIVE RELEASE GATE              " -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host "Project Root: $ProjectRoot"
Write-Host "Timestamp:    $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss K')"
Write-Host ""

$TotalSteps = if ($SkipFrontend) { 9 } else { 10 }
$CurrentStep = 0
$FailedSteps = @()

function Run-GateStep {
    param(
        [string]$Name,
        [scriptblock]$Command
    )
    $script:CurrentStep++
    Write-Host "[$script:CurrentStep/$TotalSteps] Running $Name..." -ForegroundColor Yellow
    try {
        & $Command
        if ($LASTEXITCODE -ne 0) {
            throw "Step '$Name' exited with code $LASTEXITCODE"
        }
        Write-Host "  -> [PASS] $Name" -ForegroundColor Green
    }
    catch {
        Write-Host "  -> [FAIL] ${Name}: $_" -ForegroundColor Red
        $script:FailedSteps += $Name
    }
}

# Step 1: System Diagnostics
Run-GateStep "System Diagnostics" {
    uv run python -m proprelay.diagnostics
}

# Step 2: Code Quality & Linting
Run-GateStep "Ruff Linter & Formatter Check" {
    uv run ruff check .
}

# Step 3: Static Type Checking
Run-GateStep "Mypy Strict Static Typing" {
    uv run mypy proprelay tests
}

# Step 4: Security Vulnerability Scan (Bandit)
Run-GateStep "Bandit Static Security Audit" {
    uv run bandit -c pyproject.toml -r proprelay
}

# Step 5: Technical Claims & Sanity Scanner
Run-GateStep "Claims Scanner (Truthfulness & Provenance)" {
    uv run python scripts/scan_claims.py
}

# Step 6: Secrets & Credentials Scanner
Run-GateStep "Secrets Scanner" {
    uv run python scripts/scan_secrets.py
}

# Step 7: Unit & Architectural Invariant Tests
Run-GateStep "Pytest Unit & Invariant Test Suite" {
    uv run pytest tests/unit -v --tb=short
}

# Step 8: Behavioral Evaluation Suite & Release Gate
Run-GateStep "25-Scenario Evaluation Suite & Release Gate" {
    uv run python -m proprelay.evaluation.runner --all
}

# Step 9: Build Manifest Generation
Run-GateStep "Build Manifest Generation" {
    uv run python -m proprelay.build_manifest -o reports/build_manifest.json
}

# Step 10: Frontend Production Build
if (-not $SkipFrontend) {
    Run-GateStep "Frontend Production Build (pnpm build)" {
        pnpm --dir frontend build
    }
}

Write-Host ""
Write-Host "=================================================================" -ForegroundColor Cyan
if ($FailedSteps.Count -eq 0) {
    Write-Host "RELEASE GATE VERDICT: READY FOR RELEASE" -ForegroundColor Green
    Write-Host "All $TotalSteps verification steps passed without regression or policy breach."
    Write-Host "=================================================================" -ForegroundColor Cyan
    exit 0
} else {
    Write-Host "RELEASE GATE VERDICT: BLOCKED" -ForegroundColor Red
    Write-Host "Failed verification steps:"
    foreach ($f in $FailedSteps) {
        Write-Host "  - $f" -ForegroundColor Red
    }
    Write-Host "=================================================================" -ForegroundColor Cyan
    exit 1
}
