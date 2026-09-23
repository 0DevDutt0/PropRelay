<#
.SYNOPSIS
    Starts the Vite development server for the PropRelay frontend (port 5173).
#>

[CmdletBinding()]
param ()

$ErrorActionPreference = "Stop"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "PropRelay — Frontend Dev Server" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

$frontendDir = Join-Path $PSScriptRoot "..\frontend"
Set-Location $frontendDir

& pnpm dev
