# PropRelay — Technical Walkthrough for Hiring Managers & Recruiters

Welcome! This guide is designed for **Engineering Leaders, Staff/Principal Engineers, and Technical Hiring Managers** evaluating a candidate for an **Agentic Engineer / Real-Time Voice AI** role.

PropRelay was built to demonstrate that real-time Voice AI can be **deterministic, reliable, cost-free, and production-hardened**—moving far beyond trivial wrapper demos into disciplined systems engineering.

---

## 1. Executive Summary: Why This Project Is Different

Most voice AI demos string together paid cloud APIs (Twilio -> Deepgram -> OpenAI GPT-4o -> ElevenLabs) and claim success when happy paths work. In reality, such demos:
- Leak sensitive audio and transcripts to multiple third-party clouds.
- Incur steep per-minute usage bills ($0.15–$0.30/min).
- Hallucinate non-existent database entities or perform unintended state mutations upon ambiguous spoken input.
- Break down under user speech corrections, barge-in interruptions, and context switching.

**PropRelay takes the opposite approach:**
1. **$0.00 / month Recurring Cost**: Fully local, open-weights neural pipeline (CTranslate2 Faster-Whisper, Ollama Qwen 2.5, Kokoro-82M ONNX, LiveKit Server).
2. **Deterministic Business Policy Enforcement**: The language model is an intent router, *not* an authoritative state machine. All consequential actions (scheduling, rescheduling, cancelling) require a two-phase confirmation gate and repository validation.
3. **Rigorous Behavioral Evaluation (25 Scenarios)**: Evaluated like a mission-critical financial or medical system with specialized judges (Grounding, Booking Safety, Confirmation Safety, Stale Action Safety) and automated release gating.
4. **Technical Honesty & Provenance**: Latency claims are measured empirically, arithmetic is verified (28.2% total turn reduction), and test limitations are disclosed upfront.

---

## 2. Five-Minute Technical Evaluation

If you have five minutes to assess this candidate's engineering depth, run these four commands:

### 1. Inspect Local Subsystems & Hardware Acceleration
```powershell
uv run python -m proprelay.diagnostics
```
*What it demonstrates*: Clean environment introspection, CUDA detection, neural weight verification, and remediation guidance.

### 2. Run the Full Authoritative Release Gate
```powershell
.\scripts\release_gate.ps1
```
*What it demonstrates*: Rigorous release-gate pipeline combining linting (`ruff`), strict static typing (`mypy`), security analysis (`bandit`), technical claim scanning, secret scanning, unit invariant testing, 25 behavioral evaluation scenarios, and frontend compilation.

### 3. Deterministically Replay a Complex Behavioral Scenario
```powershell
uv run python -m proprelay.evaluation.replay --scenario S04 -v
```
*What it demonstrates*: Turn-by-turn tool execution, state machine transitions, event capture, and multi-judge assertion tables with severity ratings.

### 4. Test Adversarial Prompt Injection Defense
```powershell
uv run python -m proprelay.evaluation.replay --scenario S16
```
*What it demonstrates*: The candidate understands prompt injection defense and entity grounding: attempts to inject instructions or book nonexistent properties are safely rejected at the domain boundary.

---

## 3. Key Architecture & Code Tour

Where to look in the codebase to evaluate core engineering competencies:

| Candidate Competency | Key File / Location | What to Look For |
| :--- | :--- | :--- |
| **Agentic State Machines** | [`proprelay/workflows/state.py`](file:///E:/work/Agentic%20Engineer%28Voice%20AI%29/PropRelay/proprelay/workflows/state.py)<br>[`proprelay/workflows/context.py`](file:///E:/work/Agentic%20Engineer%28Voice%20AI%29/PropRelay/proprelay/workflows/context.py) | Clear separation of conversational state vs consequential `PendingAction`. Expiration tokens, turn counters, and reference resolution. |
| **Domain Policy & Invariants** | [`proprelay/domain/policy.py`](file:///E:/work/Agentic%20Engineer%28Voice%20AI%29/PropRelay/proprelay/domain/policy.py)<br>[`proprelay/agent/tools.py`](file:///E:/work/Agentic%20Engineer%28Voice%20AI%29/PropRelay/proprelay/agent/tools.py) | Deterministic two-phase booking gate, slot availability validation, idempotent reservation defense, and past-date rejection. |
| **Event Sourcing & Cryptography** | [`proprelay/events/schemas.py`](file:///E:/work/Agentic%20Engineer%28Voice%20AI%29/PropRelay/proprelay/events/schemas.py)<br>[`proprelay/events/journal.py`](file:///E:/work/Agentic%20Engineer%28Voice%20AI%29/PropRelay/proprelay/events/journal.py) | Strictly sequenced domain events with SHA-256 hash chaining and sequence gap detection. |
| **Security & Hardening** | [`proprelay/auth/tokens.py`](file:///E:/work/Agentic%20Engineer%28Voice%20AI%29/PropRelay/proprelay/auth/tokens.py)<br>[`proprelay/api/server.py`](file:///E:/work/Agentic%20Engineer%28Voice%20AI%29/PropRelay/proprelay/api/server.py) | Strict zero-leeway WebRTC token verification, room isolation, 64KB request body limits, security headers middleware, and input sanitization. |
| **Behavioral Evaluation** | [`proprelay/evaluation/judges.py`](file:///E:/work/Agentic%20Engineer%28Voice%20AI%29/PropRelay/proprelay/evaluation/judges.py)<br>[`proprelay/evaluation/runner.py`](file:///E:/work/Agentic%20Engineer%28Voice%20AI%29/PropRelay/proprelay/evaluation/runner.py) | Multi-judge evaluation suite with severity gating (`CRITICAL`, `MAJOR`, `MINOR`), failure fixture dumping, and release gate decision logic. |
| **Performance & Latency Engineering** | [`docs/LATENCY.md`](file:///E:/work/Agentic%20Engineer%28Voice%20AI%29/PropRelay/docs/LATENCY.md)<br>[`proprelay/performance/benchmark.py`](file:///E:/work/Agentic%20Engineer%28Voice%20AI%29/PropRelay/proprelay/performance/benchmark.py) | Methodologically sound turn timeline reconstruction, acoustic endpointing tuning, and concurrency contention modeling. |

---

## 4. Key Questions Answered by This Project

### *"How does this engineer handle LLM hallucinations?"*
The candidate does not rely on system prompts alone to prevent hallucinations. The architecture enforces **hard domain grounding**:
- Property IDs and Showing Slot IDs are validated against in-memory/database repositories. If an ID is invalid, the operation fails deterministically regardless of what the LLM generated.
- The language model cannot mutate booking state directly; it can only propose an action. An explicit confirmation step from the user is required before any database write occurs.

### *"How does this engineer handle real-time voice interruptions (barge-in)?"*
When the user speaks while the agent is responding, the Silero VAD detects speech onset. The agent worker immediately cancels the in-flight Kokoro TTS audio stream, flushes the WebRTC playback track, and clears any unconfirmed proposals staged during that turn.

### *"How does this engineer approach testing and code quality?"*
- **100% Type Coverage**: `mypy` strict mode enforced across all application and test code.
- **Architectural Invariants as Tests**: `tests/unit/test_architecture_invariants.py` continuously tests that domain services never import LiveKit, that models are never directly mutated, and that two-phase confirmation cannot be bypassed.
- **Failure Replayability**: Any failed evaluation scenario automatically dumps a replayable JSON fixture for deterministic debugging via `python -m proprelay.evaluation.replay`.

---

## 5. Candidate Contact & Discussion Points

Suggested discussion topics for technical interviews based on this codebase:
1. **Trade-offs of Local Inference vs Cloud APIs**: Latency vs VRAM constraints, cold-start characteristics, and quantization accuracy trade-offs.
2. **Evolution to Cloud Production**: Transitioning from single-machine SQLite/LiveKit to Kubernetes with Triton Inference Server, vLLM, Aurora PostgreSQL, and Redis (detailed in [PRODUCTION_EVOLUTION.md](file:///E:/work/Agentic%20Engineer%28Voice%20AI%29/PropRelay/docs/PRODUCTION_EVOLUTION.md)).
3. **Endpointing vs Interruption Sensitivity**: Balancing EOU commit delay against accidental user cutoffs.
