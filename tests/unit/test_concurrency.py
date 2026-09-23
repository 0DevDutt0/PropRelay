"""Concurrency and race-condition tests verifying thread-safe slot booking.

CRITICAL GUARANTEE:
When N concurrent requests attempt to reserve the exact same showing slot simultaneously,
the deterministic domain locking mechanism guarantees that exactly ONE request succeeds
and N-1 requests are rejected with structured error codes.
"""

from __future__ import annotations

import asyncio

import pytest

from proprelay.domain.policy import (
    BookingPolicyService,
    BookingRequest,
    PolicyErrorCode,
    PolicyResult,
)


@pytest.mark.asyncio
async def test_concurrent_slot_booking_exactly_one_succeeds(
    booking_policy: BookingPolicyService,
) -> None:
    """N concurrent requests compete for the same slot behind an asyncio barrier.

    Expected: Exactly 1 success, N-1 rejections.
    """
    concurrency_count = 20
    target_slot_id = "slot-test-01"
    target_property_id = "test-prop-1"

    barrier = asyncio.Event()

    async def competitor(renter_index: int) -> PolicyResult:
        # Wait for all competitors to assemble at the barrier
        await barrier.wait()
        req = BookingRequest(
            property_id=target_property_id,
            slot_id=target_slot_id,
            renter_name=f"Concurrent_Renter_{renter_index}",
        )
        return await booking_policy.validate_and_reserve(req)

    # Launch competitors
    tasks = [asyncio.create_task(competitor(i)) for i in range(concurrency_count)]

    # Allow all tasks to yield and wait on the barrier
    await asyncio.sleep(0.01)

    # Release all concurrent requests simultaneously
    barrier.set()

    # Collect all outcomes
    results: list[PolicyResult] = await asyncio.gather(*tasks)

    successes = [r for r in results if r.success]
    failures = [r for r in results if not r.success]

    # Verify exact invariants
    assert len(successes) == 1, f"Expected exactly 1 success, got {len(successes)}"
    assert len(failures) == concurrency_count - 1, (
        f"Expected {concurrency_count - 1} failures, got {len(failures)}"
    )

    for fail in failures:
        assert fail.error_code == PolicyErrorCode.SLOT_UNAVAILABLE
