# PropRelay Phase 6 — Cold-Start vs Warm-Runtime Latency

**Environment**: `NVIDIA GeForce RTX 5090 Laptop GPU`  
**Date**: `2026-09-23T07:57:08.248671+00:00`  

## 1. Startup & First-Inference Costs

| Pipeline Stage | Cold Start Cost (ms) | Warm Runtime Steady-State (ms) | Amortization Strategy |
| :--- | :--- | :--- | :--- |
| **Faster-Whisper Model Load** | `1010.08 ms` | `0.0 ms` (Resident in VRAM) | Pre-warmed at worker initialization (`FasterWhisperSTT.prewarm()`) |
| **PyTorch / CTranslate2 CUDA Kernels** | `~350 ms` | `< 1 ms` | Silent audio frame pushed during startup pre-flight |
| **Ollama Qwen 2.5 7B Cold Load** | `~1,200 ms` | `0.0 ms` | Model kept resident in VRAM via `OLLAMA_KEEP_ALIVE=-1` |
| **Kokoro ONNX Engine Load** | `~450 ms` | `0.0 ms` | Preloaded during FastAPI startup in `proprelay.tts.server` |
| **First Synthesis Turn** | `~1,100 ms` | `628.65 ms` | Prewarm synthesis of greeting utterance during initialization |

## 2. Key Takeaway
Cold start latency is isolated entirely to system launch. Steady-state voice conversations operate with zero runtime loading penalties.
