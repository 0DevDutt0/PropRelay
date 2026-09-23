# System Architecture Diagram

This diagram documents the end-to-end component topology of PropRelay, from the browser WebRTC client through the local audio pipeline, agent runtime, deterministic domain services, and audit storage.

```mermaid
flowchart TD
    subgraph Client["Client Browser (React 19 + TypeScript + Vite)"]
        UI["Web UI / Operations Console"]
        Mic["Microphone Audio Stream (Opus)"]
        Speaker["Speaker Audio Playout"]
        DataChan["WebRTC Data Channel Receiver"]
    end

    subgraph Transport["WebRTC Transport Layer (Local)"]
        LK["LiveKit SFU Server (Port 7880)"]
        FastAPI["FastAPI Token & Health Server (Port 8000)"]
    end

    subgraph AgentRuntime["Voice Agent Worker (livekit-agents)"]
        VAD["Silero VAD (ONNX)"]
        TurnDet["Edge Turn Detector (EOU Tuned 0.3s)"]
        STT["Faster-Whisper STT (CTranslate2 CUDA float16)"]
        LLM["Ollama Qwen 2.5 7B (Port 11434)"]
        TTS["Kokoro-82M ONNX TTS (Port 8880, af_alloy)"]
        Session["VoiceSession Orchestrator"]
        VoiceTools["Voice Tools Bridge (@llm.function_tool)"]
    end

    subgraph WorkflowLayer["Conversational Workflow & Context"]
        Context["ConversationContext (Reference Resolution)"]
        State["WorkflowState Machine (Awaiting Confirmation)"]
        Gate["Two-Phase Confirmation Safety Gate"]
    end

    subgraph DomainLayer["Deterministic Domain & Policy Services"]
        AgentTools["AgentTools (Typed ToolResult Envelopes)"]
        Policy["BookingPolicyService (Deterministic Invariants)"]
        Clock["Clock Protocol (SystemClock / FrozenClock)"]
        Broadcaster["LiveKitEventBroadcaster"]
    end

    subgraph StorageLayer["Durable Storage & Cryptographic Journal"]
        Repos["In-Memory Thread-Safe Repositories (asyncio.Lock)"]
        Catalog["Catalog Seed Fixtures (listings.json, showings.json)"]
        Journal["DurableEventJournal (events.jsonl)"]
        HashChain["SHA-256 Monotonic Hash Chaining"]
    end

    %% Client and Transport Connections
    Mic -->|PCM Audio Track| LK
    LK -->|Audio Frames| Speaker
    LK <-->|Data Channel 'proprelay.events'| DataChan
    UI -->|HTTP /api/token, /api/health| FastAPI
    FastAPI -.->|JWT Dispenser| LK

    %% Transport and Agent Worker Connections
    LK <-->|Room Audio Subscription| Session
    Session --> VAD
    VAD --> TurnDet
    TurnDet --> STT
    STT --> LLM
    LLM --> VoiceTools
    VoiceTools --> AgentTools
    Session --> TTS
    TTS -->|Streaming Audio Chunks| LK

    %% Workflow and Policy Connections
    AgentTools <--> Context
    AgentTools <--> State
    AgentTools --> Gate
    Gate --> Policy
    Policy --> Repos
    Policy --> Clock
    Repos -.-> Catalog

    %% Event Path
    Policy --> Journal
    Journal --> HashChain
    Journal --> Broadcaster
    Broadcaster -->|WebRTC Data Channel| LK
```

## Architectural Highlights

1. **Untrusted Language Model Boundary**: The LLM interprets conversational intent and selects tool calls. It never directly mutates domain state, verifies schedules, or marks reservations confirmed.
2. **Zero Cloud Dependencies**: All inference (Faster-Whisper STT, Ollama LLM, Kokoro TTS, Silero VAD) runs 100% locally on localhost loopback.
3. **Durable-Before-Broadcast Event Sourcing**: Every state mutation is cryptographically appended to `events.jsonl` with SHA-256 hash chaining before being broadcast over the WebRTC data channel.
4. **Decoupled Architecture**: Domain services and repositories have zero imports of WebRTC or HTTP transport code, ensuring high testability and clean separation of concerns.
