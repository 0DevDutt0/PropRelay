<#
.SYNOPSIS
    Starts the local OpenAI-compatible Kokoro TTS Server.

.DESCRIPTION
    Verifies Python environment, port availability (default 8880),
    starts proprelay.tts.server, and displays health endpoint.
#>

[CmdletBinding()]
param (
    [string]$HostAddress = "127.0.0.1",
    [int]$Port = 8880
)

$ErrorActionPreference = "Stop"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "PropRelay — Local Kokoro TTS Server Launcher" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Check Python / uv availability
$uvCmd = Get-Command "uv" -ErrorAction SilentlyContinue
if (-not $uvCmd) {
    Write-Host "[ERROR] 'uv' package manager not found. Please install uv." -ForegroundColor Red
    exit 1
}

# 2. Check Port Availability
$portInUse = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue | Where-Object { $_.State -eq "Listen" }
if ($portInUse) {
    Write-Host "[ERROR] Port $Port is already in use by PID $($portInUse[0].OwningProcess)." -ForegroundColor Red
    exit 1
}

Write-Host "[INFO] Port $Port is available." -ForegroundColor Green
Write-Host "[INFO] Health URL: http://$HostAddress`:$Port/health" -ForegroundColor Cyan
Write-Host "[INFO] Speech URL: http://$HostAddress`:$Port/v1/audio/speech" -ForegroundColor Cyan
Write-Host "[INFO] Starting Kokoro TTS server (Press Ctrl+C to terminate)..." -ForegroundColor Yellow

$env:KOKORO_HOST = $HostAddress
$env:KOKORO_PORT = "$Port"

& uv run python -m proprelay.tts.server
