# scripts/download_livekit.ps1
# Downloads and extracts official standalone Windows binaries for LiveKit Server and CLI.
# Binaries are placed into bin/ (gitignored).

[CmdletBinding()]
param (
    [string]$ServerVersion = "1.13.7",
    [string]$CliVersion = "2.18.8",
    [switch]$Force = $false
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$BinDir = Join-Path $RepoRoot "bin"

if (-not (Test-Path $BinDir)) {
    New-Item -ItemType Directory -Path $BinDir -Force | Out-Null
}

$ServerExe = Join-Path $BinDir "livekit-server.exe"
$CliExe = Join-Path $BinDir "lk.exe"

# 1. Download and Extract LiveKit Server
if ((-not (Test-Path $ServerExe)) -or $Force) {
    Write-Host "[LiveKit] Downloading LiveKit Server v$ServerVersion (Windows amd64)..." -ForegroundColor Cyan
    $ServerUrl = "https://github.com/livekit/livekit/releases/download/v$ServerVersion/livekit_${ServerVersion}_windows_amd64.zip"
    $ServerZip = Join-Path $BinDir "livekit_server.zip"

    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 -bor [Net.SecurityProtocolType]::Tls13
        Invoke-WebRequest -Uri $ServerUrl -OutFile $ServerZip -UseBasicParsing
        
        Write-Host "[LiveKit] Extracting LiveKit Server to $BinDir..." -ForegroundColor Cyan
        Expand-Archive -Path $ServerZip -DestinationPath $BinDir -Force
        Remove-Item $ServerZip -Force -ErrorAction SilentlyContinue
    }
    catch {
        Write-Error "[LiveKit] Failed to download or extract LiveKit Server from ${ServerUrl} - error: $_"
        exit 1
    }
}
else {
    Write-Host "[LiveKit] LiveKit Server already present at $ServerExe (use -Force to re-download)." -ForegroundColor Green
}

# 2. Download and Extract LiveKit CLI (lk.exe)
if ((-not (Test-Path $CliExe)) -or $Force) {
    Write-Host "[LiveKit] Downloading LiveKit CLI v$CliVersion (Windows amd64)..." -ForegroundColor Cyan
    $CliUrl = "https://github.com/livekit/livekit-cli/releases/download/v$CliVersion/lk_${CliVersion}_windows_amd64.zip"
    $CliZip = Join-Path $BinDir "lk_cli.zip"

    try {
        Invoke-WebRequest -Uri $CliUrl -OutFile $CliZip -UseBasicParsing
        
        Write-Host "[LiveKit] Extracting LiveKit CLI to $BinDir..." -ForegroundColor Cyan
        Expand-Archive -Path $CliZip -DestinationPath $BinDir -Force
        Remove-Item $CliZip -Force -ErrorAction SilentlyContinue
    }
    catch {
        Write-Warning "[LiveKit] Optional LiveKit CLI download failed: $_"
    }
}
else {
    Write-Host "[LiveKit] LiveKit CLI already present at $CliExe." -ForegroundColor Green
}

# 3. Verify executables and report versions
if (Test-Path $ServerExe) {
    Write-Host "`n[LiveKit Server Version]" -ForegroundColor Green
    & $ServerExe --version
} else {
    Write-Error "[LiveKit] Verification failed: $ServerExe does not exist."
    exit 1
}

if (Test-Path $CliExe) {
    Write-Host "`n[LiveKit CLI Version]" -ForegroundColor Green
    & $CliExe --version
}

Write-Host "`n[LiveKit] Download and setup completed successfully." -ForegroundColor Green
