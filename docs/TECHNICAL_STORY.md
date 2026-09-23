# PropRelay — Technical Evolution Narrative

**"What I Would Explain in an Interview"**

This document provides the authentic engineering story behind PropRelay's architectural evolution across its six developmental stages. It communicates the engineering motivations, failure modes discovered, and technical decisions made at each milestone.

---

## Stage 1: The Local Real-Time Voice Foundation

### What Was Built:
- Integrated a standalone, self-hosted LiveKit SFU binary on Windows.
- Built a custom Python `livekit-agents` worker connecting Faster-Whisper (ASR via CTranslate2 CUDA float16), local Ollama Qwen 2.5 (LLM), and Kokoro-82M (TTS via ONNX Runtime).
- Established a basic browser WebRTC client with microphone input and audio playback.

### Why This Stage Existed:
Before worrying about complex real estate business logic, I needed to prove that a **zero-recurring-cost, 100% local voice pipeline was physically viable** on a single workstation without third-party cloud APIs. 

Most voice demos rely on Twilio, Deepgram, and ElevenLabs. If you can't get sub-2-second local audio turnaround on consumer hardware, everything else is moot. Stage 1 established our baseline turn latency (~2,003.9 ms), proved that CTranslate2 and Ollama could coexist in VRAM, and confirmed that WebRTC audio streaming functioned smoothly on localhost.

---

## Stage 2: The Deterministic Domain Layer

### What Was Built:
- Strongly-typed Pydantic domain models: `Property`, `ShowingSlot`, `Booking`, `Lead`, `DomainEvent`.
- In-memory thread-safe domain repositories with per-slot `asyncio.Lock` concurrency protection.
- `BookingPolicyService` enforcing 10 deterministic business rules (double-booking defense, past-date rejections, operating hours validation).
- An append-only JSON-lines `EventJournal` with an injected `Clock` abstraction for deterministic time testing.

### Why This Stage Existed:
The biggest mistake engineers make with Agentic AI is allowing the language model to talk directly to the database or assume the LLM will follow prompting instructions. 

In real estate leasing, double-booking an apartment tour or promising a discount on an occupied unit causes immediate customer frustration and lost revenue. I deliberately isolated the domain layer with **zero imports of WebRTC, LiveKit, or HTTP frameworks**. The domain rules had to be 100% testable, pure Python, and mathematically deterministic before letting an LLM anywhere near them.

---

## Stage 3: Conversational Workflows & Context Management

### What Was Built:
- A conversational finite state machine (`WorkflowState`) tracking discovery, property selection, calendar inspection, and confirmation states.
- `ConversationContext` handling colloquial reference resolution ("the first one", "the loft", "the cheapest").
- Deterministic temporal normalization (`normalize_date_expression`) anchored strictly to the reference clock.
- The **Two-Phase Confirmation Safety Gate**: `book_showing(confirmed=False)` stages a short-lived `PendingAction`, requiring explicit verbal confirmation before writing to disk.
- **Stale Action Invalidation**: Topic switches or property shifts instantly wipe staged proposals.

### Why This Stage Existed:
Real human voice conversation is messy. Users don't provide JSON payloads; they say *"Tell me about the first one"* or *"Book 2 PM for Alex"*. 

If the agent immediately commits a booking without asking for confirmation, a mis-heard word from the STT engine could book the wrong day or the wrong apartment. Stage 3 introduced human-in-the-loop confirmation gates and contextual reference tracking, ensuring that state mutations require explicit user agreement and that proposals automatically expire if the user changes the topic.

---

## Stage 4: Evaluation, Observability & Cryptographic Auditing

### What Was Built:
- Upgraded `DomainEvent` with monotonic sequence numbers and **SHA-256 cryptographic hash chaining** (`previous_event_hash`) for tamper-evident event sourcing.
- Built an offline, automated behavioral evaluation framework (`runner.py`) executing 15 canonical YAML scenarios.
- Implemented 8 deterministic Python judges (`BookingSafetyJudge`, `GroundingJudge`, `ConfirmationJudge`, `StaleActionJudge`, etc.) that inspect execution traces rather than fuzzy text.
- Built an operations console in React with turn latency waterfalls and a live domain events feed.

### Why This Stage Existed:
In machine learning, you cannot improve what you cannot measure. Relying on manual ad-hoc testing (*"I talked to the mic and it felt okay"*) is unacceptable for engineering systems. 

Stage 4 established repeatable evaluation. Instead of using expensive, non-deterministic cloud LLMs to grade our LLM, we wrote deterministic Python judges that verify whether database invariants were respected. The cryptographic hash chain ensured that every mutation left an indisputable, tamper-evident audit trail.

---

## Stage 5: Performance Engineering & Latency Optimization

### What Was Built:
- A standalone benchmark harness (`python -m proprelay.performance.benchmark --all`) running against a controlled 30-utterance synthetic leasing corpus.
- **Endpointing Delay Tuning (TDR-039)**: Reduced acoustic endpointing delay from 0.5s to 0.3s, slashing 447.2 ms off EOU commitment.
- **Speculative Generation (TDR-040)**: Preemptive prompt evaluation in Ollama during trailing speech silence, cutting effective TTFT to 16.98 ms p50.
- **Sentence-Boundary TTS Streaming (TDR-043)**: Synthesizing and streaming the first sentence chunk across WebRTC, delivering audible speech in 407.95 ms p50 (1,085 ms faster than full multi-sentence generation).
- **Safe Read-Only Catalog Caching (TDR-044)**: < 0.01 ms cache hits on static property queries while enforcing zero caching on volatile showing slots.

### Why This Stage Existed:
Our Stage 1 baseline turn latency was ~2.0 seconds. While functional, a 2-second pause feels sluggish in natural voice conversation. 

Rather than randomly guessing what to optimize, I systematically profiled each stage of the pipeline. Profiling revealed that audio chunking and endpointing were dominating the latency, not LLM token generation. By streaming TTS at the first sentence boundary and tuning the VAD endpointing window, we achieved a **28.2% total turn latency reduction** (down to 1,439.3 ms p50) on our reference hardware.

---

## Stage 6: Security Hardening, Release Engineering & Truthfulness Audit

### What Was Built:
- Automated claims scanner (`scripts/scan_claims.py`) and secrets scanner (`scripts/scan_secrets.py`) to eliminate ungrounded marketing claims and secret leaks.
- FastAPI security hardening: security headers middleware (CSP, nosniff, DENY), 64KB request body limits, and bounded regex input validation.
- WebRTC token hardening: strict zero-leeway token expiration (`leeway_seconds=0`) and room-scoped isolation.
- Expanded the behavioral evaluation suite to **25 scenarios** (adding adversarial prompt injections, impersonation attempts, and fake property grounding tests).
- Automated Release Gate (`scripts/release_gate.ps1`) executing 10 verification steps with fail-fast enforcement.

### Why This Stage Existed:
A project is not complete when it works on the happy path; it is complete when it is secure, robust against adversarial attacks, reproducible by external developers, and methodologically honest. 

Stage 6 conducted a thorough truthfulness audit: we corrected historical latency claims to match exact arithmetic (28.2%), disclosed dataset comparability differences openly, and built automated release gates so that any security flaw, typing error, or ungrounded claim immediately breaks the build.

---

## The Core Takeaway

PropRelay is the result of treating Voice AI as a **systems engineering challenge** rather than a prompt-engineering experiment. By decoupling language understanding from domain authorization, benchmarking acoustic bottlenecks empirically, and enforcing invariants through automated release gates, we created a voice agent that is deterministic, responsive, secure, and completely free to run.
