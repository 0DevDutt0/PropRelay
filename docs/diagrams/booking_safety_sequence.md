# Booking Safety & Invariant Sequence Diagram

This sequence diagram illustrates PropRelay's deterministic safety architecture governing consequential actions. It contrasts natural language interpretation against authoritative domain enforcement and highlights rejection branches.

```mermaid
sequenceDiagram
    autonumber
    actor User as User (Spoken Voice)
    participant LLM as Language Model (Intent Router)
    participant Tools as AgentTools Bridge
    participant Context as ConversationContext
    participant Policy as BookingPolicyService
    participant Repos as Domain Repositories (asyncio.Lock)
    participant Journal as DurableEventJournal

    %% 1. Discovery Phase
    Note over User,Repos: Phase 1: Property Discovery & Selection
    User->>LLM: "Find 2-bedroom lofts in Downtown under $3000"
    LLM->>Tools: search_properties(neighborhood="Downtown", max_price=3000, bedrooms=2)
    Tools->>Repos: Query PropertyRepository (SafeReadOnlyCache hit < 0.01ms)
    Repos-->>Tools: Returns [prop-101: Modern Downtown Loft, $2850]
    Tools->>Context: Store active candidates [prop-101]
    Tools-->>LLM: "Found Modern Downtown Loft for $2,850/mo."
    LLM-->>User: Spoken voice response

    %% 2. Availability Phase
    Note over User,Repos: Phase 2: Availability Lookup & Reference Resolution
    User->>LLM: "What showings are available for the first one today?"
    LLM->>Tools: get_available_showings(property_id="the first one", date="today")
    Tools->>Context: Resolve ordinal "first one" -> prop-101
    Tools->>Context: Normalize date "today" anchored to Clock -> 2026-10-01
    Tools->>Repos: Query ShowingRepository for prop-101 on 2026-10-01
    Repos-->>Tools: Returns [slot-101-01: 10:00 AM, slot-101-02: 01:00 PM, slot-101-03: BOOKED]
    Tools-->>LLM: Active slots: 10:00 AM, 1:00 PM (3:30 PM is booked)
    LLM-->>User: "Openings at 10:00 AM and 1:00 PM. Which works?"

    %% 3. Proposal Phase (Two-Phase Gate: confirmed=False)
    Note over User,Journal: Phase 3: Action Staging (Two-Phase Confirmation Gate)
    User->>LLM: "Book the 1 PM slot for Alex Smith"
    LLM->>Tools: book_showing(slot_id="slot-101-02", renter_name="Alex Smith", confirmed=False)
    
    alt Happy Path: Staging Proposal
        Tools->>Policy: Check slot validity & availability
        Policy->>Repos: Verify slot-101-02 status == AVAILABLE
        Repos-->>Policy: Valid
        Tools->>Context: Stage PendingAction(type=BOOK_SHOWING, slot_id=slot-101-02, name="Alex Smith")
        Tools->>Journal: Emit booking.confirmation.requested
        Tools-->>LLM: Staged. Ask user: "I have Modern Downtown Loft at 1:00 PM for Alex Smith. Should I book?"
        LLM-->>User: Spoken confirmation prompt
    else Rejection Branch: Occupied Slot (e.g. 3:30 PM)
        User->>LLM: "Book the 3:30 PM slot instead"
        LLM->>Tools: book_showing(slot_id="slot-101-03", renter_name="Alex", confirmed=False)
        Tools->>Policy: Check slot-101-03
        Policy-->>Tools: Rejected: SLOT_UNAVAILABLE
        Tools-->>LLM: Error: Slot is already booked
        LLM-->>User: "That slot is no longer available. Would you like 10:00 AM instead?"
    else Rejection Branch: Fake Property ID / Un-grounded Entity
        LLM->>Tools: book_showing(slot_id="slot-999-fake", renter_name="Attacker", confirmed=False)
        Tools->>Policy: Validate slot existence
        Policy-->>Tools: Rejected: SLOT_NOT_FOUND (Grounding failure)
        Tools-->>LLM: Error: Unknown showing slot
        LLM-->>User: "I cannot find that showing slot."
    end

    %% 4. Confirmation & Execution Phase
    Note over User,Journal: Phase 4: Deterministic Commitment
    alt User Confirms Explicitly ("Yes, confirm it")
        User->>LLM: "Yes, please confirm that reservation"
        LLM->>Tools: confirm_pending_action()
        Tools->>Context: Retrieve & validate PendingAction (check TTL & topic)
        Tools->>Policy: validate_and_reserve(slot_id=slot-101-02, renter_name="Alex Smith")
        rect rgb(230, 255, 230)
            Policy->>Repos: Acquire slot mutex lock (0.15ms)
            Policy->>Repos: Double-check slot is still AVAILABLE (idempotency check)
            Policy->>Repos: Mutate status -> BOOKED, create Booking entity
            Policy->>Repos: Release slot mutex lock
            Policy->>Journal: Append showing.booked (SHA-256 chained, seq #N)
            Journal-->>Tools: Confirmed booking_id="bk-101"
            Tools->>Context: Clear PendingAction, set WorkflowState -> SHOWING_BOOKED
        end
        Tools-->>LLM: Success: Reservation bk-101 confirmed
        LLM-->>User: "Your reservation is confirmed! Code is bk-101."
    else Stale Context Invalidation Branch (User switches topic)
        User->>LLM: "Actually, tell me about the Belmont Studio instead"
        LLM->>Tools: get_property_details(property_id="prop-105")
        Tools->>Context: Invalidate pending action (property switch detected)
        Tools->>Journal: Emit stale.action.invalidated
        Tools-->>LLM: Proposal cleared. Returns prop-105 details.
        LLM-->>User: "Belmont Studio is $1,400/mo. Staged booking for Downtown Loft cancelled."
    else User Declines ("No, don't book that")
        User->>LLM: "No, never mind"
        LLM->>Tools: cancel_pending_action()
        Tools->>Context: Clear PendingAction
        Tools-->>LLM: Staged action discarded without mutation
        LLM-->>User: "Okay, I've discarded that booking request."
    end
```

## Security Invariant Guarantees

1. **Zero Direct LLM Mutation**: The LLM has zero database access handles. All mutations require passing through `BookingPolicyService`.
2. **Mandatory Confirmation Protocol**: Calling `book_showing` with `confirmed=False` never commits a booking; it only stages a short-lived `PendingAction`. Calling `confirm_pending_action()` fails if no proposal was staged or if context switched.
3. **Hardware-Anchored Grounding**: Fabricated IDs (`prop-999`, `slot-fake`) return deterministic error envelopes (`PROPERTY_NOT_FOUND`, `SLOT_NOT_FOUND`) with zero state changes.
4. **Sorted Lock Concurrency**: Simultaneous booking or rescheduling requests acquire locks in canonical sorted key order (`sorted([slot_a, slot_b])`), eliminating database deadlocks and double-booking races.
