<#
.SYNOPSIS
    Exports current local state, bookings, leads, and event journals.
.DESCRIPTION
    Creates a timestamped ZIP archive in the backups/ directory.
#>

[CmdletBinding()]
param(
    [string]$DestinationDir = "backups"
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
Set-Location $ProjectRoot

$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$BackupFolder = Join-Path $ProjectRoot $DestinationDir
if (-not (Test-Path $BackupFolder)) {
    New-Item -ItemType Directory -Path $BackupFolder -Force | Out-Null
}

$ZipFile = Join-Path $BackupFolder "proprelay_state_$Timestamp.zip"
Write-Host "Exporting PropRelay state to $ZipFile..." -ForegroundColor Cyan

# Gather files to export: data directory, reports
$TempExportDir = Join-Path $env:TEMP "proprelay_export_$Timestamp"
if (Test-Path $TempExportDir) { Remove-Item $TempExportDir -Recurse -Force }
New-Item -ItemType Directory -Path $TempExportDir | Out-Null

if (Test-Path "data") {
    Copy-Item -Path "data" -Destination (Join-Path $TempExportDir "data") -Recurse -Force
}
if (Test-Path "reports") {
    Copy-Item -Path "reports" -Destination (Join-Path $TempExportDir "reports") -Recurse -Force
}

Compress-Archive -Path "$TempExportDir\*" -DestinationPath $ZipFile -Force
Remove-Item $TempExportDir -Recurse -Force

Write-Host "Export completed successfully:" -ForegroundColor Green
Write-Host "  Archive: $ZipFile"
Write-Host "  Size:    $((Get-Item $ZipFile).Length / 1KB) KB"
