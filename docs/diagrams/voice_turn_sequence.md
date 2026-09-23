# Voice Turn Sequence Diagram

This sequence diagram depicts a complete voice turn cycle, showing the progression from microphone audio capture through acoustic endpointing, transcription, speculative prompt evaluation, deterministic tool execution, sentence-boundary TTS streaming, and audio playback.

```mermaid
sequenceDiagram
    autonumber
    actor User as User (Renter)
    participant Browser as Browser WebRTC Client
    participant LK as LiveKit SFU (127.0.0.1:7880)
    participant VAD as Silero VAD + TurnDetector
    participant STT as Faster-Whisper (CUDA float16)
    participant LLM as Ollama Qwen 2.5 (127.0.0.1:11434)
    participant Tools as AgentTools / Domain Policy
    participant TTS as Kokoro-82M TTS (127.0.0.1:8880)

    Note over User,Browser: Phase: Spoken Input
    User->>Browser: Speaks "Can you book the 2 PM slot for Alex Smith?"
    Browser->>LK: Streams Opus audio packets
    LK->>VAD: Pumps raw 16kHz PCM audio frames

    Note over VAD,STT: Phase: Endpointing & Speech Recognition
    VAD->>VAD: Detects speech onset & trailing silence
    VAD-->>STT: EOU Triggered (min_endpointing_delay=0.3s, ~485.2ms p50)
    STT->>STT: Transcribes audio buffer (~729.2ms p50 on 25-utterance corpus)
    STT->>LLM: Emits finalized transcript text

    Note over LLM,Tools: Phase: Intent Routing & Policy Execution
    rect rgb(240, 248, 255)
        Note right of LLM: Speculative prompt evaluation drops TTFT to ~16.98ms p50
        LLM->>LLM: Evaluates intent -> Selects tool 'book_showing'
        LLM->>Tools: Invokes book_showing(slot_id='slot-101-02', renter_name='Alex Smith', confirmed=False)
        Tools->>Tools: Two-Phase Confirmation Gate: confirmed=False
        Tools->>Tools: Stages PendingAction, emits booking.confirmation.requested
        Tools-->>LLM: ToolResult: "I have Modern Downtown Loft on Oct 1 at 2 PM for Alex Smith. Confirm?"
    end

    Note over LLM,TTS: Phase: Speech Synthesis & Streaming
    LLM->>TTS: Streams tokens: "I have Modern Downtown Loft at 2 PM for Alex Smith. Should I book that?"
    rect rgb(245, 255, 245)
        Note right of TTS: Sentence-Boundary Streaming (TDR-043)
        TTS->>TTS: Synthesizes Sentence 1 chunk (~407.95ms p50 TTFB)
        TTS->>LK: Streams 24kHz audio chunk directly to room audio track
        LK->>Browser: Delivers audio packet to WebRTC receiver
        Browser->>User: Audio playback starts (1,085ms earlier than full synthesis)
    end
    TTS->>TTS: Synthesizes Sentence 2 chunk in background while Sentence 1 plays

    Note over User,Browser: Interruption / Barge-in Path (If User Speaks During Playout)
    opt User Speaks During Agent Speech Playout
        User->>Browser: "Wait, stop, what was the rent again?"
        Browser->>LK: Audio frames sent
        LK->>VAD: VAD detects barge-in (> 0.3s speech onset)
        VAD-->>TTS: Sends cancellation signal
        TTS->>LK: Flushes in-flight audio buffer (< 100ms cut-through)
        VAD-->>Tools: Discards unconfirmed pending proposal
        Note over User,TTS: Agent transitions cleanly to LISTENING state
    end
```

## Measured Stage Latency Profile (Warm-Path Reference: NVIDIA RTX 5090)

| Turn Segment | Measured Mechanism | Baseline (ms) | Optimized p50 (ms) | Delta (ms) |
| :--- | :--- | :--- | :--- | :--- |
| **VAD / EOU Commitment** | Tuned endpointing (`min_delay=0.3s`) | 932.4 ms | **485.2 ms** | **-447.2 ms** |
| **Local STT (base.en CUDA)** | CTranslate2 float16 | 344.0 ms *(single clip)* | **729.2 ms** *(25 diverse fixtures)* | *Non-comparable datasets* |
| **LLM TTFT** | Speculative trailing evaluation | 75.5 ms | **16.98 ms** | **-58.5 ms** |
| **LLM Full Generation** | Resident Qwen 2.5 7B (136.4 tok/s) | 662.8 ms | **216.3 ms** | **-446.5 ms** |
| **Tool / Policy Execution** | SafeReadOnlyCache + sorted lock | 0.8 ms | **< 0.2 ms** | **-0.6 ms** |
| **TTS First Audio Chunk** | Sentence-boundary streaming | 727.5 ms | **407.95 ms** | **-319.6 ms** |
| **Total Conversational Turn** | End-of-utterance to first audio | **2,003.9 ms** | **1,439.3 ms** | **-564.6 ms (28.2% reduction)** |
