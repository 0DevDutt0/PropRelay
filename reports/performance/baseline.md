# PropRelay Phase 6 — Empirical Performance Baseline Report

**Execution Timestamp**: `2026-09-23T07:57:08.248671+00:00`  
**Benchmark Duration**: `115.83s`  
**Sample Count ($N$)**: `25 samples per stage`  

---

## 1. Hardware & Environment Profile

| Metric | Measured Value |
| :--- | :--- |
| **Operating System** | Windows 11 (Build 10.0.26200) |
| **Host CPU** | Intel(R) Core(TM) Ultra 9 275HX (24 logical cores) |
| **GPU Accelerator** | NVIDIA GeForce RTX 5090 Laptop GPU (Driver 592.01) |
| **Total VRAM** | 24463.0 MB (23.9 GB) |
| **Free VRAM (Baseline)** | 6946.0 MB |
| **Total System RAM** | 32189.0 MB |
| **Python Runtime** | Python 3.12.10 |
| **STT Engine** | faster-whisper (`base.en`, CTranslate2 CUDA float16) |
| **LLM Engine** | Ollama `qwen2.5:7b` (4-bit resident in VRAM) |
| **TTS Engine** | Kokoro-ONNX v1.0 (`af_alloy` voice, 24kHz) |

---

## 2. Subsystem Micro-Benchmark Distributions

All percentiles adhere strictly to the statistical sample-size guard ($N \ge 3$).

### A. Speech-to-Text (`faster-whisper base.en`)
- **Device**: `cuda` (`float16`)
- **Cold Model Initialization**: `1010.08 ms`
- **Mean Real-Time Factor (RTF)**: `0.483x` (processes 1s of audio in ~483ms)
- **Latency Distribution**:
  - **p50 (Median)**: `729.17 ms`
  - **p90**: `1493.26 ms`
  - **p95**: `1930.75 ms`
  - **Min / Max**: `81.21 ms / 2066.09 ms`

### B. Local LLM (`Ollama qwen2.5:7b`)
- **No-Tool Utterances**:
  - **TTFT p50**: `16.98 ms`
  - **Total Generation p50**: `216.29 ms`
  - **Tokens / Second**: `136.4 tok/s`
- **Tool-Calling Utterances**:
  - **TTFT p50**: `17.43 ms`
  - **Total Generation p50**: `216.55 ms`
  - **Tokens / Second**: `135.4 tok/s`

### C. Text-to-Speech (`Kokoro-ONNX af_alloy`)
- **Short Utterance p50**: `628.65 ms`
- **Medium Utterance p50**: `791.21 ms`
- **Multi-Sentence Full Audio p50**: `1492.06 ms`
- **Multi-Sentence First Chunk TTFB p50**: `407.95 ms`
- **Streaming Chunking TTFB Benefit**: **`1085.87 ms earlier first-audio delivery`**

### D. In-Memory Domain & Safe Cache
- **Property Lookup Uncached p50**: `0.0 ms`
- **Property Lookup Cached (`SafeReadOnlyCache`) p50**: `0.0 ms`
- **Search Uncached p50**: `0.0 ms`
- **Search Cached p50**: `0.0 ms`
- **Availability Lookup p50**: `0.0 ms` (Strictly un-cached for concurrency safety)
- **Cache Hit Ratio**: `100.0%`

### E. Event Journal Synchronous Persistence
- **Append + SHA-256 Hash Chaining p50**: `0.16 ms`
- **Cryptographic Audit Verification**: `5.24 ms` (Valid: `(True, [])`)
- **Mean Event JSON Payload**: `498.8 bytes` (Well within WebRTC MTU)
