<#
.SYNOPSIS
    Reproduces the full PropRelay behavioral evaluation suite.
.DESCRIPTION
    Runs all 25 deterministic evaluation scenarios across discovery, availability,
    safety, context switching, clarification, recovery, and adversarial prompt injection.
    Generates reports in reports/evaluation/release_gate.json and .md.
#>

[CmdletBinding()]
param(
    [switch]$SemanticLLM = $false,
    [string]$Scenario = ""
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
Set-Location $ProjectRoot

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "     PropRelay Behavioral Evaluation Reproducer           " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

$ArgsList = @()
if ($Scenario -ne "") {
    Write-Host "Running specific scenario: $Scenario" -ForegroundColor Yellow
    $ArgsList += "--scenario"
    $ArgsList += $Scenario
} else {
    Write-Host "Running full suite (25 scenarios)..." -ForegroundColor Yellow
    $ArgsList += "--all"
}

if ($SemanticLLM) {
    Write-Host "Semantic LLM evaluation judge enabled (local Ollama)" -ForegroundColor Yellow
    $ArgsList += "--semantic-llm"
}

uv run python -m proprelay.evaluation.runner @ArgsList
$RunnerExit = $LASTEXITCODE

Write-Host "`nEvaluation Artifacts:"
Write-Host "  - reports/evaluation/latest.json"
Write-Host "  - reports/evaluation/latest.md"
Write-Host "  - reports/evaluation/release_gate.json"
Write-Host "  - reports/evaluation/release_gate.md"

if ($RunnerExit -eq 0) {
    Write-Host "`nResult: READY (Pass Rate 100%, All Invariants Satisfied)" -ForegroundColor Green
} else {
    Write-Host "`nResult: BLOCKED (One or more scenario checks failed)" -ForegroundColor Red
}

exit $RunnerExit
