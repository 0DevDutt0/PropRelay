# PropRelay — Project Progress

## Current Phase:
Phase 8 — Final Portfolio, GitHub, Demo & Recruiter Demonstration Package

## Status:
Complete (193/193 Unit & Invariant Tests Green, 25/25 Behavioral Scenarios Passing, Release Gate: READY, 100% Local $0 Architecture Verified, Full Portfolio Package Shipped)

---

## Completed in Phase 8:
1. **Root License File (`LICENSE`)**:
   - Added official permissive MIT license matching `pyproject.toml`.
2. **Native GitHub Mermaid Architecture Diagram Set (`docs/diagrams/`)**:
   - `system_architecture.md`: Complete component topology and data paths.
   - `voice_turn_sequence.md`: Turn sequence with measured stage latencies and barge-in cut-through.
   - `booking_safety_sequence.md`: Two-phase confirmation protocol with ungrounded/occupied rejection branches.
   - `event_flow.md`: Durable-before-broadcast pattern with SHA-256 hash chaining.
   - `README.md`: Centralized diagram index and navigation catalog.
3. **Comprehensive Portfolio Case Study (`docs/PORTFOLIO_CASE_STUDY.md`)**:
   - Authored in-depth 2,000-word engineering case study covering problem domain, acoustic voice AI challenges, untrusted LLM boundaries, empirical latency profiling, evaluation methodology, and cloud evolution.
4. **Recruiter Demonstration Script (`docs/DEMO_SCRIPT.md`)**:
   - Structured 3–5 minute live demo script with exact timestamps (0:00 to 5:00), spoken prompts, expected UI reactions, and safety tests.
5. **Technical Interview Cheat Sheet (`docs/INTERVIEW_CHEATSHEET.md`)**:
   - One-page high-signal reference sheet answering 24 key architectural, concurrency, latency, and reliability interview questions.
6. **Role Alignment Matrix (`docs/ROLE_ALIGNMENT.md`)**:
   - Technical crosswalk mapping PropRelay implementation details to core competencies expected in Agentic Voice AI engineering roles.
7. **Technical Evolution Narrative (`docs/TECHNICAL_STORY.md`)**:
   - First-person engineering narrative recounting the motivations, failure modes, and architectural decisions across all 6 developmental stages.
8. **Non-Subjective Project Scorecard (`docs/PROJECT_SCORECARD.md`)**:
   - Factual status audit across all major capabilities using non-subjective categories (Implemented, Tested, Benchmarked, Documented, Reproducible, Known limitation, Future production concern).
9. **Portfolio Website Copy (`docs/PORTFOLIO_COPY.md`)**:
   - Factual, copy-paste-ready engineering descriptions for personal portfolio sites, project cards, and GitHub descriptions.
10. **Demonstration Fixtures Guide (`docs/DEMO_FIXTURES.md`)**:
    - Catalog fixtures, occupied showing slots, safety test records, and scenario mapping for live demonstrations.
11. **Project Landing Page Redesign (`README.md`)**:
    - Redesigned root README into high-signal portfolio landing page with direct Q&A, clean Mermaid topology, 10-step voice pipeline, and transparent empirical benchmark tables.
12. **Operational Script & Reset Enhancements**:
    - Enhanced `scripts/run_demo.ps1` with environment diagnostics pre-flight, port validation, prompt guide, and `reset` mode.
    - Refined `scripts/clean_local_state.ps1` to cleanly reset runtime databases, transient journals (`data/events.jsonl`), and logs while strictly preserving domain fixtures and compiled frontend assets.
13. **Hygiene & Gitignore Audit**:
    - Updated `.gitignore` to prevent committing runtime SQLite databases, local session journals, and test failures while tracking release evaluation reports.
    - Bumped semantic version to `0.8.0` in `proprelay/__init__.py` and `pyproject.toml`.

---

## Completed in Phase 7:
1. **Claims & Methodology Audit**:
   - Corrected total turn latency reduction from 41% to 28.2% across all documentation and reports.
   - Disclosed STT dataset comparability limits (Phase 3 single 3.8s clip vs Phase 6 25-utterance corpus).
   - Documented concurrency harness methodology (asyncio event loop scheduling against shared repositories; global VRAM via nvidia-smi).
2. **Automated Claim & Secrets Scanners**:
   - Built `scripts/scan_claims.py` enforcing truthfulness and provenance.
   - Built `scripts/scan_secrets.py` detecting API keys, private keys, and tokens.
   - Cleaned bandit false positives with `# nosec B104` (0 medium, 0 high vulnerabilities).
3. **Configuration & Versioning**:
   - Bumped semantic version to `0.7.0` in `proprelay/__init__.py` and `pyproject.toml`.
   - Implemented typed `AppConfig` and `AppProfile` with fail-fast validation in `proprelay/config.py`.
4. **FastAPI & Network Hardening**:
   - Added security headers middleware (`X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy`, CSP).
   - Enforced 64KB request body limit (returns HTTP 413).
   - Bounded participant identity and room name regex validations.
   - Added liveness probe (`/api/health`) and deep readiness probe (`/api/readiness`).
5. **Security & Invariant Test Suites**:
   - Added `tests/unit/test_token_security.py` (strict zero-leeway token expiration, room isolation, minimal permissions).
   - Added `tests/unit/test_prompt_injection.py` (adversarial injection defense, fake property grounding, cancellation protection).
   - Added `tests/unit/test_journal_integrity.py` (cryptographic SHA-256 hash checks, sequence gap detection).
   - Added `tests/unit/test_architecture_invariants.py` (enforcing the 6 core architectural guarantees).
6. **Advanced Evaluation & Release Gate Infrastructure**:
   - Enhanced evaluation models and judges with strict severities (`CRITICAL`, `MAJOR`, `MINOR`, `INFO`).
   - Added `ClarificationJudge` for underspecified voice inputs.
   - Added 10 new behavioral scenarios S16–S25 (25 total scenarios evaluated, 100% pass rate, Gate: READY).
   - Created `reports/evaluation/release_gate.json` and `release_gate.md`.
7. **Deterministic Replay CLI & Build Provenance**:
   - Implemented `proprelay/evaluation/replay.py` (`python -m proprelay.evaluation.replay --scenario S04 -v`).
   - Implemented `proprelay/build_manifest.py` generating runtime provenance manifest.
   - Enhanced `proprelay/diagnostics.py` with version, profile display, and remediation guidance.
8. **Operational Script Suite**:
   - Authored `scripts/release_gate.ps1`, `scripts/ci.ps1`, `scripts/reproduce_evaluation.ps1`, `scripts/reproduce_performance.ps1`, `scripts/clean_local_state.ps1`, `scripts/export_state.ps1`, `scripts/import_state.ps1`, `scripts/run_demo.ps1`, and `scripts/package_local.ps1`.
9. **Authoritative Documentation Suite**:
   - Authored `docs/PRODUCTION_EVOLUTION.md`, `docs/RELEASE_CHECKLIST.md`, `docs/MODEL_LICENSES.md`, `docs/PRIVACY.md`, `docs/RUNBOOK.md`, `docs/RECRUITER_WALKTHROUGH.md`, `docs/ARCHITECTURE_REVIEW.md`, and `CHANGELOG.md`.

---

## Completed in Phase 6:

1. **Performance Benchmark Suite & Statistical Integrity (TDR-038)**:
   - Built standalone benchmark harness (`python -m proprelay.performance.benchmark --all`).
   - Created controlled 30-utterance synthetic benchmark dataset (`data/benchmark_utterances.json`) and audio fixtures.
   - Enforced statistical integrity guard ($N \ge 3$) returning `"insufficient samples (N=...)"` to prevent small-sample percentile fabrication.
   - Automatically outputs `reports/performance/baseline.json`, `baseline.md`, `phase6_comparison.md`, `cold_start.md`, and `concurrency.md`.

2. **Endpointing Delay Optimization (TDR-039)**:
   - Benchmarked fixed 0.5s vs fixed 0.3s vs dynamic 0.2s endpointing.
   - Selected Fixed 0.3s (`min_endpointing_delay=0.3`, `max_endpointing_delay=2.0`), reducing end-of-utterance commitment delay from 932.4ms to 485.2ms (-447.2ms) with only 2.1% false cutoff rate.

3. **Speculative Preemptive Generation (TDR-040)**:
   - Evaluated preemptive generation against unconfirmed turn boundaries.
   - Dropped effective LLM TTFT from 75.5ms to 16.98ms (p50) with only 4.5% speculative compute discarded on interruption.

4. **Preemptive TTS Evaluation & Rejection (TDR-041)**:
   - Benchmarked preemptive TTS against user corrections and interruptions.
   - Rejected preemptive TTS due to 18.2% wasted audio compute and memory thrashing; kept `enable_preemptive_tts=False` to preserve high-stakes leasing confirmation accuracy.

5. **Local STT Profiling & Audio Buffer Reuse (TDR-042)**:
   - Profiled `faster-whisper` base.en CUDA `float16` and audio preprocessing.
   - Resampling 48kHz stereo to 16kHz mono takes 0.02ms; float32 normalization takes 0.01ms.
   - Pre-warmed CTranslate2 engine eliminates CUDA kernel compilation jitter on live turns.

6. **Kokoro TTS First-Chunk Streaming (TDR-043)**:
   - Profiled multi-sentence speech generation vs first-sentence chunk streaming.
   - First-sentence chunk delivers audio to WebRTC in 407.95ms (p50), providing **1,085.87ms earlier first-audio delivery** over full multi-sentence rendering (1,492ms).

7. **Safe Read-Only Catalog Caching (TDR-044)**:
   - Implemented `SafeReadOnlyCache` with 300s TTL for static listing lookups and query searches, cutting repository lookup to < 0.01ms.
   - Strictly prohibited caching of showing slot availability and booking mutations to guarantee transactional freshness.

8. **Single-Machine Local Concurrency Scaling & Race Safety (TDR-045)**:
   - Verified transactional mutual exclusion under simultaneous conflicting booking attempts: exactly 1 succeeded, 1 rejected with `SLOT_UNAVAILABLE` (0.15ms lock evaluation).
   - Profiled 1, 2, and 4 concurrent sessions: 100% success rate with median turn latency stable at ~61ms.

9. **Broad Performance Regression Smoke Tests (TDR-046)**:
   - Created `tests/test_performance_smoke.py` asserting broad SLAs (lookup < 25ms, search < 30ms, journal append < 50ms, race safety = True).
   - Preserves 100% passing test suite across machine load variations.

10. **Pre-Flight Diagnostics & Hardware Telemetry**:
    - Improved `proprelay/diagnostics.py` to auto-detect NVIDIA GPUs via CTranslate2 / nvidia-smi when torch is absent.
    - Normalized `0.0.0.0` to `127.0.0.1` for Windows network compatibility.
    - Authored comprehensive `docs/PERFORMANCE.md` and appended TDR-038 through TDR-046.

---

## Overall Test & Evaluation Status:
- **Pytest**: 176 passing tests (100% green).
- **Behavioral Scenarios**: 15/15 passing (100.0% pass rate).
- **Performance Benchmarks**: Completed across 25 samples per stage.
- **Ruff & Mypy**: 0 errors, 100% clean typing and linting.
- **Diagnostics**: 100% green environment pre-flight verification.
