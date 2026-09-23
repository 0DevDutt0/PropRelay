<#
.SYNOPSIS
    Orchestrates the complete local PropRelay Voice AI stack in separate visible windows.

.DESCRIPTION
    Launches:
    1. Local LiveKit Server (127.0.0.1:7880)
    2. Local Kokoro TTS Server (127.0.0.1:8880)
    3. PropRelay Token & Health API (127.0.0.1:8000)
    4. PropRelay Voice Agent Worker
    5. Web Frontend Dev Server (http://localhost:5173)
#>

[CmdletBinding()]
param ()

$ErrorActionPreference = "Stop"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "PropRelay — Local Realtime Voice Stack Orchestrator" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

$RepoRoot = Split-Path -Parent $PSScriptRoot

# 1. Start LiveKit Server
Write-Host "[1/5] Launching LiveKit Server (Port 7880)..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-File", "$RepoRoot\scripts\start_livekit.ps1"

# 2. Check Ollama
Write-Host "[2/5] Checking Ollama (Port 11434)..." -ForegroundColor Yellow
try {
    $olResp = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -Method Get -TimeoutSec 2 -ErrorAction Stop
    Write-Host "  -> Ollama is already active." -ForegroundColor Green
} catch {
    Write-Host "  -> Launching Ollama app..." -ForegroundColor Yellow
    Start-Process ollama -ArgumentList "serve"
}

# 3. Start Kokoro TTS
Write-Host "[3/5] Launching Kokoro TTS Server (Port 8880)..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-File", "$RepoRoot\scripts\start_kokoro.ps1"

# 4. Start Token & Health API
Write-Host "[4/5] Launching Token & Health API (Port 8000)..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-File", "$RepoRoot\scripts\start_api.ps1"

Start-Sleep -Seconds 3

# 5. Start PropRelay Agent Worker
Write-Host "[5/5] Launching PropRelay Voice Agent Worker..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-File", "$RepoRoot\scripts\start_agent.ps1"

Write-Host "`nAll PropRelay services have been launched in dedicated terminal windows." -ForegroundColor Green
Write-Host "Open frontend at: http://localhost:8000 or run .\scripts\start_frontend.ps1 for Vite HMR (http://localhost:5173)" -ForegroundColor Cyan
Write-Host "Health dashboard: http://127.0.0.1:8000/api/health" -ForegroundColor Cyan
