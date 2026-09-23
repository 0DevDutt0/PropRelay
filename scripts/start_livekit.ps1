# scripts/start_livekit.ps1
# Launches local standalone LiveKit Server in development mode.
# Binds locally to 127.0.0.1:7880 with dev credentials (devkey / secret).

[CmdletBinding()]
param (
    [switch]$Background = $false
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$BinDir = Join-Path $RepoRoot "bin"
$ServerExe = Join-Path $BinDir "livekit-server.exe"

if (-not (Test-Path $ServerExe)) {
    Write-Error "[LiveKit] livekit-server.exe not found in $BinDir.`nPlease run .\scripts\download_livekit.ps1 first."
    exit 1
}

# Check if port 7880 is already in use
$PortInUse = Get-NetTCPConnection -LocalPort 7880 -ErrorAction SilentlyContinue
if ($PortInUse) {
    Write-Host "[LiveKit] Port 7880 is already active (Process ID: $($PortInUse[0].OwningProcess)). LiveKit is likely already running." -ForegroundColor Yellow
    exit 0
}

Write-Host "[LiveKit] Starting LiveKit Server in dev mode..." -ForegroundColor Cyan
Write-Host "  Endpoint: ws://127.0.0.1:7880" -ForegroundColor Gray
Write-Host "  API Key:  devkey" -ForegroundColor Gray
Write-Host "  Secret:   secret" -ForegroundColor Gray

if ($Background) {
    $OutLog = Join-Path $BinDir "livekit-server.log"
    $ErrLog = Join-Path $BinDir "livekit-server-err.log"
    $Process = Start-Process -FilePath $ServerExe -ArgumentList "--dev" -PassThru -WindowStyle Hidden -RedirectStandardOutput $OutLog -RedirectStandardError $ErrLog
    Start-Sleep -Seconds 3
    if (-not $Process.HasExited) {
        Write-Host "[LiveKit] Server successfully started in background (PID: $($Process.Id))." -ForegroundColor Green
        Write-Host "[LiveKit] Logs: $OutLog" -ForegroundColor Gray
        Write-Host "[LiveKit] To terminate: Stop-Process -Id $($Process.Id) -Force" -ForegroundColor Gray
    } else {
        Write-Error "[LiveKit] Failed to start LiveKit server process. Check $OutLog and $ErrLog for details."
        exit 1
    }
} else {
    Write-Host "[LiveKit] Running in foreground. Press Ctrl+C to terminate." -ForegroundColor Cyan
    & $ServerExe --dev
}
