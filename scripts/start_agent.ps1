<#
.SYNOPSIS
    Starts the PropRelay LiveKit Agent worker process.

.DESCRIPTION
    Connects to local LiveKit server (127.0.0.1:7880), loads local STT (Faster-Whisper),
    Ollama LLM (qwen2.5:7b), local Kokoro TTS (8880), and typed property tools.
#>

[CmdletBinding()]
param (
    [string]$Mode = "dev" # dev or start
)

$ErrorActionPreference = "Stop"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "PropRelay — Realtime Voice Agent Worker Launcher" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# Check LiveKit port
$lkPort = Get-NetTCPConnection -LocalPort 7880 -ErrorAction SilentlyContinue | Where-Object { $_.State -eq "Listen" }
if (-not $lkPort) {
    Write-Host "[WARN] LiveKit Server not detected on port 7880. Launching may wait for server." -ForegroundColor Yellow
} else {
    Write-Host "[OK] LiveKit Server active on port 7880." -ForegroundColor Green
}

# Check Ollama port
try {
    $olResp = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -Method Get -TimeoutSec 2 -ErrorAction Stop
    Write-Host "[OK] Ollama active at http://127.0.0.1:11434" -ForegroundColor Green
} catch {
    Write-Host "[WARN] Ollama not responding on port 11434. Local LLM will fail if not started." -ForegroundColor Yellow
}

Write-Host "[INFO] Starting PropRelay Agent Worker ($Mode mode)..." -ForegroundColor Cyan

& uv run python -m proprelay.agent.worker $Mode
