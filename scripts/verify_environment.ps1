# scripts/verify_environment.ps1
# PropRelay Environment Verifier: Audits local toolchains, runtimes, and services.
# Read-only inspection. Emits [PASS], [WARN], or [FAIL] status codes.

$ErrorActionPreference = "Continue"

$PassCount = 0
$WarnCount = 0
$FailCount = 0

function Report-Check {
    param (
        [string]$Name,
        [string]$Status, # PASS, WARN, FAIL
        [string]$Details
    )
    switch ($Status) {
        "PASS" {
            Write-Host "  [PASS] " -ForegroundColor Green -NoNewline
            Write-Host "$Name " -ForegroundColor White -NoNewline
            Write-Host "($Details)" -ForegroundColor Gray
            $script:PassCount++
        }
        "WARN" {
            Write-Host "  [WARN] " -ForegroundColor Yellow -NoNewline
            Write-Host "$Name " -ForegroundColor White -NoNewline
            Write-Host "($Details)" -ForegroundColor Yellow
            $script:WarnCount++
        }
        "FAIL" {
            Write-Host "  [FAIL] " -ForegroundColor Red -NoNewline
            Write-Host "$Name " -ForegroundColor White -NoNewline
            Write-Host "($Details)" -ForegroundColor Red
            $script:FailCount++
        }
    }
}

Write-Host "`n========================================================" -ForegroundColor Cyan
Write-Host " PropRelay - Local Environment Verification Audit" -ForegroundColor Cyan
Write-Host "========================================================`n" -ForegroundColor Cyan

# 1. Python Check
try {
    $PyOut = python --version 2>&1
    if ($LASTEXITCODE -eq 0 -and $PyOut -match 'Python 3\.12') {
        Report-Check -Name "Python 3.12" -Status "PASS" -Details $PyOut.Trim()
    } elseif ($LASTEXITCODE -eq 0) {
        Report-Check -Name "Python Version" -Status "WARN" -Details "$($PyOut.Trim()) - Python 3.12 recommended"
    } else {
        Report-Check -Name "Python" -Status "FAIL" -Details "python command failed"
    }
} catch {
    Report-Check -Name "Python" -Status "FAIL" -Details "Not found on PATH"
}

# 2. uv Check
try {
    $UvOut = uv --version 2>&1
    if ($LASTEXITCODE -eq 0) {
        Report-Check -Name "uv Package Manager" -Status "PASS" -Details $UvOut.Trim()
    } else {
        Report-Check -Name "uv Package Manager" -Status "FAIL" -Details "uv command returned error"
    }
} catch {
    Report-Check -Name "uv Package Manager" -Status "FAIL" -Details "Not found on PATH"
}

# 3. Node.js Check
try {
    $NodeOut = node --version 2>&1
    if ($LASTEXITCODE -eq 0) {
        Report-Check -Name "Node.js Runtime" -Status "PASS" -Details $NodeOut.Trim()
    } else {
        Report-Check -Name "Node.js Runtime" -Status "WARN" -Details "node returned error"
    }
} catch {
    Report-Check -Name "Node.js Runtime" -Status "WARN" -Details "Not found on PATH (needed in Phase 4)"
}

# 4. pnpm Check
try {
    $PnpmOut = pnpm --version 2>&1
    if ($LASTEXITCODE -eq 0) {
        Report-Check -Name "pnpm Package Manager" -Status "PASS" -Details "v$($PnpmOut.Trim())"
    } else {
        Report-Check -Name "pnpm Package Manager" -Status "WARN" -Details "pnpm returned error"
    }
} catch {
    Report-Check -Name "pnpm Package Manager" -Status "WARN" -Details "Not found on PATH (needed in Phase 4)"
}

# 5. ffmpeg Check
try {
    $FfmpegOut = ffmpeg -version 2>&1
    if ($LASTEXITCODE -eq 0) {
        $FfmpegFirstLine = $FfmpegOut[0].ToString()
        Report-Check -Name "ffmpeg Audio Engine" -Status "PASS" -Details $FfmpegFirstLine.Substring(0, [Math]::Min(35, $FfmpegFirstLine.Length))
    } else {
        Report-Check -Name "ffmpeg Audio Engine" -Status "WARN" -Details "ffmpeg not detected"
    }
} catch {
    Report-Check -Name "ffmpeg Audio Engine" -Status "WARN" -Details "Not found on PATH (needed in Phase 3)"
}

# 6. GPU Visibility (NVIDIA SMI)
try {
    $SmiExe = (Get-Command nvidia-smi.exe -ErrorAction SilentlyContinue).Source
    if ($SmiExe) {
        $SmiOut = & $SmiExe --query-gpu=name,memory.total,driver_version --format=csv,noheader 2>&1
        if ($LASTEXITCODE -eq 0 -and $SmiOut) {
            $GpuText = ($SmiOut -join " ").Trim()
            Report-Check -Name "NVIDIA GPU and CUDA" -Status "PASS" -Details $GpuText
        } else {
            Report-Check -Name "NVIDIA GPU and CUDA" -Status "WARN" -Details "nvidia-smi returned code $LASTEXITCODE"
        }
    } else {
        Report-Check -Name "NVIDIA GPU and CUDA" -Status "WARN" -Details "No NVIDIA GPU detected (CPU mode fallback)"
    }
} catch {
    Report-Check -Name "NVIDIA GPU and CUDA" -Status "WARN" -Details "nvidia-smi error: $_"
}

# 7. Local LiveKit Binary Check
$RepoRoot = Split-Path -Parent $PSScriptRoot
$LkServerExe = Join-Path $RepoRoot "bin\livekit-server.exe"
if (Test-Path $LkServerExe) {
    try {
        $LkVer = & $LkServerExe --version
        Report-Check -Name "LiveKit Server Binary" -Status "PASS" -Details "$LkVer located at bin/livekit-server.exe"
    } catch {
        Report-Check -Name "LiveKit Server Binary" -Status "FAIL" -Details "Failed executing $LkServerExe"
    }
} else {
    Report-Check -Name "LiveKit Server Binary" -Status "WARN" -Details "Not found in bin/ (run .\scripts\download_livekit.ps1)"
}

# 8. LiveKit Port Check (7880)
$LkPort = Get-NetTCPConnection -LocalPort 7880 -ErrorAction SilentlyContinue
if ($LkPort) {
    Report-Check -Name "LiveKit Port 7880" -Status "PASS" -Details "Port active (PID: $($LkPort[0].OwningProcess))"
} else {
    Report-Check -Name "LiveKit Port 7880" -Status "WARN" -Details "Not currently listening (start via .\scripts\start_livekit.ps1)"
}

# 9. Ollama Service and Model Check
try {
    $OllamaResp = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -Method Get -TimeoutSec 3 -ErrorAction Stop
    $Models = $OllamaResp.models | ForEach-Object { $_.name }
    $QwenFound = $Models -match 'qwen2\.5:7b'
    if ($QwenFound) {
        Report-Check -Name "Ollama Service and Model" -Status "PASS" -Details "Endpoint online, qwen2.5:7b model confirmed"
    } else {
        Report-Check -Name "Ollama Service and Model" -Status "WARN" -Details "Endpoint online, but qwen2.5:7b not found"
    }
} catch {
    Report-Check -Name "Ollama Service and Model" -Status "WARN" -Details "Ollama not running at http://127.0.0.1:11434 (needed in Phase 3)"
}

# 10. Kokoro TTS Service Check
try {
    $KokoroResp = Invoke-RestMethod -Uri "http://127.0.0.1:8880/health" -Method Get -TimeoutSec 2 -ErrorAction Stop
    Report-Check -Name "Kokoro TTS Service" -Status "PASS" -Details "Online at http://127.0.0.1:8880/health (Model loaded: $($KokoroResp.model_loaded))"
} catch {
    Report-Check -Name "Kokoro TTS Service" -Status "WARN" -Details "Not currently running at http://127.0.0.1:8880 (start via .\scripts\start_kokoro.ps1)"
}

# 11. Faster-Whisper and CTranslate2 Python Check
try {
    $SttCheck = uv run python -c "import faster_whisper, ctranslate2; print(f'CUDA: {ctranslate2.get_cuda_device_count()}')" 2>&1
    if ($LASTEXITCODE -eq 0) {
        Report-Check -Name "faster-whisper and CTranslate2" -Status "PASS" -Details $SttCheck.Trim()
    } else {
        Report-Check -Name "faster-whisper and CTranslate2" -Status "WARN" -Details "Module import warning"
    }
} catch {
    Report-Check -Name "faster-whisper and CTranslate2" -Status "WARN" -Details "Error testing faster-whisper"
}

Write-Host "`n--------------------------------------------------------" -ForegroundColor Gray
Write-Host " Verification Summary: $PassCount PASS, $WarnCount WARN, $FailCount FAIL" -ForegroundColor $(if ($FailCount -gt 0) { "Red" } elseif ($WarnCount -gt 0) { "Yellow" } else { "Green" })
Write-Host "========================================================`n" -ForegroundColor Cyan

if ($FailCount -gt 0) {
    exit 1
} else {
    exit 0
}
