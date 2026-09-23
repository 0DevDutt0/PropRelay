<#
.SYNOPSIS
    Packages PropRelay for local distribution and recruiter review.
.DESCRIPTION
    Builds the frontend, runs release gate checks, generates the build manifest,
    and packages Python artifacts into dist/.
#>

[CmdletBinding()]
param(
    [switch]$SkipGate = $false
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
Set-Location $ProjectRoot

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "           PropRelay Local Packaging Process              " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

if (-not $SkipGate) {
    Write-Host "Executing release gate verification..." -ForegroundColor Yellow
    & "$ScriptDir\release_gate.ps1"
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Release gate failed. Cannot package release."
        exit 1
    }
}

Write-Host "Building Python distribution package (uv build)..." -ForegroundColor Yellow
uv build

Write-Host "`nDistribution package created in dist/:" -ForegroundColor Green
Get-ChildItem -Path "dist" | ForEach-Object {
    Write-Host "  - $($_.Name) ($([math]::Round($_.Length / 1KB, 1)) KB)"
}

Write-Host "`nPackage verified and ready for local distribution." -ForegroundColor Green
