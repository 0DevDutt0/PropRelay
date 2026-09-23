"""PropRelay Performance Engineering, Voice Latency Optimization & Local Concurrency Suite."""

from __future__ import annotations

from proprelay.performance.cache import SafeReadOnlyCache
from proprelay.performance.concurrency import ConcurrencyHarness
from proprelay.performance.fixtures import BENCHMARK_UTTERANCES, BenchmarkUtterance
from proprelay.performance.profiler import (
    DomainAndEventProfiler,
    LLMProfiler,
    STTProfiler,
    TTSProfiler,
)
from proprelay.performance.stats import calculate_distribution_stats
from proprelay.performance.system_info import get_current_process_resources, get_system_telemetry

__all__ = [
    "BENCHMARK_UTTERANCES",
    "BenchmarkUtterance",
    "ConcurrencyHarness",
    "DomainAndEventProfiler",
    "LLMProfiler",
    "STTProfiler",
    "SafeReadOnlyCache",
    "TTSProfiler",
    "calculate_distribution_stats",
    "get_current_process_resources",
    "get_system_telemetry",
]
