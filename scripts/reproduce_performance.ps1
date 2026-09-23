<#
.SYNOPSIS
    Reproduces the PropRelay performance benchmark and concurrency metrics suite.
.DESCRIPTION
    Executes empirical turn timeline measurements, endpointing latency analysis,
    and 1, 2, and 4 concurrent session load scaling tests.
    Generates reports in reports/performance/phase6_comparison.md and concurrency.md.
#>

[CmdletBinding()]
param(
    [int]$Iterations = 25,
    [switch]$VerboseOutput = $false
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
Set-Location $ProjectRoot

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "     PropRelay Performance Benchmark Reproducer           " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "Iterations: $Iterations per stage"
Write-Host "Reports Directory: reports/performance"
Write-Host ""

$VerboseFlag = if ($VerboseOutput) { "--verbose" } else { "" }

uv run python -m proprelay.performance.benchmark --all --iterations $Iterations --output reports/performance $VerboseFlag
$ExitCode = $LASTEXITCODE

Write-Host ""
Write-Host "Benchmark Output Reports:"
Write-Host "  - reports/performance/phase6_comparison.md"
Write-Host "  - reports/performance/concurrency.md"
Write-Host "  - reports/performance/summary.json"

if ($ExitCode -eq 0) {
    Write-Host "`nPerformance benchmarks successfully reproduced." -ForegroundColor Green
} else {
    Write-Host "`nPerformance benchmark exited with code $ExitCode." -ForegroundColor Red
}

exit $ExitCode
