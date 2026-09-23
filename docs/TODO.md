# PropRelay — Project Implementation Roadmap (TODO)

## Completed in Phase 2 (Deterministic Domain & Policy Engine)
- [x] Initialized Git repository and created strict `.gitignore`
- [x] Setup Python environment with `uv` (`pyproject.toml`, pinned dependencies, `uv.lock`)
- [x] Implemented standalone LiveKit Server local download and startup scripts (`scripts/download_livekit.ps1`, `scripts/start_livekit.ps1`)
- [x] Implemented strongly-typed Domain Entities with Pydantic (`Property`, `ShowingSlot`, `Booking`, `Lead`, `DomainEvent`)
- [x] Implemented In-Memory Thread-Safe Domain Repositories with per-slot `asyncio.Lock` concurrency protection (`PropertyRepository`, `ShowingRepository`, `BookingRepository`, `LeadRepository`)
- [x] Implemented Business Policy Service (`BookingPolicyService`) enforcing 10 deterministic business rules, collision prevention, and structured error codes
- [x] Implemented stable booking idempotency key derivation and duplicate handling
- [x] Implemented Clock abstraction (`Clock`, `SystemClock`, `FrozenClock`) for deterministic time-dependent tests
- [x] Implemented Event Journal Service (`EventJournal`) with append-only JSONL persistence and publisher protocol
- [x] Implemented Typed Agent Function Tools with `ToolResult[T]` error envelopes
- [x] Implemented server-side LiveKit JWT token generation and verification module (`LiveKitTokenService`)
- [x] Created fictional property and showing fixtures (`data/listings.json`, `data/showings.json`)
- [x] Implemented environment verification audit script (`scripts/verify_environment.ps1`)
- [x] Wrote automated unit, policy, repository, event, concurrency, and tool tests (57 tests, 97% coverage)

---

## Completed in Phase 3 (Realtime Voice Runtime)
- [x] Implemented `FasterWhisperSTT` (custom `livekit.agents.stt.STT` wrapping in-process CTranslate2 on NVIDIA CUDA float16 with auto-resampling and pre-warming)
- [x] Implemented local Kokoro ONNX TTS microservice on port 8880 (`proprelay/tts/server.py`) serving OpenAI-compatible `/v1/audio/speech` at 24kHz with `af_alloy` voice
- [x] Configured Local LLM with Ollama `qwen2.5:7b` via `livekit-plugins-openai` (`openai.LLM.with_ollama`)
- [x] Configured Silero VAD (`livekit-plugins-silero`) and local edge `TurnDetector(version="v1-mini")` (100% offline ONNX execution)
- [x] Configured local VAD-based interruption & barge-in (`mode="vad"`, `min_duration=0.3s`) bypassing cloud adaptive barge-in without LiveKit Cloud keys
- [x] Implemented `@llm.function_tool` bindings (`proprelay/agent/voice_tools.py`) delegating to Phase 2 `AgentTools` and serializing outputs to JSON dictionaries
- [x] Implemented `LiveKitEventBroadcaster` streaming typed `DomainEvent` JSON schemas over LiveKit WebRTC data channel (topic `proprelay.events`)
- [x] Implemented `VoiceSession` orchestrating `AgentSession`, state machine management (`VoiceState`), and real-time metric tracking (`LatencyTracker`)
- [x] Implemented `AgentServer` worker entrypoint (`proprelay/agent/worker.py`) connecting to local LiveKit server and auto-dispatching voice sessions
- [x] Implemented unified FastAPI token dispenser, health monitor, and static React frontend server (`proprelay/api/server.py`)
- [x] Built React 19 + TypeScript + Vite + `livekit-client` web application (`frontend/`) with live state pill, transcript log, live events feed, and latency breakdown
- [x] Created management scripts: `download_kokoro.ps1`, `start_kokoro.ps1`, `start_agent.ps1`, `start_api.ps1`, `start_frontend.ps1`, and `run_local.ps1`
- [x] Verified live end-to-end conversational turn with measured benchmarks: `t_turn_eou_ms` (932ms), `t_stt_ms` (344ms), `t_llm_ttft_ms` (75ms), `t_llm_total_ms` (662ms), `t_tts_ttfb_ms` (727ms)
- [x] Authored comprehensive documentation: `docs/VOICE_PIPELINE.md`, `docs/LATENCY.md`, `docs/DEMO_SCRIPT.md`, and Technical Decision Records TDR-017 through TDR-024

---

## Completed in Phase 4 (Agentic Property Workflows, Conversational Context & Action Safety)
- [x] Extended domain models (`Booking.updated_at`, `Booking.cancellation_reason`, `Lead.lifecycle_state`)
- [x] Implemented atomic showing reschedule and cancellation in `BookingPolicyService` (`validate_and_reschedule`, `validate_and_cancel`)
- [x] Enforced deadlock-free sorted slot locking across multi-slot reschedule mutations (`sorted([old_slot_id, new_slot_id])`)
- [x] Standardized 8 new domain event schemas (`showing.reschedule.*`, `showing.cancellation.*`, `booking.confirmation.*`, `workflow.state.changed`)
- [x] Built deterministic date/time normalization anchored strictly to injected `Clock` reference date (`proprelay/agent/date_normalization.py`)
- [x] Implemented conversational finite state machine (`WorkflowState`) and `ActionType` (`proprelay/workflows/state.py`)
- [x] Implemented structured session context and reference resolution (`ConversationContext` in `proprelay/workflows/context.py`)
- [x] Implemented deterministic reference resolvers: ordinals ("first", "second"), superlatives ("cheapest"), and temporal slot matching ("2 PM")
- [x] Implemented two-phase Application-Level Action Confirmation Safety Gate (`PendingAction` staging and verification in `AgentTools`)
- [x] Implemented Stale Action Invalidation: Topic/property/date switches automatically invalidate staged proposals
- [x] Built multi-turn workflow metrics tracker (`WorkflowMetricsTracker` in `proprelay/observability/metrics.py`)
- [x] Exposed 9 typed tools in `voice_tools.py` with behavioral prompts for local LLM
- [x] Updated frontend dashboard with Workflow State pill, Action Confirmation Safety Gate banner, and Active Property focus card
- [x] Created comprehensive test suites: 10 multi-turn workflow scenarios, grounding tests, reschedule/cancel concurrency tests (137 passing tests, 88% overall coverage)
- [x] Authored comprehensive architectural documentation: `docs/AGENTIC_WORKFLOWS.md` and TDR-025 through TDR-028

---

## Completed in Phase 5 (Event-Driven Realtime Operations, Evaluation, Observability & Reliability)
- [x] Upgraded `DomainEvent` schema v1 with monotonic 64-bit integer sequences (`sequence_number`) and SHA-256 tamper-evident hash chaining (`previous_event_hash`)
- [x] Built cryptographic tamper detection engine (`EventJournal.verify_integrity()`) catching unauthorized line edits, record swaps, or deletions
- [x] Implemented in-memory automated PII masking for phone numbers and email usernames before disk write or WebRTC broadcast
- [x] Built sequenced `EventReplayEngine` with session reconstruction and filtered query support (`read_filtered()`)
- [x] Implemented `MetricsStore` tracking turn latencies, workflow run summaries, and system health snapshots
- [x] Enforced statistical integrity guard ($N \ge 3$) returning `"insufficient samples (N=...)"` to prevent fabricated percentiles
- [x] Implemented typed `ErrorTaxonomy` and `StructuredError` envelope across 7 error categories with explicit recovery actions
- [x] Extended FastAPI endpoints: `/api/metrics/summary`, `/api/sessions/{id}`, `/api/workflows/{id}`, `/api/events`, `/api/events/{id}`, `/api/evaluations/latest`
- [x] Built 15 canonical behavioral scenario YAML definitions (`tests/scenarios/S01` to `S15`)
- [x] Implemented 8 deterministic judges: `ConsequentialSafetyJudge`, `GroundingJudge`, `ConfirmationSafetyJudge`, `StaleActionJudge`, `StateTransitionJudge`, `ToolCallCorrectnessJudge`, `DeterministicDateJudge`, `LatencySLAJudge`
- [x] Implemented local `OllamaSemanticJudge` scoring persona tone and brevity with zero cloud leak
- [x] Built evaluation runner CLI (`python -m proprelay.evaluation.runner --all`) outputting `reports/evaluation/latest.json` and `latest.md` (100% pass rate)
- [x] Built pre-flight diagnostics CLI (`python -m proprelay.diagnostics`) probing environment dependencies with Rich console tables
- [x] Added Operations Console tabs to React frontend: Turn Latency Waterfall visualizer, Workflow Run Inspector, Structured Error Taxonomy panel, and Event Journal replay
- [x] Added client-side WebRTC event deduplication gate (`seenEventIdsRef`)
- [x] Built 5 targeted test suites (168 passing tests, 100% green)
- [x] Sanitized documentation across repo to purge misleading claims (such as fabricated latency guarantees or ungrounded claims)
- [x] Authored `docs/OBSERVABILITY.md`, `docs/EVALUATION.md`, `docs/EVENT_SCHEMA.md`, and TDR-029 through TDR-037

---

## Completed in Phase 6 (Performance Engineering, Voice Latency Optimization & Local Concurrency)
- [x] Implemented reproducible performance benchmark suite CLI (`python -m proprelay.performance.benchmark --all`)
- [x] Created controlled 30-utterance synthetic benchmark dataset (`data/benchmark_utterances.json`) and audio fixtures
- [x] Enforced statistical sample-size guards ($N \ge 3$) preventing fabricated percentiles
- [x] Profiled faster-whisper STT audio preprocessing, buffer conversion, and CTranslate2 CUDA `float16` inference
- [x] Profiled Ollama `qwen2.5:7b` TTFT, tokens/sec, tool-calling overhead, and prompt length tradeoffs
- [x] Profiled Kokoro-ONNX TTS first-chunk streaming delivery vs full multi-sentence audio rendering
- [x] Benchmarked and tuned endpointing delays (`min_endpointing_delay=0.3`, `max_endpointing_delay=2.0`), reducing EOU delay by 447ms
- [x] Evaluated and enabled speculative preemptive generation, dropping effective TTFT to 16.98ms (p50)
- [x] Evaluated and rejected preemptive TTS to prevent audio waste and GPU memory thrashing during user corrections
- [x] Implemented `SafeReadOnlyCache` with 300s TTL for immutable property metadata while enforcing zero caching of volatile showing slots
- [x] Verified transactional mutual exclusion under concurrent conflicting booking attempts (0.15ms lock evaluation)
- [x] Profiled local concurrency scaling across 1, 2, and 4 concurrent sessions with zero failures
- [x] Authored performance regression smoke tests (`tests/test_performance_smoke.py`)
- [x] Generated comprehensive empirical reports: `baseline.json`, `baseline.md`, `phase6_comparison.md`, `cold_start.md`, and `concurrency.md`
- [x] Authored `docs/PERFORMANCE.md` and Technical Decision Records TDR-038 through TDR-046
- [x] Updated pre-flight diagnostics CLI (`python -m proprelay.diagnostics`) for CTranslate2 GPU detection and Windows IP normalization

---

## Completed in Phase 7 (Production-Style Hardening, Security, Advanced Agent Evaluation & Release Readiness)
- [x] Audited and corrected technical claims across all documentation (verified 28.2% total turn reduction; disclosed STT dataset limits)
- [x] Built automated claims scanner (`scripts/scan_claims.py`) and secrets scanner (`scripts/scan_secrets.py`)
- [x] Hardened FastAPI server with security headers middleware, 64KB request body limits, bounded regex inputs, and deep readiness probe
- [x] Hardened LiveKit JWT token verification with strict zero-leeway token expiration checks
- [x] Implemented comprehensive security test suites: WebRTC token security, prompt injection defense, and event journal integrity
- [x] Implemented architecture invariant enforcement test suite (`tests/unit/test_architecture_invariants.py`)
- [x] Expanded behavioral evaluation suite to 25 scenarios (S16–S25) with severity gating and automated release gate generation
- [x] Built deterministic scenario replay CLI (`proprelay/evaluation/replay.py`)
- [x] Built runtime provenance manifest generator (`proprelay/build_manifest.py`)
- [x] Enhanced system diagnostics CLI with version 0.7.0, active profile display, and remediation guidance
- [x] Authored operational PowerShell scripts (`release_gate.ps1`, `ci.ps1`, `reproduce_evaluation.ps1`, `reproduce_performance.ps1`, `clean_local_state.ps1`, `export_state.ps1`, `import_state.ps1`, `run_demo.ps1`, `package_local.ps1`)
- [x] Authored authoritative documentation suite (`PRODUCTION_EVOLUTION.md`, `RELEASE_CHECKLIST.md`, `MODEL_LICENSES.md`, `PRIVACY.md`, `RUNBOOK.md`, `RECRUITER_WALKTHROUGH.md`, `ARCHITECTURE_REVIEW.md`, `CHANGELOG.md`)

---

## Completed in Phase 8 (Final Portfolio, GitHub, Demo & Recruiter Demonstration Package)
- [x] Added root MIT `LICENSE` file matching project metadata
- [x] Authored native Mermaid architecture diagram set in `docs/diagrams/` (`system_architecture.md`, `voice_turn_sequence.md`, `booking_safety_sequence.md`, `event_flow.md`, `README.md`)
- [x] Authored comprehensive 2,000-word engineering case study (`docs/PORTFOLIO_CASE_STUDY.md`)
- [x] Structured 3–5 minute recruiter demonstration script with minute-by-minute milestones and safety tests (`docs/DEMO_SCRIPT.md`)
- [x] Authored one-page technical interview cheat sheet answering 24 key questions (`docs/INTERVIEW_CHEATSHEET.md`)
- [x] Authored engineering role alignment matrix and capability crosswalk (`docs/ROLE_ALIGNMENT.md`)
- [x] Authored first-person technical evolution narrative across all 6 developmental stages (`docs/TECHNICAL_STORY.md`)
- [x] Authored non-subjective project scorecard with factual status matrix (`docs/PROJECT_SCORECARD.md`)
- [x] Authored copy-paste portfolio website copy and project descriptions (`docs/PORTFOLIO_COPY.md`)
- [x] Authored demonstration fixtures guide with occupied slots and scenario mappings (`docs/DEMO_FIXTURES.md`)
- [x] Redesigned root `README.md` into high-signal portfolio landing page with direct Q&A and transparent performance tables
- [x] Enhanced demonstration launcher `scripts/run_demo.ps1` with pre-flight verification, endpoints, and `reset` mode
- [x] Refined `scripts/clean_local_state.ps1` to reset databases and transient event journals while preserving catalog fixtures
- [x] Performed GitHub hygiene audit and refined `.gitignore` for runtime state databases and test failures
- [x] Bumped semantic version to `0.8.0` in `proprelay/__init__.py` and `pyproject.toml`
- [x] Executed full authoritative release gate (`release_gate.ps1`) confirming 10/10 passing verification steps

---

## Future Production Evolution Roadmap (Stage 2 & Stage 3 Cloud Migration)
- [ ] Implement SQLModel / SQLAlchemy repository adapters backed by managed PostgreSQL (Aurora Multi-AZ)
- [ ] Implement Redis-backed distributed locks and session state store for multi-worker horizontal scaling
- [ ] Containerize inference services with Triton Inference Server (Faster-Whisper) and vLLM (Qwen 2.5) on Kubernetes
- [ ] Deploy LiveKit Server in distributed cluster mode behind Network Load Balancers
- [ ] Bridge LiveKit SIP Gateway to Telnyx or Twilio SIP trunks for direct PSTN inbound telephone calls
- [ ] Deploy LiveKit Edge media relays for multi-region low-latency (<30ms RTT) audio ingress
- [ ] Integrate lightweight on-device acoustic speaker diarization for conference/speakerphone leasing calls


