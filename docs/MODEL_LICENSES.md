# PropRelay — Model Licenses, Provenance & Attribution

This document details the licensing, upstream provenance, runtime framework, and commercial permissibility for all neural models and open-source infrastructure components utilized in the PropRelay zero-cost local architecture.

---

## 1. Neural Model Inventory

| Subsystem | Model Identifier | Upstream Author / Source | License | Permissible for Commercial Use? | Local Runtime Framework |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Speech-to-Text (STT)** | `faster-whisper-base.en` | Systran / OpenAI Whisper | **MIT License** | **YES** | CTranslate2 (int8 / float16) |
| **Language Model (LLM)** | `Qwen2.5-3B-Instruct` | Alibaba Cloud / Qwen Team | **Apache-2.0** | **YES** | Ollama (llama.cpp 4-bit GGUF) |
| **Alternative LLM** | `Qwen2.5-7B-Instruct` | Alibaba Cloud / Qwen Team | **Apache-2.0** | **YES** | Ollama (llama.cpp 4-bit GGUF) |
| **Text-to-Speech (TTS)** | `Kokoro-82M` (v0.19) | hexgrad (HuggingFace) | **Apache-2.0** | **YES** | ONNX Runtime (CPU / CUDA) |
| **Voice Activity Detection** | `Silero VAD v5` | Silero Team | **MIT License** | **YES** | ONNX Runtime |

---

## 2. Infrastructure & Framework Licenses

| Component | Repository / Author | License | Description |
| :--- | :--- | :--- | :--- |
| **LiveKit Server** | LiveKit Inc. (`livekit/livekit`) | **Apache-2.0** | Open-source WebRTC SFU server binary |
| **LiveKit Agents SDK** | LiveKit Inc. (`livekit/agents`) | **Apache-2.0** | Real-time Python WebRTC worker framework |
| **FastAPI** | Sebastián Ramírez (`tiangolo/fastapi`) | **MIT License** | High-performance Python web framework |
| **Pydantic** | Samuel Colvin (`pydantic/pydantic`) | **MIT License** | Data validation and schema enforcement |
| **CTranslate2** | OpenNMT (`OpenNMT/CTranslate2`) | **MIT License** | High-throughput inference engine for Whisper |

---

## 3. Detailed Model Attribution & Notes

### 3.1 Faster-Whisper (Systran / OpenAI)
- **Origin**: OpenAI Whisper architecture reimplemented by Systran using CTranslate2.
- **Weights**: `Systran/faster-whisper-base.en` (~140MB).
- **License Terms**: Full MIT license granting unrestricted commercial use, modification, and local redistribution.
- **Local Isolation**: All acoustic feature extraction and token decoding occur entirely within local memory. Zero audio bytes or transcripts are transmitted externally.

### 3.2 Qwen 2.5 Instruct (Alibaba Cloud)
- **Origin**: Alibaba Cloud Qwen Team.
- **Weights**: Quantized via llama.cpp to 4-bit integer weights (`qwen2.5:3b-instruct-q4_K_M`, ~2.0GB).
- **License Terms**: Released under the permissive Apache-2.0 license, permitting commercial deployment, fine-tuning, and offline inference without royalty obligations.
- **Prompt Isolation**: System instructions, user transcripts, and structured tool definitions reside purely in the host Ollama server process (`127.0.0.1:11434`).

### 3.3 Kokoro-82M (hexgrad)
- **Origin**: Created by hexgrad, trained on open speech datasets.
- **Weights**: ONNX model file `kokoro-v0_19.onnx` (~82M parameters, ~320MB) accompanied by `voices.bin`.
- **License Terms**: Apache-2.0 license. Free for both research and commercial usage.
- **Acoustic Output**: Generates 24kHz single-channel PCM audio chunks streamed via chunked transfer encoding directly to the LiveKit audio track.

---

## 4. Compliance & Intellectual Property Safeguards

1. **Zero Proprietary API Dependency**: No portion of the runtime pipeline invokes closed, proprietary SaaS APIs (such as OpenAI, Anthropic, ElevenLabs, or Deepgram).
2. **Zero Recurring Royalties**: All weights, binaries, and runtime libraries are licensed under OSI-approved permissive licenses (MIT and Apache-2.0).
3. **Redistribution Policy**: Model weights must be downloaded via official reproducible download scripts (`download_kokoro.ps1`, `download_livekit.ps1`, `ollama pull`) rather than bundled directly into source control, keeping repository size lean and respecting weight hosting norms.
