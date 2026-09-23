# PropRelay — Architecture & Sequence Diagrams Catalog

This directory contains the authoritative Mermaid-based architectural diagrams and sequence flows for PropRelay.

---

## Diagrams Index

| Diagram | Focus Area | Description |
| :--- | :--- | :--- |
| [**System Architecture**](file:///E:/work/Agentic%20Engineer%28Voice%20AI%29/PropRelay/docs/diagrams/system_architecture.md) | Component Topology | Complete end-to-end flow from browser WebRTC, local LiveKit SFU, agent runtime, local neural pipeline, deterministic domain services, and storage substrate. |
| [**Voice Turn Sequence**](file:///E:/work/Agentic%20Engineer%28Voice%20AI%29/PropRelay/docs/diagrams/voice_turn_sequence.md) | Realtime Turn Flow | Turn progression: Microphone -> VAD -> EOU -> STT -> Speculative LLM -> Tool Call -> Sentence-Boundary TTS Streaming -> WebRTC Playout, with barge-in interruption path and stage latencies. |
| [**Booking Safety Sequence**](file:///E:/work/Agentic%20Engineer%28Voice%20AI%29/PropRelay/docs/diagrams/booking_safety_sequence.md) | Safety & Confirmation | Two-phase confirmation protocol (`confirmed=False` staging -> user confirmation -> atomic commitment), highlighting rejection branches (fake property, occupied slot, stale proposal). |
| [**Event Sourcing Flow**](file:///E:/work/Agentic%20Engineer%28Voice%20AI%29/PropRelay/docs/diagrams/event_flow.md) | Auditability & Events | Durable-before-broadcast pattern, SHA-256 monotonic hash chaining, automated PII sanitization, WebRTC data channel delivery, and client-side deduplication. |

---

## Rendering Notes

All diagrams are written in standard GitHub-compatible [Mermaid](https://mermaid.js.org/) syntax and render natively in GitHub markdown previews and IDE Markdown previewers.
