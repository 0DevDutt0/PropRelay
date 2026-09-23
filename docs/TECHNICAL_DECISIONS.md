# PropRelay — Technical Decision Records (TDR)

## TDR-001: LiveKit Server Deployment Model
- **Decision:** Self-hosted standalone native binary (`livekit-server.exe --dev`) running locally on Windows.
- **Alternatives Considered:** LiveKit Cloud, Docker Compose, WSL2.
- **Why Selected:** Satisfies genuine $0 cost constraint without credit cards. Official standalone Windows binary (`v1.13.7`) runs directly without Docker overhead or Hyper-V/WSL complications. `--dev` mode provisions an in-memory datastore and signaling port (7880) with zero external Redis dependency.
- **Tradeoffs:** Dev mode stores room state in memory (resets on restart); suitable for single-node development and demos, not multi-node horizontal clustering.
- **Cost:** $0.00.
- **Risk:** Minor firewall prompt on first Windows launch.
- **Future Replacement Path:** Docker Compose or Kubernetes Helm chart in production with external Redis cluster.

---

## TDR-002: LiveKit Agents SDK Architecture (AgentSession vs VoicePipelineAgent)
- **Decision:** Use modern `livekit-agents` 1.8+ with `AgentSession` and `AgentServer`.
- **Alternatives Considered:** Legacy `VoicePipelineAgent` (0.x).
- **Why Selected:** Current official LiveKit Agents documentation deprecates `VoicePipelineAgent` in favor of `AgentSession`. Modern SDK provides native `@function_tool` decorators on `Agent`, unified pipeline orchestration, per-turn latency via `ChatMessage.metrics`, and native speculative turn-taking.
- **Tradeoffs:** Newer API conventions require adhering strictly to 1.x type contracts.
- **Cost:** $0.00.
- **Risk:** Older internet tutorials reference deprecated classes; mitigated by adhering strictly to official 2026 documentation.
- **Future Replacement Path:** Continual minor updates within `livekit-agents` 1.x.

---

## TDR-003: Core Speech-to-Text (STT) Strategy
- **Decision:** Dual-Engine Architecture:
  1. **Primary Zero-Cost Local:** In-process `FasterWhisperSTT` subclassing `livekit.agents.stt.STT` wrapping `faster-whisper` (CTranslate2) on NVIDIA CUDA.
  2. **Optional Zero-Cost Cloud Adapter:** `livekit-plugins-groq` (`whisper-large-v3-turbo`) using Groq Free Tier (no credit card).
- **Alternatives Considered:** OpenAI Cloud Whisper ($0.006/min), Deepgram Nova-2 (paid), standard PyTorch Whisper (high latency).
- **Why Selected:** Hardware audit revealed RTX 5090 (24 GB VRAM), where `faster-whisper` base.en/small.en executes with <150ms transcription latency at $0. Groq adapter allows instant zero-cost cloud acceleration without billing.
- **Tradeoffs:** Local CTranslate2 requires CUDA runtime DLLs; Groq requires a free API key and has rate limits.
- **Cost:** $0.00.
- **Risk:** PyPI lacks `livekit-plugins-whisper`; mitigated by clean custom STT adapter subclass.
- **Future Replacement Path:** Production streaming ASR (e.g. self-hosted Kaldi/Whisper CTranslate2 microservice or managed Deepgram).

---

## TDR-004: Language Model (LLM) Strategy & Intent Decoupling
- **Decision:** Local Ollama runtime hosting `qwen2.5:7b` (Q4_K_M) accessed via `livekit-plugins-openai` (`openai.LLM.with_ollama`) with an optional Groq Free Tier fallback (`llama-3.3-70b-versatile` / `llama-3.1-8b-instant`).
- **Alternatives Considered:** `qwen3.5:9b` (reasoning model), `allenporter/xlam:1b`, OpenAI GPT-4o-mini (paid), Claude 3.5 Sonnet (paid).
- **Why Selected:** Environment audit confirmed Ollama 0.34.2 is already running on the machine with `qwen2.5:7b`. Live execution confirmed 130 tokens/second generation speed on RTX 5090 and accurate function calling. Reasoning models (`qwen3.5`) were rejected due to `<think>` token generation latency causing 2-5s conversational dead air.
- **Core Principle:** The LLM decides *intent* only; domain services determine *authorization and state validity*.
- **Tradeoffs:** 7B model requires strict system prompts and typed tool schemas to prevent hallucinated argument names.
- **Cost:** $0.00.
- **Risk:** Model cold-start on first load (mitigated by prewarming in startup script).
- **Future Replacement Path:** Self-hosted vLLM cluster or cloud LLM gateway.

---

## TDR-005: Text-to-Speech (TTS) Strategy
- **Decision:** Local `Kokoro-82M` (via `kokoro-onnx` / `Kokoro-FastAPI` OpenAI-compatible endpoint) accessed via `openai.TTS`.
- **Alternatives Considered:** ElevenLabs (paid), Cartesia (paid), Coqui TTS (abandoned/heavy), pyttsx3 (robotic quality).
- **Why Selected:** Kokoro produces natural voice cadence with an 82M parameter footprint. Supported officially in LiveKit documentation via OpenAI-compatible endpoints (`http://localhost:8880/v1`) with response format `wav`.
- **Tradeoffs:** Requires local ONNX runtime or Kokoro server running alongside agent.
- **Cost:** $0.00.
- **Risk:** First-chunk audio latency must be monitored (<300ms target).
- **Future Replacement Path:** Self-hosted Kokoro streaming microservice or managed Cartesia Sonic.

---

## TDR-006: Voice Activity Detection (VAD) & Turn Detection
- **Decision:** `livekit-plugins-silero` (Silero VAD v5) combined with `TurnHandlingOptions(turn_detection=inference.TurnDetector(model="v1-mini"))`.
- **Alternatives Considered:** WebRTC VAD (coarse), Cloud TurnDetector v1 (requires LiveKit Cloud).
- **Why Selected:** Silero VAD runs entirely locally via ONNX with zero cloud dependency. `TurnDetector(v1-mini)` is specifically engineered to run locally on CPU, analyzing acoustic pitch and cadence to minimize turn-taking latency.
- **Tradeoffs:** Aggressive endpointing (<300ms) can cut off hesitant speakers; mitigated by configuring `min_delay=0.3s`, `max_delay=1.0s`.
- **Cost:** $0.00.
- **Risk:** Audio echo if AEC is disabled in browser.
- **Future Replacement Path:** Integrated speech-to-speech multimodal models.

---

## TDR-007: Domain State & Business Policy Architecture
- **Decision:** Deterministic, in-memory domain service layer with thread-safe lock primitives and strict Pydantic schemas. The LLM has zero direct database mutation authority.
- **Alternatives Considered:** Direct SQL query generation by LLM, ORM auto-commit from tool arguments.
- **Why Selected:** Prevents LLM hallucinations from corrupting schedule availability. A booking can only occur if `BookingPolicyService.validate_and_reserve()` returns success.
- **Tradeoffs:** In-memory state resets between application runs (seeded from JSON fixture files).
- **Cost:** $0.00.
- **Risk:** Race conditions on simultaneous slot booking (handled via mutex/semaphore on showing slot ID).
- **Future Replacement Path:** PostgreSQL with row-level locking (`SELECT ... FOR UPDATE`) or transactional Redis.

---

## TDR-008: Real-Time Business Event Synchronization
- **Decision:** Dual-plane messaging:
  1. **Storage Plane:** Local append-only JSONL event journal (`data/events.jsonl`).
  2. **Realtime Plane:** WebRTC reliable data packets published over `room.local_participant.publish_data(topic="proprelay.events", reliable=True)`.
- **Alternatives Considered:** Polling REST API, separate WebSocket server, Redis Pub/Sub, Kafka.
- **Why Selected:** Reuses the established LiveKit WebRTC peer connection, achieving zero additional ports, low-latency peer-to-peer delivery (~5-15ms local transport, non-guaranteed over WAN), and true real-time UI synchronization without running another server.
- **Tradeoffs:** LiveKit data packets are dropped if participant is completely disconnected; mitigated by client-side deduplication and querying current snapshot on reconnect.
- **Cost:** $0.00.
- **Risk:** Payload size limits (kept under 15KB per event).
- **Future Replacement Path:** Apache Kafka or AWS EventBridge with WebSocket gateway.

---

## TDR-009: Frontend Operations Dashboard
- **Decision:** Modern React 19 + TypeScript + Vite + Tailwind CSS dashboard leveraging `@livekit/components-react` and `livekit-client`.
- **Alternatives Considered:** Generic LiveKit Meet demo app, plain HTML/JS, Next.js fullstack.
- **Why Selected:** Clean separation between frontend (static client) and Python backend. Focuses strictly on engineering clarity: real-time audio controls, speaker state visualization, live transcript, event timeline, and latency metric breakdown.
- **Tradeoffs:** Requires Node.js build step during development.
- **Cost:** $0.00.
- **Risk:** Browser microphone permission policy on localhost (handled via standard browser WebRTC APIs).
- **Future Replacement Path:** Integration into enterprise CRM/property management dashboard.

---

## TDR-010: Python Package Management with uv
- **Context:** Python dependency management and resolution across virtual environments and local developer setups must be deterministic, fast, and repeatable.
- **Decision:** Use `uv` with a PEP 621 `pyproject.toml` specification and committed `uv.lock`.
- **Alternatives Considered:** Poetry, Pipenv, pip-tools, standard pip + requirements.txt.
- **Rationale:** `uv` resolves and installs Python 3.12 dependencies orders of magnitude faster than pip/Poetry, generates cross-platform lockfiles, and eliminates tool drift without requiring external package management daemons.
- **Tradeoffs:** Requires `uv` binary to be installed on developer systems (installed and verified v0.11.16).
- **Future Migration Path:** `pyproject.toml` conforms to standard packaging standards (Hatchling backend), allowing seamless fallback to standard pip or Docker builder environments if required.

---

## TDR-011: In-Memory Repositories for Local Zero-Cost Mode
- **Context:** The local demonstration and development environment requires persistence, query capabilities, and mutation safety without provisioning heavyweight database services.
- **Decision:** Implement typed in-memory repositories (`InMemoryPropertyRepository`, `InMemoryShowingRepository`, `InMemoryBookingRepository`, `InMemoryLeadRepository`) seeded from static JSON fixtures.
- **Alternatives Considered:** SQLite, PostgreSQL via Docker, TinyDB, Redis.
- **Rationale:** Eliminates external service dependencies, credentials, and Docker containers, satisfying the hard $0 local execution constraint while providing instantaneous test execution (<0.5s for 57 tests).
- **Tradeoffs:** State does not persist across application restarts; single-process only.
- **Future Migration Path:** Repository interfaces (`IPropertyRepository`, `IShowingRepository`, etc.) are defined with `Protocol`, enabling drop-in PostgreSQL/SQLAlchemy or asyncpg adapters without altering domain models or tools.

---

## TDR-012: Deterministic Booking Policy Outside the LLM
- **Context:** Voice AI agents frequently hallucinate slot availability, double-book calendars, or accept invalid dates if business rules are left to prompt instructions.
- **Decision:** Enforce all booking validation, collision prevention, idempotency resolution, and state mutations exclusively within `BookingPolicyService`. The LLM only expresses intent by calling `book_showing`.
- **Alternatives Considered:** LLM prompt-guided validation, database triggers, ORM model hooks.
- **Rationale:** Separates nondeterministic natural language understanding from deterministic business rules. Ten distinct policy rules return typed error codes (`SLOT_UNAVAILABLE`, `DATE_IN_PAST`, etc.) and ensure 100% testable, deterministic policy validation that prevents unverified mutations regardless of LLM output.
- **Tradeoffs:** Agent prompts must cleanly format structured error responses to conversational speech.
- **Future Migration Path:** Extend policy rules to handle multi-agent calendars, landlord approval workflows, or external CRM webhooks.

---

## TDR-013: JSONL Event Journal
- **Context:** The system requires an append-only, durable telemetry and state audit trail for all business actions, latency tracking, and operational debugging.
- **Decision:** Implement `EventJournal` persisting structured `DomainEvent` envelopes to an append-only local file (`data/events.jsonl`).
- **Alternatives Considered:** SQLite audit table, syslog, ElasticSearch, Kafka.
- **Rationale:** Simple, zero-dependency, human-readable, and machine-parsable format. Guarantees deterministic serialization and clean test truncation without running external logging daemons.
- **Tradeoffs:** Local single-file storage requires periodic rotation in production; does not support distributed indexing.
- **Future Migration Path:** Replace or supplement file append with an asynchronous background worker streaming events to Kafka, AWS S3, or ClickHouse.

---

## TDR-014: Download Script Instead of Committed Binaries
- **Context:** LiveKit standalone server (`livekit-server.exe`) and CLI (`lk.exe`) are large Windows binaries (~50MB+) that must not bloat version control.
- **Decision:** Gitignore all binaries in `bin/*` (preserving `bin/.gitkeep`) and provide an idempotent PowerShell script (`scripts/download_livekit.ps1`) to download official releases from GitHub.
- **Alternatives Considered:** Committing binaries to Git, Git LFS, Docker container.
- **Rationale:** Keeps repository lightweight, prevents Git repository bloat, allows version pinning via script parameters (`$ServerVersion`), and complies with open-source distribution best practices.
- **Tradeoffs:** Requires initial network download when cloning repository for the first time.
- **Future Migration Path:** Integrate into CI/CD build scripts or devcontainer provisioning definitions.

---

## TDR-015: Injected Clock for Deterministic Testing
- **Context:** Showing reservations are strictly time-dependent (rejecting dates in the past and filtering upcoming slots). Scattering `datetime.now()` prevents reproducible automated tests.
- **Decision:** Introduce a lightweight `Clock` protocol with `SystemClock` for runtime and `FrozenClock` for deterministic tests.
- **Alternatives Considered:** `freezegun`, `time-machine`, mocking `datetime.now`.
- **Rationale:** Dependency injection of a domain-native clock avoids monkey-patching C-extensions or runtime globals, ensures type-safe datetime evaluation, and guarantees that past/present/future tests remain completely independent of the real wall clock.
- **Tradeoffs:** Requires passing the clock dependency through services.
- **Future Migration Path:** Can be extended to support timezone conversions or simulated fast-forward calendar simulations.

---

## TDR-016: Typed Tool and Application Boundary
- **Context:** LLM tool calls must translate from string/dict payloads into strongly-typed domain operations with validated schemas and standardized responses.
- **Decision:** Encapsulate all agent tools in `AgentTools` using explicit Pydantic input models, typed output models, and generic `ToolResult[T]` error envelopes.
- **Alternatives Considered:** Raw dictionary arguments, monolithic agent callback functions.
- **Rationale:** Guarantees strict input validation, prevents invalid types from reaching the domain layer, unifies telemetry and event emission across tool invocations, and cleanly decouples LiveKit SDK tool bindings from domain business logic.
- **Tradeoffs:** Requires declaring input and output schemas for each tool.
- **Future Migration Path:** Direct integration with modern `@function_tool` decorators in `livekit-agents` 1.8+ in Phase 3 without modifying the tool implementation logic.

---

## TDR-017: LiveKit Agents 1.8 `AgentServer` & `AgentSession` Runtime
- **Context:** `livekit-agents` v1.8 supersedes legacy `VoicePipelineAgent` with the `AgentServer` worker and `AgentSession` event-driven lifecycle.
- **Decision:** Build the Phase 3 voice runtime around `AgentServer` decorating an asynchronous `rtc_session` entrypoint, instantiating `AgentSession` with decoupled STT, VAD, LLM, and TTS pipelines.
- **Alternatives Considered:** Deprecated `VoicePipelineAgent`, raw WebRTC peer connection management, external SIP trunks.
- **Rationale:** Aligns with official LiveKit current architecture; natively supports turn detection, pre-warming, metric telemetry, tool execution callbacks, and clean room lifecycle management.
- **Tradeoffs:** Required adapting to the modern `livekit-agents` 1.8 API surface.
- **Future Migration Path:** Enables multi-agent handoffs and phone telephony (SIP) support without architectural rewrites.

---

## TDR-018: Faster-Whisper Local CUDA float16 STT with `StreamAdapter`
- **Context:** PropRelay requires zero-cost, private, high-accuracy speech-to-text without cloud API keys or external SaaS latency.
- **Decision:** Implement a custom `FasterWhisperSTT` subclassing LiveKit's `stt.STT`, running `faster-whisper-base.en` with CTranslate2 on NVIDIA CUDA (`float16`), wrapped in `stt.StreamAdapter` with Silero VAD.
- **Alternatives Considered:** OpenAI Whisper cloud API, Deepgram Nova-2, local Whisper.cpp, Vosk.
- **Rationale:** Achieves an empirical latency of ~340ms for a 3.8s utterance (Real-Time Factor ~0.09x) on NVIDIA hardware with zero cloud cost. `StreamAdapter` buffers VAD speech segments cleanly without hallucinating interim text.
- **Tradeoffs:** Requires local GPU with CUDA support for optimal sub-500ms latency (falls back to CPU int8 if CUDA unavailable).
- **Future Migration Path:** Support larger Whisper models (`small.en`, `distil-whisper`) via environment variable toggling.

---

## TDR-019: Standalone Local Kokoro ONNX TTS HTTP Microservice
- **Context:** Voice agent needs natural, high-fidelity speech synthesis with low latency at zero cloud cost.
- **Decision:** Deploy a lightweight FastAPI service on port 8880 using `kokoro-onnx` (`kokoro-v1.0.onnx` + `voices-v1.0.bin`, `af_alloy` voice) exposing an OpenAI-compatible `/v1/audio/speech` endpoint returning 24kHz WAV audio.
- **Alternatives Considered:** ElevenLabs, OpenAI TTS Cloud API, Coqui TTS, Piper TTS.
- **Rationale:** Kokoro ONNX produces expressive American English speech in ~450-700ms TTFB without GPU requirements or cloud subscription fees. Exposing an OpenAI-compatible endpoint allows seamless integration with `livekit.plugins.openai.TTS`.
- **Tradeoffs:** Requires initial one-time download of ONNX model (~325MB) and voice embeddings (~28MB).
- **Future Migration Path:** Add streaming chunked HTTP transfer encoding or multi-voice speaker assignment based on property persona.

---

## TDR-020: 100% Local Turn Detection via `turn-detector-v1-mini`
- **Context:** Standard fixed silence timers (e.g. 1.5s) introduce perceptible conversational lag. Cloud inference endpoints introduce credentials requirements and latency.
- **Decision:** Configure `livekit.agents.inference.TurnDetector(version="v1-mini")` to run the 108MB local ONNX turn detection model entirely in-process.
- **Alternatives Considered:** Cloud `turn-detector-v1` gateway, raw fixed silence delay.
- **Rationale:** Accurately classifies whether the human has concluded their grammatical utterance vs paused mid-sentence, reducing end-of-utterance latency to ~930ms with zero network requests to LiveKit Cloud.
- **Tradeoffs:** Resident in-memory footprint of ~108MB.
- **Future Migration Path:** Dynamic threshold tuning based on conversation domain and ambient acoustic noise levels.

---

## TDR-021: Local Silero VAD Interruption & Barge-in Handling
- **Context:** Natural conversations require the caller to interrupt (barge-in) the agent while it is speaking. LiveKit 1.8 defaults to cloud adaptive interruption which fails with 401 in offline mode.
- **Decision:** Explicitly configure `AgentSession` turn handling with `interruption={"enabled": True, "mode": "vad", "min_duration": 0.3, "resume_false_interruption": True}`.
- **Alternatives Considered:** Cloud adaptive barge-in, client-side mute buttons, disabling interruptions.
- **Rationale:** 100% offline, $0 local execution. If the user speaks for >300ms while the agent is speaking, audio output is canceled within sub-100ms and the pipeline returns to `LISTENING`.
- **Tradeoffs:** Loud acoustic feedback in environments without headphones can occasionally trigger false barge-ins (mitigated by AEC warmup and min_duration threshold).
- **Future Migration Path:** Client-side WebRTC Acoustic Echo Cancellation (AEC) filtering.

---

## TDR-022: WebRTC Reliable Data Channel for Real-Time Typed Domain Events
- **Context:** The frontend operations dashboard requires low-latency synchronization of state changes, tool executions, transcripts, and latency telemetry without managing a separate WebSocket connection.
- **Decision:** Implement `LiveKitEventBroadcaster` using `room.local_participant.publish_data` on topic `proprelay.events` with `reliable=True`, bound via `CompositeEventPublisher` alongside the JSONL journal.
- **Alternatives Considered:** Separate FastAPI WebSocket connection, polling `/api/events`, Server-Sent Events (SSE).
- **Rationale:** Reuses the existing WebRTC PeerConnection already established for audio. Zero port proliferation. SCTP reliable data channels provide ordered delivery at the transport layer, with typical local latency of ~5-15ms, while client-side deduplication (`seenEventIdsRef`) guards against duplicate triggers.
- **Tradeoffs:** Event payloads must stay within WebRTC data channel packet size constraints (< 64KB per message).
- **Future Migration Path:** Channel multiplexing or client-initiated RPC requests over data channels.

---

## TDR-023: Function Tool Output Serialization to JSON Dictionaries
- **Context:** LiveKit Agents 1.8 requires `@llm.function_tool` functions to return standard JSON-serializable types (`dict`, `str`, `int`, `list`). Returning raw Pydantic model objects logs an `invalid output` error and replaces the response with a generic error message.
- **Decision:** Have voice tool wrappers call `res.model_dump(mode="json")` before returning to LiveKit.
- **Alternatives Considered:** Subclassing `dict`, returning raw strings, converting inside LiveKit internals.
- **Rationale:** Fully compliant with LiveKit's internal output validator; preserves 100% of Phase 2 domain typing, validation, and `ToolResult` envelopes, while ensuring the local Ollama LLM receives clean, structured JSON listings.
- **Tradeoffs:** Tests asserting on tool wrapper calls inspect dictionary keys (`result["success"]`) rather than Pydantic attributes.
- **Future Migration Path:** Standardized serializer helper across all future tool packages.

---

## TDR-024: Unified FastAPI Serving (Token Dispenser + WebRTC Dispatch + React Frontend)
- **Context:** Running frontend, API, token issuance, and agent dispatch across disparate development servers creates CORS complexity and multi-process overhead for local users.
- **Decision:** Implement a unified FastAPI server (`proprelay/api/server.py`) that:
  1. Issues signed WebRTC participant JWTs (`POST /api/token`).
  2. Dispatches the agent worker to the room via LiveKit Server API.
  3. Monitors system health across LiveKit, Ollama, and Kokoro (`GET /api/health`).
  4. Statically mounts the production-built React application from `frontend/dist/`.
- **Alternatives Considered:** Running standalone Nginx, separate Vite dev server on port 5173, reverse proxies.
- **Rationale:** Single-port (`http://localhost:8000`) turnkey experience. Zero CORS errors in production mode. Instant access from any browser on localhost.
- **Tradeoffs:** Requires building frontend assets (`pnpm build`) prior to static serving.
- **Future Migration Path:** Containerize the unified service into a single Docker image for cloud deployment.

---

## TDR-025: Application-Level Action Confirmation Safety Gate (Staged PendingAction vs LLM Intent)
- **Context:** Consequential domain mutations (booking, rescheduling, and cancelling showings) have real-world operational effects. Relying on an LLM to accurately track user intent across turns, remember confirmation status, and refrain from premature mutations is inherently unsafe and prone to hallucinations.
- **Decision:** Implement a strict, application-level safety gate within `ConversationContext` and `AgentTools`. When a tool like `book_showing`, `reschedule_showing`, or `cancel_showing` is called with `confirmed=False`, the system does NOT mutate database state. Instead, it validates all inputs, pre-checks slot availability, generates an explicit proposal question, stages a typed `PendingAction` object with an expiration turn limit, and emits a `*.confirmation.requested` domain event. The state mutation is ONLY executed when the user subsequently confirms (via `confirm_pending_action()` or `confirmed=True`), which retrieves the staged `PendingAction` and hands it to `BookingPolicyService`.
- **Alternatives Considered:** Asking the LLM in system prompt to "only call book_showing after asking for confirmation", multi-agent confirmation router, storing confirmation flags in raw conversation history.
- **Rationale:** Hard deterministic safety gate. Even if the LLM emitted `confirmed=True` prematurely, it would fail with `NO_PENDING_ACTION` unless a valid proposal was already staged. Zero unverified mutations can bypass the gate.
- **Tradeoffs:** Adds an explicit two-step turn sequence for bookings, reschedules, and cancellations.
- **Future Migration Path:** Configurable confirmation policies per operation type or user privilege level.

---

## TDR-026: Deterministic Conversational Context & Reference Resolution
- **Context:** Callers speak using natural conversational references ("the first one", "the cheaper property", "the 2 PM slot", "tomorrow afternoon") rather than citing database UUIDs. Expecting local 7B models (`qwen2.5:7b`) to reliably parse, maintain, and ground these references across multi-turn sessions results in hallucinated IDs and context drift.
- **Decision:** Maintain a dedicated, stateful `ConversationContext` instance per session. It stores the active search shortlist, currently selected property, available calendar slots, and renter profile. All property and slot lookups in tools pass through deterministic reference resolvers (`resolve_property_reference` and `resolve_slot_reference`) backed by regex matching and sorting. Date and time normalization is anchored strictly to an injected `Clock` abstraction.
- **Stale Action Invalidation:** If a user stages a booking proposal for Property A and in the next turn asks about Property B or changes the date, `ConversationContext` immediately wipes `pending_action`. A subsequent "Yes" will safely fail with `NO_PENDING_ACTION` rather than reserving the obsolete slot.
- **Alternatives Considered:** Relying entirely on LLM conversation context, LangChain conversational memory, vector database lookups.
- **Rationale:** Deterministic reference resolution engine that maps conversational ordinal, price, and time tokens directly to domain entities in sub-millisecond execution time, eliminating reliance on LLM ID memorization.
- **Tradeoffs:** Reference vocabulary (e.g. ordinals, superlatives, time patterns) must be maintained in deterministic parsing rules.
- **Future Migration Path:** Extend superlative resolution to multi-criteria sorting (e.g., "closest with pets allowed").

---

## TDR-027: LiveKit Primitives & Multi-Turn State Machine Architecture
- **Context:** Voice agents can be structured either as a collection of specialized sub-agents with handoffs (e.g., LiveKit `AgentTask`, `AgentHandoff`) or as a unified single agent backed by an explicit domain state machine and structured context.
- **Decision:** Architect PropRelay as a unified single agent with an explicit application-level state machine (`WorkflowState`) and `ConversationContext`, rather than multi-agent task handoffs.
- **Alternatives Considered:** Multi-agent handoff pattern (Discovery Agent -> Scheduling Agent -> Confirmation Agent) via LiveKit `AgentTask` or `AgentHandoff`.
- **Rationale:** In spoken residential real estate dialogues, callers constantly interrupt, switch topics, and backtrack (e.g., asking about parking while in the middle of picking a showing date). Multi-agent handoffs introduce severe boundary thrashing, duplicate voice pipelines, increased latency, and loss of shared context when callers cross back and forth. A unified agent backed by deterministic tools and an explicit state machine handles interruptions and context switching effortlessly with minimal latency.
- **Tradeoffs:** Tool definitions and system prompts must accommodate both discovery and scheduling workflows cleanly.
- **Future Migration Path:** Support subagent handoff for complex escalation scenarios (e.g., live human operator handoff).

---

## TDR-028: Concurrency & Deadlock Prevention in Showing Rescheduling
- **Context:** Rescheduling an existing showing reservation atomically swaps two showing slots: releasing the old slot back to `AVAILABLE` and claiming the new slot as `BOOKED`. Under concurrent requests (e.g., User 1 moving from Slot A to Slot B while User 2 moves from Slot B to Slot A), naive locking order causes lock inversion deadlocks.
- **Decision:** In `BookingPolicyService.validate_and_reschedule()`, enforce sorted slot locking order (`sorted([old_slot_id, new_slot_id])`). Both slot locks are acquired via a single composite `async with (lock_a, lock_b):` context manager in lexicographical order.
- **Alternatives Considered:** Global repository lock, optimistic concurrency with retry loops, two-phase commit.
- **Rationale:** Guarantees absolute deadlock freedom under arbitrary concurrency while maintaining fine-grained, per-slot locking scalability.
- **Tradeoffs:** Both slot IDs must be validated before acquiring locks.
- **Future Migration Path:** Distributed lock provider (e.g. Redis Redlock) if scaling to multi-node clusters.

---

## TDR-029: DomainEvent Schema v1 with Monotonic Sequencing & SHA-256 Hash Chaining
- **Context:** State auditability, event sourcing, and compliance require tamper-evident log integrity without relying on external cloud ledger services or expensive blockchain solutions.
- **Decision:** Standardize on `DomainEvent` schema v1 with monotonic 64-bit integer sequences (`sequence_number`) and SHA-256 hash chaining (`previous_event_hash`) linking each event to its predecessor's canonical JSON.
- **Alternatives Considered:** Unchained JSONL lines, SQLite WAL journal, external append-only log services (AWS QLDB).
- **Rationale:** Lightweight, $0 local implementation providing mathematical tamper-evidence, corruption detection, and sequential replay guarantees.
- **Tradeoffs:** Event insertion requires sequential hash computation (~0.05ms overhead).
- **Future Migration Path:** Merkle tree anchoring to external public timestamping services.

---

## TDR-030: Application-Level WebRTC Data Channel Event Deduplication
- **Context:** While LiveKit WebRTC reliable data channels (`reliable=True`) use SCTP retransmissions, network rebinding, reconnection events, or proxy re-dispatches can result in duplicate message deliveries to the browser.
- **Decision:** Implement client-side event deduplication in React (`seenEventIdsRef = useRef<Set<string>>(new Set())`) filtering out previously observed UUIDs before state mutations or timeline rendering.
- **Alternatives Considered:** Server-side connection tracking, ignoring duplicates, transport-level deduplication alone.
- **Rationale:** Guarantees idempotent client-side event handling and prevents duplicate UI reactions, counter increments, or audio alerts.
- **Tradeoffs:** Client memory retains a set of seen event IDs for the duration of the session.
- **Future Migration Path:** Bounded LRU cache or sliding window for very long-lived sessions.

---

## TDR-031: In-Memory Automated PII Redaction at the Event Boundary
- **Context:** Logging phone numbers and emails in unredacted plaintext violates privacy and compliance standards (GDPR, CCPA).
- **Decision:** Automatically mask phone numbers (e.g. `+1-555-***-1234`) and email usernames (e.g. `j***n@domain.com`) in memory within `AppendOnlyEventJournal` prior to persistence or broadcast.
- **Alternatives Considered:** Post-processing log scrapers, client-side masking, plaintext local storage.
- **Rationale:** Guarantees zero sensitive data leakage to persistent disk or network packets while preserving debugging utility and entity correlation.
- **Tradeoffs:** Regex execution adds ~0.1ms serialization overhead per event.
- **Future Migration Path:** Enterprise DLP engine integration (e.g., Presidio).

---

## TDR-032: Multi-Turn Behavioral Evaluation Suite with 15 Canonical Scenarios
- **Context:** Traditional voice benchmarks test isolated components (STT WER, LLM tokens/sec) rather than multi-turn goal completion, edge case handling, and conversational safety.
- **Decision:** Build a 15-scenario behavioral evaluation suite (`tests/scenarios/S01` to `S15`) defined in declarative YAML covering property discovery, ambiguous narrowing, collision recovery, two-phase confirmation, stale action invalidation, atomic rescheduling, cancellation, lead capture, date corrections, idempotency, reference resolution, barge-in, and out-of-domain queries.
- **Alternatives Considered:** End-to-end audio recording re-injection, manual QA testing, single-turn prompt evals.
- **Rationale:** 100% automated, reproducible, deterministic CI/CD regression protection for all voice agent behavioral paths.
- **Tradeoffs:** Scenarios must be authored and maintained as YAML specifications.
- **Future Migration Path:** Automated scenario synthesis from historical production call transcripts.

---

## TDR-033: Eight Deterministic Judges for Consequential Safety and Policy Grounding
- **Context:** Evaluating voice agents with LLM judges alone produces flaky, non-deterministic test results and cannot reliably assert state invariants.
- **Decision:** Implement 8 deterministic Python judges inspecting typed execution traces: `ConsequentialSafetyJudge`, `GroundingJudge`, `ConfirmationSafetyJudge`, `StaleActionJudge`, `StateTransitionJudge`, `ToolCallCorrectnessJudge`, `DeterministicDateJudge`, `LatencySLAJudge`.
- **Alternatives Considered:** Cloud LLM judge prompts (e.g. GPT-4 as judge), fuzzy string matching.
- **Rationale:** Mathematical certainty on safety-critical business rules (e.g. 100% guarantee that zero unconfirmed bookings mutate database state).
- **Tradeoffs:** Judges require access to structured session traces rather than raw audio alone.
- **Future Migration Path:** Pluggable judge framework allowing external custom rule authoring.

---

## TDR-034: Local Semantic Evaluation via Ollama Qwen 2.5 7B
- **Context:** Spoken responses must be evaluated for tone, brevity, and persona adherence without incurring cloud costs or leaking user transcripts.
- **Decision:** Implement `OllamaSemanticJudge` utilizing local Ollama `qwen2.5:7b` to score persona adherence and spoken conciseness.
- **Alternatives Considered:** OpenAI API, Claude API, omitting semantic tone checks.
- **Rationale:** Preserves 100% offline, $0 cost architecture while providing automated qualitative feedback.
- **Tradeoffs:** Local 7B model evaluation takes ~1.5s per turn compared to instant deterministic checks.
- **Future Migration Path:** Fine-tuned local judge specialized for conversational dialogue evaluation.

---

## TDR-035: Sample Size Guard Policy for Honest Latency Percentile Computation
- **Context:** Computing p50, p90, and p99 on tiny sample counts ($N = 1$ or $2$) is mathematically unsound and produces misleading performance claims.
- **Decision:** Enforce `SAMPLE_SIZE_THRESHOLD = 3` in `compute_percentiles()`. When $N < 3$, return explicit `"insufficient samples (N=...)"` markers.
- **Alternatives Considered:** Fabricating interpolated percentiles, returning NaN, omitting sample counts.
- **Rationale:** Enforces rigorous engineering honesty and statistical integrity across all reports and UI panels.
- **Tradeoffs:** Initial turns in a new session do not display percentile distributions until sufficient samples accumulate.
- **Future Migration Path:** Configurable confidence interval reporting for enterprise deployments.

---

## TDR-036: Structured Error Taxonomy with Typed Recovery Actions
- **Context:** Unhandled exceptions or ambiguous error strings lead to silent voice agent failure or confusing spoken outputs.
- **Decision:** Create a typed `StructuredError` envelope and `ErrorTaxonomy` classifying failures into 7 categories (`STT_FAILURE`, `LLM_FAILURE`, `TTS_FAILURE`, `TOOL_EXECUTION`, `WEBRTC_TRANSPORT`, `VALIDATION_POLICY`, `SYSTEM_RESOURCE`) with explicit severity levels and typed recovery actions (`REASK_USER`, `PROMPT_ALTERNATIVE_SLOT`, etc.).
- **Alternatives Considered:** Generic Python exception handling, raw logging without classification.
- **Rationale:** Empowers the conversational agent to gracefully recover from failures and communicate actionable alternatives to the caller.
- **Tradeoffs:** Error handling requires mapping all component-level exceptions to taxonomy codes.
- **Future Migration Path:** Dynamic adaptive recovery routing based on historical recovery success rates.

---

## TDR-037: Turnkey Pre-Flight Diagnostics CLI (`proprelay.diagnostics`)
- **Context:** Complex local stacks combining CUDA STT, local LLM, ONNX TTS, and WebRTC servers require multi-step environment verification before launch.
- **Decision:** Build a standalone diagnostics module (`python -m proprelay.diagnostics`) that systematically probes Python, PyTorch CUDA, Faster-Whisper, Node.js, pnpm, LiveKit server, Ollama, Kokoro, and catalog fixtures, outputting a Rich console status table.
- **Alternatives Considered:** Shell scripts alone, manual troubleshooting guides, runtime crash reporting.
- **Rationale:** Provides instant, single-command triage of local dependencies, drastically reducing setup friction and debugging time.
- **Tradeoffs:** Adds `rich` dependency for terminal styling.
- **Future Migration Path:** Automated self-healing actions (e.g., auto-starting Ollama if stopped).

---

## TDR-038: Performance Benchmark Methodology & Statistical Integrity
- **Context:** Establishing reliable, reproducible voice pipeline latency baselines requires controlled inputs and strict statistical integrity.
- **Problem:** Measuring live microphone audio produces random variance, while computing percentiles on small sample sets ($N=1$) leads to fabricated metrics.
- **Hypothesis:** A controlled 30-utterance synthetic benchmark dataset with pre-synthesized audio fixtures and a minimum sample threshold ($N \ge 20$) yields repeatable empirical latency distributions.
- **Experiment:** Executed `BenchmarkSuite` with 25 iterations per stage across short, medium, long, tool, and no-tool queries.
- **Result:** Standard deviation across STT was stabilized within ~15%; guarded percentiles eliminated fabricated statistics.
- **Decision:** Mandate `BenchmarkSuite` (`python -m proprelay.performance.benchmark --all`) with minimum 20 iterations for all baseline reporting.
- **Tradeoffs:** Full benchmark run takes ~115s of compute time.
- **Verification:** Verified via `tests/test_performance_smoke.py::test_percentile_sample_size_guard`.

---

## TDR-039: Endpointing Minimum Delay Tuning
- **Context:** Conversational turn responsiveness depends heavily on end-of-utterance (EOU) detection delay.
- **Problem:** Phase 3 baseline configured fixed endpointing with `min_delay=0.5s`, causing a 932ms delay before the agent committed to responding.
- **Hypothesis:** Lowering `min_delay` from 0.5s to 0.3s accelerates turn-taking without increasing premature turn cutoffs.
- **Experiment:** Benchmarked three configurations: Config A (fixed 0.5s), Config B (fixed 0.3s), and Config C (dynamic 0.2s).
- **Result:** Config B reduced EOU commit from 932.4ms to 485.2ms (-447.2ms) with only 2.1% false cutoffs. Config C caused 6.8% premature cutoffs during hesitant pauses.
- **Decision:** Adopt Configuration B (`endpointing_mode="fixed"`, `min_endpointing_delay=0.3`, `max_endpointing_delay=2.0`).
- **Tradeoffs:** Fast speakers with brief mid-sentence hesitations (< 300ms) may experience slight premature cutoffs.
- **Verification:** Empirically verified in `reports/performance/phase6_comparison.md`.

---

## TDR-040: Speculative Preemptive Generation Strategy
- **Context:** LiveKit Agents supports starting LLM prompt evaluation before final end-of-turn confirmation.
- **Problem:** Waiting for complete silence commitment before initiating LLM inference adds 75–120ms to caller wait time.
- **Hypothesis:** Preemptive generation enables Ollama to evaluate prompt tokens speculatively while trailing silence is analyzed.
- **Experiment:** Compared `enable_preemptive_generation=False` vs `True` across benchmark queries.
- **Result:** Effective TTFT dropped from 75.5ms to 16.98ms (p50); speculative compute discarded on interruption was only 4.5%.
- **Decision:** Enable `enable_preemptive_generation=True` by default.
- **Tradeoffs:** Minor GPU compute wasted if user resumes speaking within the trailing endpoint window.
- **Verification:** Measured TTFT p50 = 16.98ms in `reports/performance/baseline.md`.

---

## TDR-041: Preemptive TTS Architectural Rejection
- **Context:** LiveKit supports preemptive TTS to begin speech synthesis before the LLM completes full generation.
- **Problem:** Does the TTFB latency gain justify the risk of false speech output or GPU contention during cancellations?
- **Hypothesis:** Preemptive TTS reduces first-audio latency by ~150ms.
- **Experiment:** Evaluated `preemptive_tts=True` vs `False` under user barge-in and corrections.
- **Result:** Preemptive TTS resulted in 18.2% wasted audio generation and GPU memory spikes during user corrections ("Actually, Sunday").
- **Decision:** KEEP `preemptive_tts=False`. Conversational safety and prompt correction accuracy take precedence.
- **Tradeoffs:** Caller waits for the first complete sentence chunk (~408ms) rather than speculative partial phonemes.
- **Verification:** Validated in `reports/performance/baseline.md`.

---

## TDR-042: Local STT Performance Configuration & Audio Buffer Reuse
- **Context:** Faster-Whisper (CTranslate2) runs locally on NVIDIA CUDA.
- **Problem:** Inefficient audio buffer resampling and format conversion create unnecessary Python allocation overhead.
- **Hypothesis:** Persistent `AudioResampler` caching and in-process `float16` CUDA execution minimize audio preprocessing overhead.
- **Experiment:** Measured buffer conversions: 48kHz stereo to 16kHz mono took 0.02ms; float32 normalization took 0.01ms.
- **Result:** Overall preprocessing overhead is < 0.05ms; warm STT transcribes short utterances in 81ms (RTF ~0.48x across full suite).
- **Decision:** Standardize on `FasterWhisperSTT(device="cuda", compute_type="float16")` with pre-warmed engine.
- **Tradeoffs:** Requires ~1.5GB of dedicated VRAM.
- **Verification:** Verified via `STTProfiler.benchmark_audio_preprocessing`.

---

## TDR-043: Local TTS First-Chunk Streaming via Sentence Boundaries
- **Context:** Kokoro-ONNX synthesizes high quality 24kHz audio, but full paragraph synthesis takes ~1.5 seconds.
- **Problem:** Caller experiences noticeable silence if audio playback waits for the full multi-sentence reply.
- **Hypothesis:** Splitting agent responses at sentence boundaries allows immediate synthesis and playback of Sentence 1 while Sentence 2 generates concurrently.
- **Experiment:** Benchmarked full multi-sentence response (1,492ms) against first-sentence chunk (408ms).
- **Result:** Sentence 1 chunk delivered audio to the transport in 407.95ms (p50), yielding a **1,085.87ms earlier first-audio delivery**.
- **Decision:** Enforce sentence-chunked streaming on all multi-sentence responses.
- **Tradeoffs:** Inter-sentence pause must be smoothly managed by WebRTC audio track buffering.
- **Verification:** Documented in `reports/performance/baseline.md`.

---

## TDR-044: Safe Read-Only Catalog Caching & Concurrency Invariants
- **Context:** Domain repository lookups should execute in microseconds without caching volatile transactional state.
- **Problem:** Naive caching of showing availability causes stale slot representations and race condition failures.
- **Hypothesis:** In-memory caching can be safely applied to immutable property listings, while strictly forbidding caching of availability or bookings.
- **Implementation:** `SafeReadOnlyCache` with 300s TTL for property metadata; showing availability queries remain 100% dynamic.
- **Result:** Property lookup latency dropped from 0.08ms to < 0.01ms (100% hit ratio). Zero stale booking decisions occurred.
- **Decision:** Deploy `SafeReadOnlyCache` for static listings and search queries. Strictly prohibit availability caching.
- **Tradeoffs:** Memory cache invalidates after 300s.
- **Verification:** Verified in `tests/test_performance_smoke.py::test_domain_lookup_and_cache_latency_smoke`.

---

## TDR-045: Single-Machine Local Concurrency Scaling & Race Safety
- **Context:** PropRelay runs fully on-premise on a single workstation with local models.
- **Problem:** How does the system behave under concurrent caller loads, and does transactional locking hold?
- **Experiment:** Executed `ConcurrencyHarness` with simultaneous conflicting bookings and 1, 2, and 4 concurrent sessions.
- **Result:** Under simultaneous slot competition, exactly 1 session succeeded and 1 failed with `SLOT_UNAVAILABLE` (0.15ms lock evaluation). At 4 concurrent sessions, turn latency remained stable at ~61ms.
- **Decision:** Validate single-node concurrency up to 4 sessions for local workloads while explicitly documenting that this is not a distributed cloud SLA.
- **Tradeoffs:** At > 4 sessions, CUDA kernel scheduling contention begins to introduce queuing jitter.
- **Verification:** Verified via `tests/test_performance_smoke.py::test_concurrent_booking_race_safety_smoke`.

---

## TDR-046: Broad Performance Regression Thresholds for CI Smoke Testing
- **Context:** Automated tests must catch severe performance regressions without failing due to normal operating system jitter.
- **Problem:** Hyper-strict thresholds (< 1ms) cause false-positive test failures on busy developer machines.
- **Hypothesis:** Broad thresholds (e.g. repo lookup < 25ms, search < 30ms, journal append < 50ms) catch order-of-magnitude architectural regressions reliably.
- **Decision:** Implement `tests/test_performance_smoke.py` enforcing broad thresholds (< 25–50ms) and sample-size percentile guards ($N \ge 3$).
- **Tradeoffs:** Does not detect micro-regressions of 1–2ms.
- **Verification:** 100% passing across standard test runs.


