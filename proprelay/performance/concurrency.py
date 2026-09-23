"""Local concurrency benchmark harness and booking collision race safety verification."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from proprelay.domain.clock import SystemClock
from proprelay.domain.policy import (
    BookingPolicyService,
    BookingRequest,
    PolicyErrorCode,
)
from proprelay.domain.repositories import (
    InMemoryBookingRepository,
    InMemoryPropertyRepository,
    InMemoryShowingRepository,
)
from proprelay.performance.fixtures import BENCHMARK_UTTERANCES
from proprelay.performance.stats import calculate_distribution_stats
from proprelay.performance.system_info import get_current_process_resources


class ConcurrencyHarness:
    """Evaluates local concurrency performance and transactional safety under concurrent workloads."""

    def __init__(self) -> None:
        self.clock = SystemClock()

    async def verify_concurrent_booking_safety(self) -> dict[str, Any]:
        """Verify that concurrent booking attempts on the identical slot enforce strict mutual exclusion.

        CRITICAL SAFETY RULE (TDR-045):
        When Session A and Session B race to reserve the same slot concurrently:
        - Exactly ONE session MUST succeed.
        - Exactly ONE session MUST be rejected with SLOT_UNAVAILABLE.
        - Zero double-bookings may occur.
        """
        prop_repo = InMemoryPropertyRepository.from_json_file("data/listings.json")
        showing_repo = InMemoryShowingRepository.from_json_file("data/showings.json")
        booking_repo = InMemoryBookingRepository()
        policy = BookingPolicyService(
            property_repo=prop_repo,
            showing_repo=showing_repo,
            booking_repo=booking_repo,
            clock=self.clock,
        )

        slots = await showing_repo.list_by_property("prop-101", available_only=True)
        if not slots:
            raise RuntimeError("No available slots found for prop-101 in fixtures.")
        target_slot = slots[0]

        req_a = BookingRequest(
            property_id="prop-101",
            slot_id=target_slot.slot_id,
            renter_name="Renter Alice",
            renter_phone="+1-555-111-2222",
            renter_email="alice@example.com",
        )
        req_b = BookingRequest(
            property_id="prop-101",
            slot_id=target_slot.slot_id,
            renter_name="Renter Bob",
            renter_phone="+1-555-333-4444",
            renter_email="bob@example.com",
        )

        # Launch concurrent bookings simultaneously
        t0 = time.perf_counter()
        res_a, res_b = await asyncio.gather(
            policy.validate_and_reserve(req_a),
            policy.validate_and_reserve(req_b),
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000
        results = [res_a, res_b]

        successes = [r for r in results if r.success]
        failures = [r for r in results if not r.success]

        is_safe = (
            len(successes) == 1
            and len(failures) == 1
            and failures[0].error_code == PolicyErrorCode.SLOT_UNAVAILABLE
        )

        return {
            "race_test_passed": is_safe,
            "total_attempts": 2,
            "successful_bookings": len(successes),
            "rejected_bookings": len(failures),
            "rejection_code": failures[0].error_code if failures else None,
            "execution_duration_ms": round(elapsed_ms, 2),
            "target_slot_id": target_slot.slot_id,
        }

    async def _execute_session_turns(
        self,
        session_idx: int,
        turns_per_session: int,
        prop_repo: InMemoryPropertyRepository,
        showing_repo: InMemoryShowingRepository,
        session_turn_times: list[float],
        errors_list: list[int],
    ) -> None:
        """Run simulated voice turns for one session."""
        for turn_idx in range(turns_per_session):
            utt = BENCHMARK_UTTERANCES[
                (session_idx * turns_per_session + turn_idx) % len(BENCHMARK_UTTERANCES)
            ]
            t0 = time.perf_counter()
            try:
                if utt.has_tool:
                    _ = await prop_repo.search(max_rent=3000, bedrooms=2)
                    _ = await showing_repo.list_by_property("prop-101", available_only=True)
                await asyncio.sleep(0.05)
                session_turn_times.append((time.perf_counter() - t0) * 1000)
            except Exception:
                errors_list.append(1)

    async def benchmark_concurrency_scaling(
        self,
        session_levels: list[int] | None = None,
        turns_per_session: int = 5,
    ) -> dict[str, Any]:
        """Measure latency, throughput, and hardware utilization across 1, 2, and 4 concurrent sessions."""
        if session_levels is None:
            session_levels = [1, 2, 4]

        report: dict[str, Any] = {
            "experiment_type": "single-machine local experiment",
            "caveat": "These measurements reflect local RTX 5090 hardware limits and are NOT production cloud SLA claims.",
            "levels": {},
        }

        prop_repo = InMemoryPropertyRepository.from_json_file("data/listings.json")
        showing_repo = InMemoryShowingRepository.from_json_file("data/showings.json")

        for num_sessions in session_levels:
            session_turn_times: list[float] = []
            errors_list: list[int] = []

            t_level_start = time.perf_counter()
            initial_resources = get_current_process_resources()

            # Run sessions concurrently
            tasks = [
                self._execute_session_turns(
                    i,
                    turns_per_session,
                    prop_repo,
                    showing_repo,
                    session_turn_times,
                    errors_list,
                )
                for i in range(num_sessions)
            ]
            await asyncio.gather(*tasks)

            total_duration_s = time.perf_counter() - t_level_start
            peak_resources = get_current_process_resources()

            stats = calculate_distribution_stats(session_turn_times)

            errors_count = len(errors_list)
            report["levels"][f"{num_sessions}_sessions"] = {
                "active_sessions": num_sessions,
                "total_turns_completed": len(session_turn_times),
                "total_duration_seconds": round(total_duration_s, 2),
                "errors_count": errors_count,
                "success_rate_percent": round(
                    ((len(session_turn_times) - errors_count) / max(1, len(session_turn_times)))
                    * 100,
                    1,
                ),
                "turn_latency_ms": stats,
                "resources": {
                    "initial": initial_resources,
                    "peak": peak_resources,
                },
            }

        return report
