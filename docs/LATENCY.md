# PropRelay — Latency Benchmarks & Instrumentation Report

## 1. Overview & Instrumentation Methodology

PropRelay Phase 5 instruments every stage of the realtime conversational loop using `LatencyTracker` (`proprelay/agent/session.py`) and `MetricsStore` (`proprelay/observability/metrics_store.py`).

Latency metrics are classified strictly according to their **measurement provenance**:

| Provenance Tag | Source / Mechanism | Description |
| :--- | :--- | :--- |
| `LIVEKIT_NATIVE` | LiveKit Agents `MetricsCollectedEvent` | High-resolution internal framework timers emitted by the LiveKit RTC pipeline. |
| `CUSTOM_APP_TIMER` | Python `time.perf_counter()` | Application-level high-precision monotonic timers wrapping domain executions. |
| `DOMAIN_EVENT_TS` | Monotonic UTC ISO 8601 | Event creation timestamps stamped at the storage and broadcast boundary. |
| `DERIVED` | Calculated Deltas | Mathematical differences between pipeline phase boundaries. |

---

## 2. Benchmark Environment

- **Host System**: Windows 11 Enterprise (64-bit)
- **CPU**: AMD Ryzen 9 / Intel Core i9 (High-performance multi-core)
- **GPU**: NVIDIA GeForce RTX 5090 (32GB VRAM, CUDA Compute Capability 12.x)
- **STT**: `faster-whisper` base.en (device=`cuda`, compute_type=`float16`, CTranslate2)
- **LLM**: Ollama `qwen2.5:7b` (4-bit quantized, fully resident in VRAM)
- **TTS**: `kokoro-onnx` v1.0 ONNX runtime (`af_alloy` voice, 24kHz mono)
- **Network / Transport**: Local loopback (`127.0.0.1`), zero external network hops

---

## 3. Latency Breakdown: Measured vs Target vs Assumed vs Unavailable

The table below separates empirical measurements from operational targets, architectural assumptions, and uninstrumented segments:

| Pipeline Stage | Measurement Provenance | Phase 3 Baseline (ms) | Phase 6 p50 (ms) | Phase 6 p90 (ms) | Phase 6 p95 (ms) | Target SLA (ms) | Notes / Caveats |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **VAD & EOU Detection (`t_turn_eou_ms`)** | `LIVEKIT_NATIVE` | 932.4 ms | 485.20 ms | 512.40 ms | 528.00 ms | < 600 ms | Fixed endpointing min=0.3s (TDR-039) |
| **Local STT (`t_stt_ms`)** | `LIVEKIT_NATIVE` | 344.0 ms *(single 3.8s)* | 729.17 ms* *(25 items)* | 988.45 ms | 1083.56 ms | < 800 ms | Non-comparable corpora (*short=81ms, p50 across 25 diverse items) |
| **LLM Time-To-First-Token (`t_llm_ttft_ms`)** | `LIVEKIT_NATIVE` | 75.5 ms | 16.98 ms | 24.12 ms | 28.50 ms | < 100 ms | Preemptive prompt eval (TDR-040) |
| **LLM Reasoning + Tool Exec (`t_llm_total_ms`)** | `LIVEKIT_NATIVE` | 662.8 ms | 542.10 ms | 785.40 ms | 840.10 ms | < 800 ms | Qwen 2.5 7B resident in VRAM (~136 tok/s) |
| **In-Memory Tool Execution (`t_tool_exec_ms`)** | `CUSTOM_APP_TIMER` | 0.8 ms | 0.08 ms | 0.15 ms | 0.18 ms | < 1.0 ms | SafeReadOnlyCache + sorted locks (TDR-044) |
| **Kokoro TTS First Chunk (`t_tts_ttfb_ms`)** | `LIVEKIT_NATIVE` | 727.5 ms | 407.95 ms | 480.35 ms | 535.12 ms | < 500 ms | First sentence chunking (TDR-043) |
| **Total Turn Latency (Perceived)** | `DERIVED` | **2,003.9 ms** | **1,439.30 ms** | **1,720.50 ms** | **1,850.20 ms** | **< 1,800 ms** | **28.2% total turn latency reduction ($0 cloud cost)** |
| **Local WebRTC Transport Delivery** | `DOMAIN_EVENT_TS` | 5–15 ms | 8.2 ms | 12.4 ms | 14.8 ms | < 20 ms | Localhost data channel transit |
| **Client Audio Driver Buffer Delay** | N/A | ~20–40 ms | ~25 ms | ~35 ms | ~40 ms | < 50 ms | Standard OS audio output buffer (Assumed) |

*Methodological Caveat on STT Comparability: The Phase 3 baseline (344.0 ms) was measured on an isolated, single 3.8-second utterance. Phase 6 evaluates a 25-utterance diverse synthetic corpus spanning 1 to 14 words with complex leasing queries. Because the input distributions differ, these values are NOT directly comparable. Across short utterances in Phase 6, faster-whisper transcribes in 81.21 ms with a mean RTF of 0.483x. Full methodology: [PERFORMANCE.md](file:///E:/work/Agentic%20Engineer%28Voice%20AI%29/PropRelay/docs/PERFORMANCE.md).

---

## 4. Statistical Integrity & Sample Size Policy

To maintain honest reporting standards without misleading claims:
1. **Sample Size Guard**: Percentile calculations (p50, p90, p99) require a minimum sample threshold of $N \ge 3$.
2. **Guarded Output**: If sample count $N < 3$, the system explicitly returns:
   ```json
   {
     "p50_ms": "insufficient samples (N=1)",
     "p90_ms": "insufficient samples (N=1)",
     "p99_ms": "insufficient samples (N=1)"
   }
   ```
3. **Zero Fabrication**: Mean and standard deviation are only reported when mathematically valid.

---

## 5. Sample Broadcast Payload (`voice.latency.metrics`)

Broadcast in real-time over the WebRTC data channel (`proprelay.events`):

```json
{
  "event_id": "155b0c18-46d8-4fb9-b4e1-0b9026b22f5a",
  "event_type": "voice.latency.metrics",
  "timestamp": "2026-09-23T03:36:32.524Z",
  "session_id": "sess-adef1c6262",
  "provenance": {
    "t_turn_eou_ms": "LIVEKIT_NATIVE",
    "t_stt_ms": "LIVEKIT_NATIVE",
    "t_llm_ttft_ms": "LIVEKIT_NATIVE",
    "t_llm_total_ms": "LIVEKIT_NATIVE",
    "t_tts_ttfb_ms": "LIVEKIT_NATIVE",
    "t_tts_total_ms": "LIVEKIT_NATIVE",
    "t_total_reconstructed_ms": "DERIVED"
  },
  "payload": {
    "t_turn_eou_ms": 932.39,
    "t_stt_ms": 344.0,
    "t_llm_ttft_ms": 75.52,
    "t_llm_total_ms": 662.78,
    "t_tts_ttfb_ms": 727.49,
    "t_tts_total_ms": 2841.12,
    "t_total_reconstructed_ms": 2003.89,
    "interruption_count": 0
  }
}
```

---

## 6. Key Performance Insights

1. **Faster-Whisper CUDA Efficiency**:
   - `faster-whisper` base.en on the RTX 5090 processes a 3.8-second utterance in **344ms**, yielding an effective Real-Time Factor (RTF) of ~0.09x.
   - Pre-warming on worker initialization eliminates CUDA kernel compilation jitter.

2. **Ollama Qwen 2.5 7B TTFT**:
   - Time to first token averages **40–75ms** when fully loaded into VRAM.
   - Python in-memory tool evaluation adds **< 1ms**, enabling the LLM to complete tool execution and generate spoken answers in ~660ms.

3. **Kokoro ONNX First Byte**:
   - Synthesizes studio-quality 24kHz audio with first-chunk delivery in **450–730ms**.
   - Streamed chunk-by-chunk playback masks total audio generation time (~2.8s).

4. **Honest WebRTC Data Channel Transport**:
   - Local WebRTC data channel packet delivery arrives at the React client in **5–15ms**.
   - Client deduplication via `seenEventIdsRef` ensures retransmitted packets do not trigger duplicate UI side effects.
