<#
.SYNOPSIS
    Imports and restores local state from an export archive.
.DESCRIPTION
    Extracts data and journals from a specified ZIP backup into the workspace.
    Requires -Force to overwrite existing data.
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)]
    [string]$ArchiveFile,
    [switch]$Force = $false
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
Set-Location $ProjectRoot

if (-not (Test-Path $ArchiveFile)) {
    Write-Error "Backup archive not found: $ArchiveFile"
    exit 1
}

if (-not $Force) {
    Write-Host "SAFETY GUARD TRIGGERED: -Force switch is required to restore state." -ForegroundColor Yellow
    Write-Host "Usage: .\scripts\import_state.ps1 -ArchiveFile <path.zip> -Force"
    exit 1
}

Write-Host "Restoring PropRelay state from $ArchiveFile..." -ForegroundColor Cyan
Expand-Archive -Path $ArchiveFile -DestinationPath $ProjectRoot -Force

Write-Host "State restoration completed successfully." -ForegroundColor Green
