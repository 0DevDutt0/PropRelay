<#
.SYNOPSIS
    Downloads Kokoro ONNX model weights and voice embeddings to bin/kokoro.

.DESCRIPTION
    Retrieves kokoro-v1.0.onnx and voices-v1.0.bin from official release distribution.
    Keeps all model weights local and excluded from version control.
#>

[CmdletBinding()]
param (
    [string]$TargetDir = "$PSScriptRoot\..\bin\kokoro"
)

$ErrorActionPreference = "Stop"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "PropRelay — Local Kokoro Model Downloader" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

$TargetDir = [System.IO.Path]::GetFullPath($TargetDir)
if (-not (Test-Path $TargetDir)) {
    New-Item -ItemType Directory -Path $TargetDir -Force | Out-Null
}

$ModelUrl = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx"
$VoicesUrl = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin"

$ModelFile = Join-Path $TargetDir "kokoro-v1.0.onnx"
$VoicesFile = Join-Path $TargetDir "voices-v1.0.bin"

if (-not (Test-Path $ModelFile)) {
    Write-Host "[DOWNLOAD] Fetching Kokoro ONNX model (~300MB)..." -ForegroundColor Yellow
    Invoke-WebRequest -Uri $ModelUrl -OutFile $ModelFile
    Write-Host "[OK] Saved to: $ModelFile" -ForegroundColor Green
} else {
    Write-Host "[EXISTS] Kokoro ONNX model already present: $ModelFile" -ForegroundColor Green
}

if (-not (Test-Path $VoicesFile)) {
    Write-Host "[DOWNLOAD] Fetching Kokoro voice embeddings (~20MB)..." -ForegroundColor Yellow
    Invoke-WebRequest -Uri $VoicesUrl -OutFile $VoicesFile
    Write-Host "[OK] Saved to: $VoicesFile" -ForegroundColor Green
} else {
    Write-Host "[EXISTS] Kokoro voice embeddings already present: $VoicesFile" -ForegroundColor Green
}

Write-Host ""
Write-Host "Kokoro assets ready at: $TargetDir" -ForegroundColor Cyan
