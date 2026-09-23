# PropRelay — Technical Interview Cheat Sheet

A concise, high-signal reference sheet for technical interviews covering architectural decisions, concurrency guarantees, performance profiling, and safety invariants.

---

### Core Architecture & Technologies

#### Why LiveKit?
LiveKit provides an open-source, high-throughput WebRTC Selective Forwarding Unit (SFU) with native Python Agents SDK. It handles audio frame packetization, WebRTC peer connection renegotiation, jitter buffering, and sub-100ms bidirectional data channels out of the box, avoiding bespoke WebRTC C++ implementations.

#### Why WebRTC instead of WebSockets?
WebSockets use TCP, which suffers from head-of-line blocking under packet loss—unacceptable for real-time human conversation. WebRTC uses UDP with SRTP encryption, forward error correction (FEC), and Opus compression, enabling 20ms audio frame transport with minimal jitter and sub-100ms global latency.

#### Why local STT instead of cloud APIs?
Local STT eliminates recurring transcription costs ($0.006–$0.01/min), removes network hops (saving 150–300ms of internet latency), guarantees zero cloud audio leakage, and ensures full functionality in offline or air-gapped environments.

#### Why Faster-Whisper?
Faster-Whisper re-implements OpenAI Whisper in CTranslate2, delivering 4x faster inference and 2x lower memory than PyTorch. On our reference NVIDIA GPU, `base.en` in CUDA `float16` processes short speech utterances in as fast as 81ms with ~1.5 GB VRAM usage.

#### Why Ollama?
Ollama provides a lightweight local inference server with native support for llama.cpp 4-bit GGUF quantization, prompt evaluation caching, resident model persistence, and an OpenAI-compatible HTTP interface that integrates cleanly with `livekit-plugins-openai`.

#### Why Qwen 2.5?
Qwen 2.5 (3B and 7B Instruct) delivers state-of-the-art tool-calling accuracy, strict JSON schema conformance, and fast token generation speeds (136.4 tokens/second on reference hardware) within a compact 2.0–5.5 GB VRAM footprint.

#### Why Kokoro-82M?
Kokoro-82M provides near-commercial acoustic naturalness in a remarkably small 82-million parameter ONNX model (~320MB). It executes under ONNX Runtime with sub-second synthesis speeds and supports sentence-boundary streaming without GPU memory thrashing.

#### Why VAD (Voice Activity Detection)?
Silero VAD v5 detects speech presence on 30ms audio windows with high noise resilience, consuming < 1% CPU. It allows the system to determine speech boundaries, compute acoustic turn completions, and trigger instantaneous barge-in interruptions without waiting for cloud transcripts.

---

### Invariants, Policy & Concurrency

#### Why a deterministic policy layer?
Language models are probabilistic token predictors, not state machines. Letting an LLM directly execute database queries creates catastrophic vulnerabilities: hallucinations, double-bookings, unauthorized cancellations, and jailbreaks. In PropRelay, the LLM only interprets conversational intent; deterministic Python services (`BookingPolicyService`) validate every business rule.

#### Why confirmation before booking?
Reserving, rescheduling, or cancelling a property showing are consequential operations that commit real-world resources. PropRelay enforces a Two-Phase Confirmation Gate: `book_showing(confirmed=False)` stages a short-lived `PendingAction` in memory. No database state changes until the user explicitly confirms (*"Yes, book it"*).

#### How do you prevent hallucinated IDs from mutating state?
All tool executions resolve property and showing slot IDs against authoritative repositories. If an identifier does not exist in `listings.json` or `showings.json`, the tool fails fast with a structured error envelope (`PROPERTY_NOT_FOUND`, `SLOT_NOT_FOUND`), halting execution before state mutation.

#### How do you handle race conditions?
Domain repositories maintain per-slot mutexes (`asyncio.Lock`). When a booking request arrives, the lock for that specific slot is acquired. Availability is re-checked under the lock (double-checked locking). If a concurrent session booked it 0.1ms earlier, the second request fails with `SLOT_UNAVAILABLE`. Lock evaluation takes ~0.15ms.

#### How does rescheduling remain atomic?
Rescheduling requires mutating two showing slots simultaneously: releasing `slot_old` and reserving `slot_new`. To prevent deadlocks from circular waits, `BookingPolicyService` acquires mutex locks on both slots in **canonical sorted key order** (`sorted([slot_old, slot_new])`). Both mutations commit in a single transactional block; if `slot_new` is unavailable, `slot_old` is never released.

#### How are events persisted?
Domain mutations produce strongly-typed `DomainEvent` schemas persisted to an append-only JSONL journal (`data/events.jsonl`). PropRelay enforces a **durable-before-broadcast** invariant: events are flushed to disk before transmission over the WebRTC data channel, preventing client/server state divergence.

#### Why hash-chain the journal?
Each event payload incorporates the cryptographic SHA-256 hash of its predecessor (`previous_event_hash`) and a monotonic 64-bit sequence number. Any unauthorized line edit, deletion, or record insertion breaks the hash chain, enabling automated offline tamper detection via `EventJournal.verify_integrity()`.

---

### Evaluation, Latency & Reliability

#### How do you replay failures?
When an evaluation scenario fails, the runner dumps a structured JSON fixture to `reports/evaluation/failures/`. Developers can deterministically replay the exact scenario turn-by-turn with rich event and assertion tables using the Replay CLI:
```powershell
uv run python -m proprelay.evaluation.replay --scenario S04 -v
```

#### How did you benchmark latency?
Latency was profiled using an automated benchmark harness (`proprelay/performance/benchmark.py`) running against a controlled 30-utterance synthetic leasing corpus on reference hardware (NVIDIA RTX 5090 Laptop GPU, 24GB VRAM). Measurements capture turn timestamps directly from LiveKit agent event hooks.

#### What is actually measured?
- Total conversational turn p50: **1,439.3 ms** (down 28.2% from 2,003.9 ms baseline).
- Acoustic endpointing (EOU) delay: **485.2 ms** p50 (tuned `min_endpointing_delay=0.3s`).
- Speculative LLM TTFT: **16.98 ms** p50 (prompt evaluation during trailing silence).
- Kokoro TTS first-chunk streaming: **407.95 ms** p50 (sentence boundary streaming).
- Tool execution overhead: **< 0.2 ms**.

#### What is NOT measured?
- Cloud network latency (public internet transit, edge routing).
- Telephony PSTN / SIP trunk transport delays.
- Multi-region distributed database replication latency.
These numbers represent local hardware observations, not cloud SLA guarantees.

#### What happens during interruption (barge-in)?
When the user speaks while the agent is playing audio, Silero VAD detects speech onset within 200–300ms. The agent worker emits a cancellation token to Kokoro TTS, flushes the WebRTC playback track (sub-100ms cut-through), and clears any unconfirmed `PendingAction` staged during that turn.

#### What happens when the model produces a malicious tool request?
If a prompt injection tricks the model into calling `book_showing` with malicious arguments, the request hits the domain policy layer. If the slot is non-existent, occupied, in the past, or unconfirmed, the policy rejects it deterministically with structured error envelopes. The LLM has zero capability to bypass these checks.

---

### Scalability & Production Evolution

#### What are the system's current scalability limitations?
1. Single-machine GPU memory bounds: A single 24GB GPU accommodates 1 to 4 concurrent voice sessions comfortably; beyond 4, sequential inference queuing increases latency.
2. In-memory repository state: Current domain state lives in memory (with SQLite backing), which is node-local and not shared across horizontal worker nodes.
3. WebRTC browser only: Inbound PSTN telephony is not yet bridged.

#### How would you evolve this architecture for production?
- **Stage 2 (Single-Region Cloud)**: Deploy LiveKit on Kubernetes behind NLBs; move Faster-Whisper to a Triton Inference Server GPU pool; move Qwen 2.5 to vLLM with PagedAttention continuous batching; replace in-memory repositories with AWS Aurora PostgreSQL (`SELECT FOR UPDATE`) and Redis Cluster for distributed locks and session state.
- **Stage 3 (Global Edge)**: Deploy LiveKit Edge media relays for <30ms audio ingress; configure SIP trunking (Telnyx/Twilio) for PSTN calls; implement multi-region PostgreSQL read-replicas.

#### What would you change first at higher scale?
First: **Decouple audio workers from GPU inference**. In the current local prototype, the agent worker shares the GPU with Whisper and Qwen. In production, audio workers should be lightweight CPU pods that stream audio frames via gRPC to autoscaled Triton and vLLM inference clusters.
