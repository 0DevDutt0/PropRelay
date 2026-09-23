# PropRelay — Operational Runbook & Troubleshooting Guide

This operational runbook provides field-tested procedures for launching, monitoring, troubleshooting, and recovering the PropRelay real-time Voice AI system.

---

## 1. System Architecture & Standard Ports

| Service | Protocol / Transport | Local Port | Health / Probe Endpoint |
| :--- | :--- | :--- | :--- |
| **FastAPI Backend Server** | HTTP / REST | `8000` | `GET http://127.0.0.1:8000/api/health` |
| **Deep Readiness Probe** | HTTP / REST | `8000` | `GET http://127.0.0.1:8000/api/readiness` |
| **LiveKit WebRTC Server** | WebSockets / WebRTC | `7880` (HTTP) / `7881` (RTC) | `GET http://127.0.0.1:7880/` |
| **Ollama LLM Engine** | HTTP API | `11434` | `GET http://127.0.0.1:11434/api/tags` |
| **Kokoro ONNX TTS Server** | HTTP API | `8880` | `GET http://127.0.0.1:8880/health` |
| **Frontend Web App** | HTTP / Vite Dev Server | `5173` | `GET http://127.0.0.1:5173/` |

---

## 2. Standard Startup Sequence

### Option A: Unified Orchestrator
Launch the complete coordinated stack with a single command:
```powershell
.\scripts\run_local.ps1
```

### Option B: Step-by-Step Manual Launch
1. **LiveKit Server**:
   ```powershell
   .\scripts\start_livekit.ps1
   ```
2. **Kokoro TTS Server**:
   ```powershell
   .\scripts\start_kokoro.ps1
   ```
3. **Ollama LLM**:
   ```powershell
   ollama serve
   ```
4. **FastAPI Backend**:
   ```powershell
   .\scripts\start_api.ps1
   ```
5. **Frontend Web UI**:
   ```powershell
   .\scripts\start_frontend.ps1
   ```
6. **LiveKit Agent Worker**:
   ```powershell
   .\scripts\start_agent.ps1
   ```

---

## 3. Incident Management & Common Failure Modes

### 3.1 Port Already in Use (HTTP 400 / Bind Exception)
**Symptom**: `OSError: [WinError 10048] Only one usage of each socket address is normally permitted.`
**Resolution**:
1. Identify the blocking process on the conflicting port (e.g. 8000):
   ```powershell
   Get-NetTCPConnection -LocalPort 8000 | Select-Object OwningProcess
   ```
2. Terminate the orphan process:
   ```powershell
   Stop-Process -Id <PID> -Force
   ```

### 3.2 CUDA Out of Memory (OOM) or GPU Thrashing
**Symptom**: `RuntimeError: CUDA out of memory. Tried to allocate...` during STT or LLM inference.
**Resolution**:
1. Inspect current GPU allocation across running processes:
   ```powershell
   nvidia-smi
   ```
2. Verify that total allocation does not exceed host VRAM.
3. If memory is tight, switch Ollama to the compact 3B model:
   ```powershell
   $env:PROPRELAY_OLLAMA_MODEL = "qwen2.5:3b"
   ```
4. Switch Whisper compute type to int8 CPU mode if needed:
   ```powershell
   $env:PROPRELAY_WHISPER_DEVICE = "cpu"
   $env:PROPRELAY_WHISPER_COMPUTE_TYPE = "int8"
   ```

### 3.3 WebRTC Audio Track Silent / Microphone Disconnected
**Symptom**: WebRTC room connects successfully, but participant audio is not transcribed by Whisper.
**Resolution**:
1. Verify browser microphone permissions in `chrome://settings/content/microphone`.
2. Inspect frontend audio meter in the UI. If the bar does not move when speaking, the WebRTC audio track is muted or unbound.
3. Check agent logs for `track_subscribed` events:
   ```powershell
   Get-Content logs/agent.log -Tail 50 -Wait
   ```

### 3.4 Stale Proposal or Blocked Conversation State
**Symptom**: Agent repeatedly asks to confirm a showing that the user already abandoned.
**Resolution**:
1. The conversational state machine enforces that navigating to another property or inquiring about different dates immediately clears stale pending actions.
2. In the terminal / browser UI, say: *"Cancel that, let's look at another property."*
3. To deterministically verify state machine behavior:
   ```powershell
   uv run python -m proprelay.evaluation.replay --scenario S07 -v
   ```

---

## 4. Disaster Recovery & Emergency Reset

To completely reset the system to a clean, known-good baseline state:
```powershell
# 1. Terminate all background processes
Get-Process -Name "python", "livekit-server" -ErrorAction SilentlyContinue | Stop-Process -Force

# 2. Safely purge ephemeral session DBs, caches, and failure fixtures
.\scripts\clean_local_state.ps1 -Force

# 3. Verify system readiness
uv run python -m proprelay.diagnostics

# 4. Verify behavioral invariants
uv run python -m proprelay.evaluation.runner --all
```
