"""Performance regression smoke tests verifying latency thresholds and concurrency safety."""

from __future__ import annotations

import datetime
import os
import tempfile
import time

import pytest

from proprelay.domain.repositories import InMemoryPropertyRepository
from proprelay.events.journal import EventJournal
from proprelay.events.schemas import DomainEvent, EventType
from proprelay.performance.cache import SafeReadOnlyCache
from proprelay.performance.concurrency import ConcurrencyHarness
from proprelay.performance.stats import calculate_distribution_stats


@pytest.mark.asyncio
async def test_domain_lookup_and_cache_latency_smoke() -> None:
    """Ensure in-memory catalog lookups and caching execute well within voice SLAs (< 25ms)."""
    repo = InMemoryPropertyRepository.from_json_file("data/listings.json")
    cache = SafeReadOnlyCache()

    # 1. Direct repository lookup
    t0 = time.perf_counter()
    prop = await repo.get_by_id("prop-101")
    repo_latency_ms = (time.perf_counter() - t0) * 1000

    assert prop is not None
    assert repo_latency_ms < 25.0, f"Repository lookup too slow: {repo_latency_ms:.2f}ms"

    # 2. Cached lookup
    cache.put_property("prop-101", prop)
    t0 = time.perf_counter()
    cached_prop = cache.get_property("prop-101")
    cache_latency_ms = (time.perf_counter() - t0) * 1000

    assert cached_prop is not None
    assert cache_latency_ms < 5.0, f"Cache lookup too slow: {cache_latency_ms:.2f}ms"
    assert cache.hits == 1


@pytest.mark.asyncio
async def test_search_and_filter_latency_smoke() -> None:
    """Ensure in-memory property search executes within broad threshold (< 30ms)."""
    repo = InMemoryPropertyRepository.from_json_file("data/listings.json")

    t0 = time.perf_counter()
    results = await repo.search(max_rent=3500, bedrooms=2)
    search_latency_ms = (time.perf_counter() - t0) * 1000

    assert len(results) > 0
    assert search_latency_ms < 30.0, f"Property search too slow: {search_latency_ms:.2f}ms"


@pytest.mark.asyncio
async def test_event_journal_append_latency_smoke() -> None:
    """Ensure EventJournal SHA-256 chaining and file append execute within SLA (< 50ms)."""
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as tmp:
        path = tmp.name

    try:
        journal = EventJournal(file_path=path)
        ev = DomainEvent(
            event_type=EventType.PROPERTY_DETAILS_VIEWED.value,
            timestamp=datetime.datetime.now(datetime.UTC),
            session_id="sess-smoke",
            workflow_id="wf-smoke",
            turn_id="1",
            payload={"property_id": "prop-101"},
        )

        t0 = time.perf_counter()
        appended = await journal.append(ev)
        append_latency_ms = (time.perf_counter() - t0) * 1000

        assert appended.sequence_number == 1
        assert appended.event_hash is not None
        assert append_latency_ms < 50.0, f"Journal append too slow: {append_latency_ms:.2f}ms"

        # Verify integrity check
        t0 = time.perf_counter()
        valid, errors = journal.verify_integrity()
        verify_latency_ms = (time.perf_counter() - t0) * 1000

        assert valid is True
        assert len(errors) == 0
        assert verify_latency_ms < 100.0, f"Integrity check too slow: {verify_latency_ms:.2f}ms"
    finally:
        if os.path.exists(path):
            os.remove(path)


@pytest.mark.asyncio
async def test_concurrent_booking_race_safety_smoke() -> None:
    """Ensure atomic mutual exclusion prevents double bookings during concurrent races."""
    harness = ConcurrencyHarness()
    result = await harness.verify_concurrent_booking_safety()

    assert result["race_test_passed"] is True
    assert result["successful_bookings"] == 1
    assert result["rejected_bookings"] == 1
    assert result["execution_duration_ms"] < 100.0


def test_percentile_sample_size_guard() -> None:
    """Ensure calculate_distribution_stats guards against fabricated percentiles when N < 3."""
    res_single = calculate_distribution_stats([100.0])
    assert "insufficient samples" in str(res_single["p50_ms"])
    assert "insufficient samples" in str(res_single["p95_ms"])

    res_adequate = calculate_distribution_stats([10.0, 20.0, 30.0, 40.0, 50.0])
    assert res_adequate["p50_ms"] == 30.0
    assert "insufficient samples for p95" in str(res_adequate["p95_ms"])
