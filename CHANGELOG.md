# Changelog

All notable changes to the PropRelay project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.8.0] - 2026-09-23

### Phase 8 — Final Portfolio, GitHub, Demo & Recruiter Demonstration Package

#### Added
- **Root License File**: Added standard permissive MIT `LICENSE` matching `pyproject.toml` specification.
- **Native Architecture Diagram Set (`docs/diagrams/`)**: Authored native GitHub-compatible Mermaid diagrams:
  - `system_architecture.md`: Complete component topology across browser WebRTC, LiveKit SFU, agent worker, local neural inference, and deterministic domain layer.
  - `voice_turn_sequence.md`: End-to-end turn timeline with measured stage latencies and barge-in cut-through path.
  - `booking_safety_sequence.md`: Two-phase confirmation protocol with explicit rejection branches for ungrounded IDs and occupied slots.
  - `event_flow.md`: Durable-before-broadcast pattern, SHA-256 monotonic hash chaining, and automated in-memory PII masking.
  - `README.md`: Centralized diagram index and visual reference catalog.
- **Authoritative Portfolio Case Study (`docs/PORTFOLIO_CASE_STUDY.md`)**: Comprehensive 2,000-word engineering case study detailing problem domain, acoustic voice differences, untrusted LLM boundary, empirical latency profiling, evaluation methodology, and cloud evolution.
- **Recruiter Demonstration Script (`docs/DEMO_SCRIPT.md`)**: Structured 3–5 minute live walkthrough script with minute-by-minute milestones (0:00 to 5:00), exact spoken prompts, UI reactions, terminal commands, and safety demonstrations.
- **Technical Interview Cheat Sheet (`docs/INTERVIEW_CHEATSHEET.md`)**: One-page high-signal reference sheet answering 24 key architectural, concurrency, latency, and reliability questions.
- **Engineering Role Alignment Crosswalk (`docs/ROLE_ALIGNMENT.md`)**: Technical crosswalk mapping PropRelay implementation details to core competencies expected in Agentic Voice AI engineering roles.
- **Technical Evolution Narrative (`docs/TECHNICAL_STORY.md`)**: First-person engineering narrative recounting the motivations, failure modes, and architectural decisions across all 6 developmental stages.
- **Non-Subjective Project Scorecard (`docs/PROJECT_SCORECARD.md`)**: Factual status audit across all major capabilities using non-subjective categories (Implemented, Tested, Benchmarked, Documented, Reproducible, Known limitation, Future production concern).
- **Portfolio Website Copy (`docs/PORTFOLIO_COPY.md`)**: Factual, copy-paste-ready engineering copy for personal portfolio sites, project cards, and GitHub descriptions.
- **Demonstration Fixtures Guide (`docs/DEMO_FIXTURES.md`)**: Catalog fixtures, occupied showing slots, safety test records, and scenario mapping for live demonstrations.

#### Changed
- **Version Bump**: Promoted semantic version to `0.8.0` in `proprelay/__init__.py` and `pyproject.toml`.
- **Project Landing Page Redesign (`README.md`)**: Redesigned root README into high-signal portfolio landing page with direct Q&A, clean Mermaid topology, 10-step voice pipeline, and transparent empirical benchmark tables.
- **Demonstration Launcher Enhancement (`scripts/run_demo.ps1`)**: Added pre-flight environment diagnostics, service validation, interactive prompt guides, and `reset` mode.
- **Demo State Reset Refinement (`scripts/clean_local_state.ps1`)**: Cleanly purges runtime databases, transient journals (`data/events.jsonl`), and logs while strictly preserving catalog fixtures and compiled frontend assets.
- **Repository Hygiene & Gitignore (`.gitignore`)**: Enhanced ignore rules to prevent committing runtime SQLite databases, local session journals, and test failures while tracking authoritative release reports.

---

## [0.7.0] - 2026-09-23

### Phase 7 — Production-Style Hardening, Security, Advanced Agent Evaluation & Release Readiness

#### Added
- **Authoritative Release Gate**: Implemented `scripts/release_gate.ps1` enforcing 10 verification steps (diagnostics, ruff, mypy, bandit, claims scanner, secrets scanner, unit invariants, 25 behavioral scenarios, build manifest, frontend build).
- **Automated Claims & Truthfulness Scanner**: Implemented `scripts/scan_claims.py` verifying technical claims and preventing ungrounded latency/concurrency assertions across docs and code.
- **Automated Secrets & Credentials Scanner**: Implemented `scripts/scan_secrets.py` detecting API tokens, private keys, and hardcoded secrets.
- **Strict Architectural Invariant Tests**: Added `tests/unit/test_architecture_invariants.py` verifying the 6 core architectural guarantees (two-phase confirmation, clean domain boundaries, entity grounding, append-only journal integrity, idempotency, WebRTC decoupling).
- **Prompt Injection & Adversarial Test Suite**: Added `tests/unit/test_prompt_injection.py` testing prompt injection defense, fake property rejections, unavailable slot defense, and cancellation hijacking protection.
- **WebRTC Token Security Test Suite**: Added `tests/unit/test_token_security.py` verifying zero-leeway token expiration, room isolation, wrong secret rejection, and minimal permission grants.
- **Journal Integrity Test Suite**: Added `tests/unit/test_journal_integrity.py` testing cryptographic SHA-256 hash mismatch detection, sequence gap detection, and duplicate event prevention.
- **Ten Advanced Behavioral Scenarios (S16–S25)**: Added scenarios covering prompt injection, fake properties, unavailable slots, impersonation defense, stale confirmations, property switching context invalidation, past-date booking rejections, ambiguous ordinal resolution, clarification quality, and speech corrections.
- **Deterministic Scenario Replay CLI**: Implemented `proprelay/evaluation/replay.py` (`python -m proprelay.evaluation.replay --scenario S04 -v`) with rich turn-by-turn tables, judge results, and event logs.
- **Build Provenance Manifest Generator**: Implemented `proprelay/build_manifest.py` capturing git commit, Python runtime, platform details, neural model versions, and dependency locks.
- **Operational Script Suite**: Added `scripts/ci.ps1`, `scripts/reproduce_evaluation.ps1`, `scripts/reproduce_performance.ps1`, `scripts/clean_local_state.ps1`, `scripts/export_state.ps1`, `scripts/import_state.ps1`, `scripts/run_demo.ps1`, `scripts/package_local.ps1`.
- **Comprehensive Documentation Suite**:
  - `docs/PRODUCTION_EVOLUTION.md`: Evolution from Stage 1 local prototype to Stage 2 Kubernetes and Stage 3 Multi-Region Edge.
  - `docs/RELEASE_CHECKLIST.md`: Formal criteria for release qualification and rollback.
  - `docs/MODEL_LICENSES.md`: Provenance, attribution, and Apache-2.0 / MIT compliance for all models.
  - `docs/PRIVACY.md`: Zero cloud data leakage guarantees and ephemeral voice lifecycle policies.
  - `docs/RUNBOOK.md`: Incident recovery, port conflict resolutions, and CUDA troubleshooting.
  - `docs/RECRUITER_WALKTHROUGH.md`: High-signal 5-minute technical evaluation guide for hiring managers.
  - `docs/ARCHITECTURE_REVIEW.md`: Component topology and bounded context catalog.

#### Changed
- **Technical Honesty Latency Correction**: Corrected total turn latency reduction across `README.md`, `docs/LATENCY.md`, `docs/PERFORMANCE.md`, and performance reports from the inaccurate "41%" claim to the verified arithmetic figure of **28.2%** (Phase 3 baseline: 2,003.9 ms -> Phase 6 p50: 1,439.3 ms).
- **STT Comparability Disclosure**: Added explicit methodological notes clarifying that Phase 3 used a single 3.8s synthetic audio clip whereas Phase 6 used a 25-utterance evaluation corpus.
- **Concurrency Harness Disclosure**: Documented that local concurrency harness tests application-level asyncio event loop scheduling against shared repositories, and that VRAM reflects host `nvidia-smi` global memory.
- **FastAPI Security Hardening**: Added security headers middleware (`X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy`, CSP), 64KB request body size limit (HTTP 413), bounded regex inputs for participant identities and room names, bounded query parameters, and deep readiness probe (`/api/readiness`).
- **Token Expiration Defense**: Hardened `LiveKitTokenService` with `leeway_seconds=0` to reject expired JWTs immediately.
- **Diagnostics CLI Enhancement**: Added version display (`0.7.0`), active environment profile display, machine-readable `--json` output, and structured remediation guidance.

---

## [0.6.0] - 2026-09-23

### Phase 6 — Observability, Latency Optimization, Concurrency & Benchmark Discipline
- Implemented `proprelay/observability/` with OpenTelemetry tracing spans and Prometheus metrics.
- Implemented structured JSON-Lines logger and correlation ID propagation.
- Optimized voice turn latency via pipeline overlap and tuned endpointing.
- Implemented local concurrency benchmark harness (`proprelay/performance/concurrency.py`).
- Authored initial `docs/LATENCY.md` and `docs/OBSERVABILITY.md`.

---

## [0.5.0] - 2026-09-23

### Phase 5 — Frontend Real-Time WebRTC Interface
- Built React + TypeScript + Vite frontend with Tailwind CSS and shadcn/ui primitives.
- Real-time WebRTC audio streaming, live transcript display, and interactive audio waveform meter.
- Live showing availability calendar and property shortlisted view.
- Real-time audit log viewer streaming domain events via WebRTC data channel.

---

## [0.4.0] - 2026-09-23

### Phase 4 — Conversational Workflows, Agent Policy & Invariants
- Implemented two-phase confirmation state machine for consequential actions.
- Built property reference resolution ("the first one", "the loft") in `ConversationContext`.
- Implemented slot availability checks and duplicate booking prevention.
- Added append-only event sourcing journal (`DurableEventJournal`).

---

## [0.3.0] - 2026-09-23

### Phase 3 — Local Neural Voice Pipeline & Baseline Benchmarks
- Integrated local Faster-Whisper ASR via CTranslate2.
- Integrated local Ollama Qwen 2.5 LLM.
- Integrated local Kokoro-82M ONNX TTS engine.
- Established baseline turn latency timeline measurements.

---

## [0.2.0] - 2026-09-23

### Phase 2 — Real-Time LiveKit WebRTC Core & Agent Worker
- Integrated local LiveKit Server binary.
- Built Python LiveKit Agent Worker responding to audio tracks.
- Implemented JWT token generation service and room management endpoints.

---

## [0.1.0] - 2026-09-23

### Phase 1 — Project Scaffold, Domain Catalog & Local Setup
- Initial project structure with `uv` package management and Python 3.12.
- Domain models for `Property`, `ShowingSlot`, `Booking`, and `Lead`.
- In-memory repositories seeded with realistic Seattle and Austin listings.
