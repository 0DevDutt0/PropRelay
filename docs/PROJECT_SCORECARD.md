# PropRelay — Project Engineering Scorecard

This scorecard provides a factual, non-subjective status audit across all major capabilities of PropRelay v0.8.0. In accordance with strict engineering standards, this scorecard contains **no subjective percentage ratings or quality scores**. Every capability is mapped to its factual status and corresponding repository evidence.

---

## 1. Status Category Definitions

- **Implemented**: Fully written, integrated, and runnable in the codebase.
- **Tested**: Verified via automated unit, invariant, integration, or scenario tests.
- **Benchmarked**: Profiled with empirical hardware measurements and documented distributions.
- **Documented**: Accompanied by dedicated architectural documentation, sequence diagrams, or runbooks.
- **Reproducible**: Executable by a fresh user via local automation scripts or CLI harnesses.
- **Known Limitation**: Deliberate boundary or constraint of the current single-machine local implementation.
- **Future Production Concern**: Architectural requirement for cloud migration at higher scale.

---

## 2. Core Capabilities Status Matrix

| Subsystem / Capability | Engineering Status | Code & Test Evidence | Empirical & Architectural Notes |
| :--- | :--- | :--- | :--- |
| **Real-Time Voice Transport** | Implemented, Tested, Documented, Reproducible | [`proprelay/agent/worker.py`](file:///E:/work/Agentic%20Engineer%28Voice%20AI%29/PropRelay/proprelay/agent/worker.py)<br>[`tests/unit/test_worker.py`](file:///E:/work/Agentic%20Engineer%28Voice%20AI%29/PropRelay/tests/unit/test_worker.py) | Standalone local LiveKit Server binary on port 7880; Opus audio streaming over WebRTC. |
| **Local Speech Recognition** | Implemented, Tested, Benchmarked, Documented | [`proprelay/stt/faster_whisper.py`](file:///E:/work/Agentic%20Engineer%28Voice%20AI%29/PropRelay/proprelay/stt/faster_whisper.py)<br>[`tests/unit/test_stt.py`](file:///E:/work/Agentic%20Engineer%28Voice%20AI%29/PropRelay/tests/unit/test_stt.py) | Faster-Whisper `base.en` via CTranslate2 CUDA `float16`; pre-warmed weights; 16kHz resampling. |
| **Local Speech Synthesis** | Implemented, Tested, Benchmarked, Documented | [`proprelay/tts/server.py`](file:///E:/work/Agentic%20Engineer%28Voice%20AI%29/PropRelay/proprelay/tts/server.py)<br>[`tests/unit/test_tts_server.py`](file:///E:/work/Agentic%20Engineer%28Voice%20AI%29/PropRelay/tests/unit/test_tts_server.py) | Kokoro-82M ONNX Runtime on port 8880; 24kHz PCM chunking; first-chunk streaming (407.95ms p50). |
| **Voice Activity & Interruption** | Implemented, Tested, Benchmarked, Documented | [`proprelay/agent/session.py`](file:///E:/work/Agentic%20Engineer%28Voice%20AI%29/PropRelay/proprelay/agent/session.py)<br>[`tests/scenarios/S15_interruption.yaml`](file:///E:/work/Agentic%20Engineer%28Voice%20AI%29/PropRelay/tests/scenarios/S15_interruption.yaml) | Silero VAD v5 ONNX; tuned endpointing window (`min_delay=0.3s`); sub-100ms barge-in audio cut-through. |
| **Untrusted LLM Boundary** | Implemented, Tested, Documented, Reproducible | [`proprelay/agent/tools.py`](file:///E:/work/Agentic%20Engineer%28Voice%20AI%29/PropRelay/proprelay/agent/tools.py)<br>[`tests/unit/test_architecture_invariants.py`](file:///E:/work/Agentic%20Engineer%28Voice%20AI%29/PropRelay/tests/unit/test_architecture_invariants.py) | Invariant 2: LLM functions strictly as intent router; zero direct database write handles. |
| **Authoritative Entity Grounding** | Implemented, Tested, Documented, Reproducible | [`proprelay/domain/policy.py`](file:///E:/work/Agentic%20Engineer%28Voice%20AI%29/PropRelay/proprelay/domain/policy.py)<br>[`tests/unit/test_grounding.py`](file:///E:/work/Agentic%20Engineer%28Voice%20AI%29/PropRelay/tests/unit/test_grounding.py) | Invariant 3: Un-grounded or hallucinated property/slot IDs reject deterministically (`PROPERTY_NOT_FOUND`). |
| **Two-Phase Confirmation Gate** | Implemented, Tested, Documented, Reproducible | [`proprelay/workflows/state.py`](file:///E:/work/Agentic%20Engineer%28Voice%20AI%29/PropRelay/proprelay/workflows/state.py)<br>[`tests/scenarios/S04_booking_happy_path.yaml`](file:///E:/work/Agentic%20Engineer%28Voice%20AI%29/PropRelay/tests/scenarios/S04_booking_happy_path.yaml) | Invariant 1: Consequential actions require `PendingAction` staging and explicit verbal confirmation. |
| **Stale Action Invalidation** | Implemented, Tested, Documented, Reproducible | [`proprelay/workflows/context.py`](file:///E:/work/Agentic%20Engineer%28Voice%20AI%29/PropRelay/proprelay/workflows/context.py)<br>[`tests/scenarios/S07_stale_action.yaml`](file:///E:/work/Agentic%20Engineer%28Voice%20AI%29/PropRelay/tests/scenarios/S07_stale_action.yaml) | Conversational topic shifts or property switches automatically clear unconfirmed staged proposals. |
| **Concurrency & Lock Safety** | Implemented, Tested, Benchmarked, Documented | [`proprelay/domain/policy.py`](file:///E:/work/Agentic%20Engineer%28Voice%20AI%29/PropRelay/proprelay/domain/policy.py)<br>[`tests/unit/test_concurrency.py`](file:///E:/work/Agentic%20Engineer%28Voice%20AI%29/PropRelay/tests/unit/test_concurrency.py) | Per-slot `asyncio.Lock`; sorted slot locking (`sorted([slot_a, slot_b])`) prevents deadlocks during rescheduling. |
| **Cryptographic Event Sourcing**| Implemented, Tested, Documented, Reproducible | [`proprelay/events/journal.py`](file:///E:/work/Agentic%20Engineer%28Voice%20AI%29/PropRelay/proprelay/events/journal.py)<br>[`tests/unit/test_journal_integrity.py`](file:///E:/work/Agentic%20Engineer%28Voice%20AI%29/PropRelay/tests/unit/test_journal_integrity.py) | Invariant 4: Monotonic sequences with SHA-256 hash chaining; automated offline tamper detection. |
| **Durable-Before-Broadcast** | Implemented, Tested, Documented | [`proprelay/events/journal.py`](file:///E:/work/Agentic%20Engineer%28Voice%20AI%29/PropRelay/proprelay/events/journal.py)<br>[`tests/unit/test_architecture_invariants.py`](file:///E:/work/Agentic%20Engineer%28Voice%20AI%29/PropRelay/tests/unit/test_architecture_invariants.py) | Invariant 6: Disk journal flush occurs prior to WebRTC data channel broadcast; prevents state divergence. |
| **Automated PII Sanitization** | Implemented, Tested, Documented | [`proprelay/logging.py`](file:///E:/work/Agentic%20Engineer%28Voice%20AI%29/PropRelay/proprelay/logging.py)<br>[`tests/unit/test_logging.py`](file:///E:/work/Agentic%20Engineer%28Voice%20AI%29/PropRelay/tests/unit/test_logging.py) | In-memory regex masking of telephone numbers and email usernames before disk write or broadcast. |
| **WebRTC Token Security** | Implemented, Tested, Documented | [`proprelay/auth/tokens.py`](file:///E:/work/Agentic%20Engineer%28Voice%20AI%29/PropRelay/proprelay/auth/tokens.py)<br>[`tests/unit/test_token_security.py`](file:///E:/work/Agentic%20Engineer%28Voice%20AI%29/PropRelay/tests/unit/test_token_security.py) | Strict zero-leeway token expiration (`leeway_seconds=0`); room-scoped access permissions. |
| **FastAPI Gateway Hardening** | Implemented, Tested, Documented | [`proprelay/api/server.py`](file:///E:/work/Agentic%20Engineer%28Voice%20AI%29/PropRelay/proprelay/api/server.py)<br>[`tests/unit/test_api_server.py`](file:///E:/work/Agentic%20Engineer%28Voice%20AI%29/PropRelay/tests/unit/test_api_server.py) | Security headers (CSP, nosniff, DENY); 64KB request body limit (HTTP 413); bounded regex params. |
| **Behavioral Evaluation Suite**| Implemented, Tested, Documented, Reproducible | [`proprelay/evaluation/runner.py`](file:///E:/work/Agentic%20Engineer%28Voice%20AI%29/PropRelay/proprelay/evaluation/runner.py)<br>[`reports/evaluation/release_gate.md`](file:///E:/work/Agentic%20Engineer%28Voice%20AI%29/PropRelay/reports/evaluation/release_gate.md) | 25 canonical YAML scenarios evaluated by 8 deterministic judges with prioritized severity gating. |
| **Deterministic Scenario Replay**| Implemented, Tested, Documented, Reproducible | [`proprelay/evaluation/replay.py`](file:///E:/work/Agentic%20Engineer%28Voice%20AI%29/PropRelay/proprelay/evaluation/replay.py) | Turn-by-turn CLI inspection tool for deterministic debugging (`python -m proprelay.evaluation.replay`). |
| **Authoritative Release Gate** | Implemented, Tested, Documented, Reproducible | [`scripts/release_gate.ps1`](file:///E:/work/Agentic%20Engineer%28Voice%20AI%29/PropRelay/scripts/release_gate.ps1)<br>[`docs/RELEASE_CHECKLIST.md`](file:///E:/work/Agentic%20Engineer%28Voice%20AI%29/PropRelay/docs/RELEASE_CHECKLIST.md) | 10-step verification gate enforcing code quality, static typing, security, claims, and scenario passes. |

---

## 3. Known Limitations & Architectural Boundaries

| Area | Current Status | Technical Explanation |
| :--- | :--- | :--- |
| **Single-Machine Concurrency** | Known Limitation | Local GPU memory (24GB VRAM) comfortably supports 1 to 4 concurrent voice sessions; higher concurrency requires horizontal distributed inference. |
| **In-Memory Storage Model** | Known Limitation | Repositories maintain state in memory with local SQLite backing; state is node-local and not shared across horizontal worker clusters. |
| **Browser WebRTC Scope** | Known Limitation | Ingress is currently browser WebRTC only; PSTN / SIP telephony trunks are not bridged in the local prototype. |
| **Preemptive TTS** | Tested & Rejected | Evaluated speculatively, but rejected due to 18.2% wasted GPU compute on interrupted turns (TDR-041). Sentence streaming selected instead. |

---

## 4. Production Evolution Concerns (Stage 2 & Stage 3 Roadmap)

| Production Concern | Current Local Pattern | Target Cloud Architecture | Detailed Specification |
| :--- | :--- | :--- | :--- |
| **Distributed State & Locks** | Python `asyncio.Lock` | Managed PostgreSQL (`SELECT FOR UPDATE`) + Redis Cluster | [`docs/PRODUCTION_EVOLUTION.md`](file:///E:/work/Agentic%20Engineer%28Voice%20AI%29/PropRelay/docs/PRODUCTION_EVOLUTION.md) (Section 3) |
| **Inference Scalability** | In-process CTranslate2 + Ollama | Autoscaling GPU pool with Triton Whisper & vLLM | [`docs/PRODUCTION_EVOLUTION.md`](file:///E:/work/Agentic%20Engineer%28Voice%20AI%29/PropRelay/docs/PRODUCTION_EVOLUTION.md) (Section 3) |
| **Telephony Ingress** | WebRTC in browser | Multi-carrier SIP trunking (Telnyx / Twilio) via LiveKit SIP | [`docs/PRODUCTION_EVOLUTION.md`](file:///E:/work/Agentic%20Engineer%28Voice%20AI%29/PropRelay/docs/PRODUCTION_EVOLUTION.md) (Section 4) |
| **Distributed Event Streaming**| Local append-only JSONL | Apache Kafka / AWS Kinesis with schema registry | [`docs/PRODUCTION_EVOLUTION.md`](file:///E:/work/Agentic%20Engineer%28Voice%20AI%29/PropRelay/docs/PRODUCTION_EVOLUTION.md) (Section 5) |
