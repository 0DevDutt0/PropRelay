<#
.SYNOPSIS
    PropRelay Master Demonstration Launcher
.DESCRIPTION
    Provides a unified, high-reliability entry point for demonstrating PropRelay:
    - 'voice' (default): Validates environment, launches full local stack, prints interactive walkthrough
    - 'eval': Runs the 25-scenario deterministic evaluation suite and prints gate verdict
    - 'replay': Deterministically replays any scenario (e.g. -Scenario S04, S16) with event traces
    - 'diagnostics': Runs hardware, CUDA, and environment introspection
    - 'reset': Safely cleans transient runtime state while preserving domain fixtures
#>

[CmdletBinding()]
param(
    [ValidateSet("voice", "eval", "replay", "diagnostics", "reset")]
    [string]$Mode = "voice",
    [string]$Scenario = "S04"
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
Set-Location $ProjectRoot

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "          PropRelay Master Demonstration Launcher         " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "Selected Mode: $Mode" -ForegroundColor Green
Write-Host "Project Root:  $ProjectRoot"
Write-Host ""

switch ($Mode) {
    "voice" {
        Write-Host "[Step 1/3] Running environment and prerequisite diagnostics..." -ForegroundColor Yellow
        uv run python -m proprelay.diagnostics
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[ERROR] Environment diagnostics failed. Please review errors above." -ForegroundColor Red
            exit $LASTEXITCODE
        }

        Write-Host "`n[Step 2/3] Launching full local zero-cost stack via scripts\run_local.ps1..." -ForegroundColor Yellow
        & "$ScriptDir\run_local.ps1"

        Write-Host "`n==========================================================" -ForegroundColor Green
        Write-Host "            PROPRELAY LOCAL DEMO IS LIVE!                 " -ForegroundColor Green
        Write-Host "==========================================================" -ForegroundColor Green
        Write-Host "Web Interface:      http://localhost:8000" -ForegroundColor Cyan
        Write-Host "API Health Probe:   http://127.0.0.1:8000/api/health" -ForegroundColor Cyan
        Write-Host "Deep Readiness:     http://127.0.0.1:8000/api/readiness" -ForegroundColor Cyan
        Write-Host "LiveKit Server:     http://127.0.0.1:7880" -ForegroundColor Cyan
        Write-Host "Kokoro TTS:         http://127.0.0.1:8880/health" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "WHAT TO SAY (3-Minute Demo Sequence):" -ForegroundColor Yellow
        Write-Host "  1. Greeting:     Click 'Start Voice Call', allow mic, say 'Hello!'"
        Write-Host "  2. Search:       'I'm looking for a 2-bedroom apartment in Metropolis under $3,000.'"
        Write-Host "  3. Select:       'Tell me more about the first one.'"
        Write-Host "  4. Schedule:     'What showings are available today?'"
        Write-Host "  5. Stage & Book: 'Can you book the 1 PM slot for Alex Smith?'"
        Write-Host "  6. Confirm:      'Yes, please confirm that.' -> Observe showing.booked event!"
        Write-Host "  7. Safety Test:  'Can you book the 3:30 PM slot?' -> Rejected (already occupied)!"
        Write-Host "==========================================================" -ForegroundColor Green
    }
    "eval" {
        Write-Host "Running 25-scenario deterministic evaluation suite..." -ForegroundColor Yellow
        & "$ScriptDir\reproduce_evaluation.ps1"
    }
    "replay" {
        Write-Host "Replaying scenario $Scenario with deterministic runner..." -ForegroundColor Yellow
        uv run python -m proprelay.evaluation.replay --scenario $Scenario -v
    }
    "diagnostics" {
        Write-Host "Running system diagnostics..." -ForegroundColor Yellow
        uv run python -m proprelay.diagnostics
    }
    "reset" {
        Write-Host "Cleaning transient runtime state while preserving fixtures..." -ForegroundColor Yellow
        & "$ScriptDir\clean_local_state.ps1" -Force
    }
}
