# PropRelay — Data Privacy, Security Boundaries & Local Retention Policy

This document establishes the authoritative data privacy, regulatory posture, and retention policies governing the PropRelay voice concierge architecture.

---

## 1. Zero Cloud Data Leakage Guarantee

PropRelay is engineered from first principles as an **offline-capable, local-first system**.

```
[User Audio Mic] ──WebRTC PCM──► [Local LiveKit Server (127.0.0.1:7880)]
                                         │
                                   Local IPC/WSS
                                         ▼
[Local TTS (Kokoro ONNX)] ◄── [Local Agent Worker] ◄── [Local Whisper STT]
          │                              │
          └─────────── Local LLM ────────┘
                    (Ollama 127.0.0.1:11434)
```

- **Zero Cloud Transmission**: At no point in the real-time pipeline is audio, text, metadata, or telemetry sent to external third-party cloud servers (such as OpenAI, Deepgram, ElevenLabs, Google, or AWS).
- **Network Interface Isolation**: By default, all service bindings (`FastAPI`, `LiveKit`, `Ollama`, `Kokoro`) bind strictly to localhost loopback interfaces (`127.0.0.1` / `::1`).
- **Telemetry Free**: The codebase contains zero external analytics tracking, third-party pixel beacons, or background phone-home mechanisms.

---

## 2. Voice Audio & Transcript Ephemeral Lifecycles

| Data Type | Retention Window | Storage Substrate | Encryption & Protection |
| :--- | :--- | :--- | :--- |
| **Real-Time Audio Frames** | Ephemeral (< 100ms) | In-memory RAM buffer / ring buffer | Discarded immediately after transcription and TTS playout. |
| **STT Turn Transcripts** | Session Duration | Python process memory | Cleared upon WebRTC room termination. |
| **LLM Context History** | Session Duration | In-memory `ConversationContext` | Rolled over / truncated at conversation boundaries. |
| **Domain State (Bookings & Leads)** | Durable Local Disk | Local SQLite DB (`data/proprelay.db`) | Standard OS filesystem permissions. |
| **Audit Event Journal** | Append-Only Disk | Local JSON-Lines file (`data/events.jsonl`) | Cryptographic SHA-256 event chaining. |

---

## 3. Regulatory Alignment (GDPR & CCPA/CPRA)

While PropRelay in Phase 7 operates in a local development and evaluation environment, its architectural primitives are designed to satisfy enterprise regulatory constraints when deployed into production:

### 3.1 Right to Erasure (GDPR Article 17 / CCPA)
- All user-specific records (leads, showing reservations) are stored with unique, indexed identifiers (`renter_name`, `booking_id`).
- Local purge commands allow immediate deterministic deletion of user records:
  ```powershell
  # Purge all local transient session records safely
  .\scripts\clean_local_state.ps1 -Force
  ```

### 3.2 Voice Biometrics & Wiretapping Protection
- **No Acoustic Biometric Profiling**: PropRelay does not compute, store, or extract biometric voiceprints, pitch identification, or speaker verification embeddings.
- **Explicit Two-Phase Consent**: Voice-initiated state mutations (scheduling, cancelling, lead creation) require explicit, unambiguous verbal confirmation before committing.
- **Recording Policy**: Real-time WebRTC audio recording is disabled by default. If room egress recording is activated, the agent is configured to announce: *"This call may be recorded for quality assurance."*

---

## 4. Lead Capture & PII Governance

When prospective renters share contact information during conversational property inquiries:
1. **Minimal Collection Policy**: The agent only solicits information strictly necessary to stage a property showing (Renter Name, Optional Phone, Optional Email).
2. **Deterministic Validation**: Pydantic input models enforce strict typing and boundary validation on names, phone numbers, and emails.
3. **No Unprompted Sharing**: Captured leads are stored solely in the local `ILeadRepository` and are never broadcast over public WebRTC data channels or shared with unauthorized participants.
