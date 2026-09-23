# Event Sourcing & Realtime Delivery Flow

This diagram illustrates PropRelay's event-driven architecture, documenting how domain state mutations are cryptographically sealed, persisted to disk, and broadcast to the WebRTC client and operations console.

```mermaid
flowchart TD
    subgraph Trigger["1. Domain State Mutation"]
        Policy["BookingPolicyService"]
        Mutation["validate_and_reserve() / validate_and_reschedule()"]
        Policy --> Mutation
    end

    subgraph Journal["2. Durable Append-Only Event Journal"]
        EventFactory["DomainEvent Schema Factory\n(assign monotonic seq_num)"]
        PrevHash["Read Previous Record Hash (H_n-1)"]
        ComputeHash["Compute SHA-256 Hash:\nSHA256(seq || prev_hash || type || payload)"]
        PIIMask["Automated In-Memory PII Masking\n(mask phone: ***-***-1234, email: a***@...)"]
        AppendFile["Append-Only Write to data/events.jsonl\n(OS Flush / fsync)"]

        Mutation --> EventFactory
        EventFactory --> PrevHash
        PrevHash --> ComputeHash
        ComputeHash --> PIIMask
        PIIMask --> AppendFile
    end

    subgraph Reliability["3. Durable-Before-Broadcast Guarantee"]
        DiskCommitted{Disk Commit\nSuccessful?}
        AppendFile --> DiskCommitted
        DiskCommitted -- "Yes" --> Broadcaster["LiveKitEventBroadcaster"]
        DiskCommitted -- "No" --> Rollback["Abort & Raise StorageException\n(State not committed)"]
    end

    subgraph Delivery["4. Real-Time WebRTC Data Channel"]
        DataTrack["LiveKit WebRTC Data Channel\n(Topic: 'proprelay.events', Reliable Mode)"]
        Broadcaster -->|Deliver JSON Payload| DataTrack
    end

    subgraph ClientOps["5. Frontend Web Application & Operations Console"]
        Dedup["Client Event Deduplication Gate\n(Track seenEventIdsRef)"]
        UI_Feed["Live Domain Event Feed"]
        UI_Pill["Workflow State Pill\n(e.g., SHOWING_BOOKED)"]
        UI_Waterfall["Latency Waterfall Visualizer"]
        UI_Audit["Operations Audit Tab & Replay"]

        DataTrack --> Dedup
        Dedup --> UI_Feed
        Dedup --> UI_Pill
        Dedup --> UI_Waterfall
        Dedup --> UI_Audit
    end

    subgraph AuditEngine["6. Offline Integrity Verification Engine"]
        VerifyCLI["EventJournal.verify_integrity()\n(CLI: proprelay.events.journal)"]
        AppendFile -.->|Verify Monotonic Sequence & Hashes| VerifyCLI
        VerifyCLI --> CleanReport["Journal Integrity: 100% Intact\nZero Tampering / Zero Gaps"]
    end
```

## Architectural Invariants Enforced in the Event Path

1. **Durable-Before-Broadcast**: Events are written to the local disk journal before transmission over the WebRTC data channel. If disk persistence fails, no event is broadcast, preventing phantom state divergence.
2. **Cryptographic Tamper-Evidence**: Each event includes `sequence_number`, `timestamp`, `event_type`, `payload`, and `previous_event_hash`. A cryptographic SHA-256 hash chains each record to its predecessor. Any modification or deletion of past events breaks the verification chain.
3. **Automated PII Sanitization**: Contact information (such as telephone numbers and email addresses) undergoes automated masking prior to disk write and network broadcast, protecting prospective renter privacy.
4. **Client-Side Deduplication**: The React client maintains an in-memory set of processed event IDs (`seenEventIdsRef`) to prevent duplicate UI rendering in the event of WebRTC transport retries.
