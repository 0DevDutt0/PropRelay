# PropRelay — Portfolio Website Copy & Project Assets

This document contains factual, copy-paste-ready engineering descriptions for personal portfolio websites, resume project sections, case study overviews, and GitHub profile cards.

---

## 1. Project Title
**PropRelay — Local-First Real-Time Property Voice Agent with Deterministic Action Safety**

---

## 2. One-Line Pitch
A 100% local, zero-recurring-cost real-time Voice AI agent for residential leasing—where the LLM handles conversational intent, but deterministic application policy gates all consequential state mutations.

---

## 3. 50-Word Description
PropRelay is an open-weights, local-first voice agent for property management built with LiveKit, Faster-Whisper, Ollama Qwen 2.5, and Kokoro TTS. It demonstrates low-latency acoustic pipeline engineering (1.44s warm p50) paired with strict architectural invariants: two-phase confirmation gates, deadlock-free sorted locking, SHA-256 event chaining, and zero cloud data leakage.

---

## 4. 150-Word Description
PropRelay demonstrates production-style Agentic Voice AI systems engineering by solving high-stakes property leasing workflows without third-party cloud APIs. Traditional voice bots often hallucinate data or execute unintended state changes. PropRelay solves this by treating the language model strictly as an untrusted intent router, requiring all reservations and cancellations to pass through deterministic application policy services and an application-level two-phase confirmation gate.

The acoustic pipeline streams audio over local WebRTC (LiveKit), transcribes via CUDA-accelerated Faster-Whisper, evaluates intent using a local Qwen 2.5 7B model, and streams speech chunks in 408ms using Kokoro-82M. Systematic profiling reduced total turn latency by 28.2% on reference hardware. Reliability is enforced through an offline behavioral evaluation suite of 25 canonical scenarios judged by deterministic trace checkers, cryptographic event journaling, and a 10-step automated release gate.

---

## 5. Technical Highlights
- **100% Zero-Cloud Architecture**: Runs entirely on consumer GPU hardware with open-weights models ($0/month recurring API bills).
- **Acoustic Turn Optimization**: 28.2% measured turn latency reduction (1,439.3ms warm p50) via sentence-boundary audio streaming and tuned 300ms endpointing.
- **Untrusted LLM Boundary**: Hard entity grounding against domain repositories; language models cannot invent properties or mutate schedules directly.
- **Two-Phase Action Confirmation**: State mutations stage a short-lived `PendingAction`; reservations require explicit verbal consent before commit.
- **Deadlock-Free Concurrency**: Mutex locks on multi-slot reschedules acquired in canonical sorted order (`sorted([slot_a, slot_b])`).
- **Cryptographic Event Journal**: Append-only JSONL event journal with SHA-256 monotonic hash chaining for automated tamper detection.
- **Automated Behavioral Evaluation**: 25 end-to-end scenarios evaluated by 8 deterministic Python judges with strict severity gating.

---

## 6. Architecture Summary
- **Transport**: Standalone self-hosted LiveKit SFU binary (`127.0.0.1:7880`) managing WebRTC Opus audio and data channels.
- **Audio & Neural Pipeline**:
  - Voice Activity Detection: Silero VAD v5 (ONNX Runtime)
  - Speech Recognition: Faster-Whisper `base.en` via CTranslate2 CUDA `float16`
  - Language Reasoning: Ollama `Qwen2.5-7B-Instruct` (4-bit GGUF)
  - Speech Synthesis: Kokoro-82M ONNX Runtime microservice (`127.0.0.1:8880`)
- **Domain Services**: Pure Python Pydantic v2 domain models, thread-safe repositories, and `BookingPolicyService` with zero WebRTC transport coupling.
- **Operations Frontend**: React 19 web application (TypeScript + Vite) with real-time waveform meters, state visualizers, and audit event streams.

---

## 7. Engineering Highlights
- **Preemptive Generation**: Ollama prompt evaluation begins during trailing speech silence, cutting effective TTFT to 16.98ms p50.
- **Sentence-Boundary Streaming**: Delivers first audio chunks in 407.95ms p50, playing speech 1,085ms earlier than full-response rendering.
- **Barge-in Interruption Handling**: Silero VAD detects user speech onset, triggering sub-100ms audio cancellation and unconfirmed proposal clearing.
- **Zero-Leeway Security**: Strict JWT verification (`leeway_seconds=0`), room-scoped permissions, 64KB request bounding, and security headers middleware.

---

## 8. Evaluation Summary
- **Evaluation Harness**: Offline behavioral runner (`proprelay/evaluation/runner.py`) executing against frozen fixtures with zero cloud leakage.
- **Scenario Suite**: 25 canonical YAML trajectories (covering discovery, booking, rescheduling, cancellations, prompt injections, and speech corrections).
- **Deterministic Judges**: 8 specialized execution-trace checkers evaluating grounding, consequential safety, confirmation compliance, and state transitions.
- **Results**: 25/25 scenarios passed (100% suite pass rate, 100% consequential safety, Release Gate: READY).

---

## 9. Performance Summary
Measured on reference workstation (NVIDIA GeForce RTX 5090 Laptop GPU, 24GB VRAM, AMD Ryzen 9 7945HX, Windows 11) across controlled synthetic leasing fixtures ($N = 25$):
- **Total Turn Latency**: Reduced from 2,003.9ms baseline to **1,439.3ms p50** (28.2% reduction).
- **Acoustic Endpointing Delay**: Reduced from 932.4ms to **485.2ms p50** (-447.2ms via 0.3s dynamic window).
- **TTS First-Chunk Delivery**: Synthesizes and delivers first sentence chunk in **407.95ms p50**.
- **LLM Token Velocity**: 136.4 tokens/second on resident local Qwen 2.5 7B.
- **Domain Tool Overhead**: < 0.2ms via read-only catalog caching and in-memory locks.

---

## 10. Limitations
- **Single-Machine Footprint**: Optimized for single-workstation local development; GPU memory supports 1 to 4 concurrent voice sessions.
- **Node-Local Storage**: Repositories operate in memory with SQLite backing rather than distributed relational databases.
- **WebRTC Ingress**: Operates via browser WebRTC; PSTN / SIP telephony trunks are not bridged in the local prototype.

---

## 11. Production Evolution
Designed to scale into cloud infrastructure without altering core domain business rules:
- **Stage 2 (Single-Region Cloud)**: LiveKit on Kubernetes behind NLBs; autoscaled GPU pools running Triton Whisper and vLLM; AWS Aurora PostgreSQL with row-level locks and Redis Cluster for distributed session state.
- **Stage 3 (Global Edge)**: LiveKit Edge media relays for <30ms audio ingress; multi-carrier SIP trunking (Telnyx/Twilio) for inbound telephone calls.

---

## 12. Short Descriptions for Web UI & GitHub

### GitHub Repository Description
Local-first, real-time property voice agent built with LiveKit, Faster-Whisper, Ollama Qwen 2.5, Kokoro TTS, and deterministic domain safety gates. $0 recurring cloud cost.

### Portfolio Card Description
A production-style real-time Voice AI system demonstrating low-latency acoustic streaming (1.44s p50), untrusted LLM boundaries, two-phase confirmation gates, and cryptographic event journaling.
