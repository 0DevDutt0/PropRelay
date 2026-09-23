# PropRelay — Production Release Checklist

This authoritative checklist governs release qualification for PropRelay. No artifact or tag may be promoted without satisfying every gate condition below.

---

## 1. Automated Release Gate Criteria

Execute the full authoritative verification script:
```powershell
.\scripts\release_gate.ps1
```

| Verification Check | Tool / Mechanism | Acceptance Threshold | Mandatory? | Status |
| :--- | :--- | :--- | :--- | :--- |
| **System Diagnostics** | `python -m proprelay.diagnostics` | 0 FAIL checks; Python >= 3.12 | YES | [X] PASS |
| **Code Formatting & Linting** | `ruff check .` | 0 errors, 0 warnings | YES | [X] PASS |
| **Static Type Integrity** | `mypy proprelay tests` | Strict mode: 0 type errors | YES | [X] PASS |
| **Security Static Analysis** | `bandit -c pyproject.toml -r proprelay` | 0 High, 0 Medium severity issues | YES | [X] PASS |
| **Technical Claims Sanity** | `python scripts/scan_claims.py` | 100% compliant; zero ungrounded claims | YES | [X] PASS |
| **Credential & Secret Audit** | `python scripts/scan_secrets.py` | 0 detected secrets or private keys | YES | [X] PASS |
| **Unit & Invariant Suite** | `pytest tests/unit -v` | 100% green; 0 failures, 0 errors | YES | [X] PASS |
| **Behavioral Evaluation Suite** | `python -m proprelay.evaluation.runner --all` | 25/25 scenarios passed; Gate: `READY` | YES | [X] PASS |
| **Build Manifest Generation** | `python -m proprelay.build_manifest` | Clean provenance JSON generated | YES | [X] PASS |
| **Frontend Production Build** | `pnpm --dir frontend build` | Clean Vite production build; 0 TS errors | YES | [X] PASS |

---

## 2. Model Provenance & Licensing Review

Verify that all local neural models comply with open-source licenses for target distribution:
- [X] **Faster-Whisper STT**: MIT License (CTranslate2 / Systran / OpenAI).
- [X] **Qwen 2.5 Instruct LLM**: Apache-2.0 License (Alibaba / Qwen team).
- [X] **Kokoro-82M TTS**: Apache-2.0 License (hexgrad).
- [X] **LiveKit Server & SDKs**: Apache-2.0 License (LiveKit Inc).
- [X] Review complete documentation in [MODEL_LICENSES.md](file:///E:/work/Agentic%20Engineer%28Voice%20AI%29/PropRelay/docs/MODEL_LICENSES.md).

---

## 3. Security & Operational Hardening Verification

- [X] **Zero Cloud Data Leakage**: Validate that no audio bytes or transcripts are transmitted to external endpoints (verified in [PRIVACY.md](file:///E:/work/Agentic%20Engineer%28Voice%20AI%29/PropRelay/docs/PRIVACY.md)).
- [X] **FastAPI Security Headers**: Verify that responses include `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, and Content Security Policy.
- [X] **Payload Size Limits**: Verify that API server rejects payloads exceeding 64KB with HTTP 413.
- [X] **Input Boundary Sanitization**: Verify regex validation for participant identities and room names (`^[a-zA-Z0-9_\-\.]{1,64}$`).
- [X] **Token Expiration Defense**: Verify that expired WebRTC JWTs are rejected immediately without leeway (`leeway_seconds=0`).
- [X] **Two-Phase Confirmation Safety**: Verify that state mutations (`book_showing`, `reschedule_showing`, `cancel_showing`) require explicit pending action confirmation.

---

## 4. Pre-Launch Readiness & Probe Verification

1. Start all supporting local services:
   ```powershell
   .\scripts\start_livekit.ps1
   .\scripts\start_kokoro.ps1
   ollama serve
   ```
2. Launch the FastAPI server:
   ```powershell
   .\scripts\start_api.ps1
   ```
3. Test Health & Readiness Endpoints:
   ```powershell
   # Liveness Probe (HTTP 200)
   curl http://127.0.0.1:8000/api/health
   
   # Deep Readiness Probe (Verifies LiveKit connectivity & model services)
   curl http://127.0.0.1:8000/api/readiness
   ```
4. Confirm WebRTC Agent Worker connects cleanly:
   ```powershell
   .\scripts\start_agent.ps1
   ```

---

## 5. Rollback & Disaster Recovery Procedures

If an unrecoverable failure occurs during deployment or demonstration:
1. **Kill Worker Processes**:
   ```powershell
   Get-Process -Name "python", "livekit-server" -ErrorAction SilentlyContinue | Stop-Process -Force
   ```
2. **Clean Ephemeral Runtime State**:
   ```powershell
   .\scripts\clean_local_state.ps1 -Force
   ```
3. **Restore Known-Good Backup**:
   ```powershell
   .\scripts\import_state.ps1 -ArchiveFile backups/proprelay_state_latest.zip -Force
   ```
4. **Rerun Diagnostics**:
   ```powershell
   uv run python -m proprelay.diagnostics
   ```
