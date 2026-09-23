<#
.SYNOPSIS
    Starts the PropRelay Token & Health API Service (port 8000).
#>

[CmdletBinding()]
param (
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "PropRelay — Token & Health API Service" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

$portInUse = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue | Where-Object { $_.State -eq "Listen" }
if ($portInUse) {
    Write-Host "[ERROR] Port $Port is already in use by PID $($portInUse[0].OwningProcess)." -ForegroundColor Red
    exit 1
}

Write-Host "[INFO] Starting Token API on http://127.0.0.1:$Port" -ForegroundColor Green
$env:API_PORT = "$Port"
& uv run python -m proprelay.api.server
