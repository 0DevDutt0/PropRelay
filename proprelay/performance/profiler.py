"""Subsystem micro-profilers and measurement engines for PropRelay Phase 6."""

from __future__ import annotations

import contextlib
import datetime
import logging
import os
import tempfile
import time
from typing import Any, cast

import httpx
import numpy as np

from proprelay.agent.prompts import (
    CONCISE_AGENT_INSTRUCTIONS,
    DEFAULT_AGENT_INSTRUCTIONS,
)
from proprelay.domain.clock import Clock, SystemClock
from proprelay.domain.policy import BookingPolicyService, BookingRequest
from proprelay.domain.repositories import (
    InMemoryBookingRepository,
    InMemoryPropertyRepository,
    InMemoryShowingRepository,
)
from proprelay.events.journal import EventJournal
from proprelay.events.schemas import DomainEvent, EventType
from proprelay.performance.cache import SafeReadOnlyCache
from proprelay.performance.fixtures import BENCHMARK_UTTERANCES, generate_synthetic_audio_tensor
from proprelay.performance.stats import calculate_distribution_stats
from proprelay.stt.faster_whisper import FasterWhisperSTT

logger = logging.getLogger(__name__)


class STTProfiler:
    """Measures faster-whisper STT latency, RTF, compute types, and audio preprocessing."""

    def __init__(self, device: str = "cuda") -> None:
        self.device = device

    async def benchmark_audio_preprocessing(self, iterations: int = 50) -> dict[str, Any]:
        """Profile cost of audio buffer conversion and sample rate resampling."""
        from livekit import rtc

        # Create dummy 48kHz 2-channel audio frame
        sample_rate = 48000
        duration_s = 3.0
        num_samples = int(sample_rate * duration_s)
        dummy_pcm = (np.sin(np.linspace(0, 100, num_samples)) * 10000).astype(np.int16)
        stereo_pcm = np.column_stack([dummy_pcm, dummy_pcm]).tobytes()

        # Benchmark 1: Resampling from 48k to 16k
        resample_times: list[float] = []
        resampler = rtc.AudioResampler(input_rate=48000, output_rate=16000, num_channels=1)

        frame = rtc.AudioFrame(
            data=stereo_pcm,
            sample_rate=48000,
            num_channels=2,
            samples_per_channel=num_samples,
        )

        for _ in range(iterations):
            t0 = time.perf_counter()
            _ = resampler.push(frame)
            resample_times.append((time.perf_counter() - t0) * 1000)

        # Benchmark 2: PCM int16 to float32 normalization
        conv_times: list[float] = []
        raw_int16 = dummy_pcm.tobytes()
        for _ in range(iterations):
            t0 = time.perf_counter()
            data_arr = np.frombuffer(raw_int16, dtype=np.int16)
            _ = (data_arr.astype(np.float32) / 32768.0).astype(np.float32)
            conv_times.append((time.perf_counter() - t0) * 1000)

        return {
            "resampling_48k_to_16k_ms": calculate_distribution_stats(resample_times),
            "pcm16_to_float32_conversion_ms": calculate_distribution_stats(conv_times),
        }

    async def benchmark_transcription(
        self,
        model_name: str = "base.en",
        compute_type: str = "float16",
        sample_count: int = 25,
        warmup_count: int = 3,
    ) -> dict[str, Any]:
        """Benchmark STT latency and Real-Time Factor (RTF) across synthetic audio fixtures."""
        stt_instance = FasterWhisperSTT(
            model=model_name,
            device=self.device,
            compute_type=compute_type,
        )

        # Cold start measurement (model load + first inference)
        t_cold_start_begin = time.perf_counter()
        model_obj = cast(Any, stt_instance._ensure_model())
        t_model_load_ms = (time.perf_counter() - t_cold_start_begin) * 1000

        # Generate audio samples from fixtures
        test_samples = [
            (u.text, generate_synthetic_audio_tensor(u.text, sample_rate=16000))
            for u in BENCHMARK_UTTERANCES[:sample_count]
        ]

        # Warm-up iterations
        for i in range(min(warmup_count, len(test_samples))):
            _, audio = test_samples[i]
            model_obj.transcribe(audio, language="en", beam_size=1)

        # Warm benchmark iterations
        latencies_ms: list[float] = []
        rtf_values: list[float] = []

        for _, audio in test_samples:
            audio_duration_s = len(audio) / 16000.0
            t0 = time.perf_counter()
            segments, _info = model_obj.transcribe(audio, language="en", beam_size=1)
            _ = list(segments)
            elapsed_s = time.perf_counter() - t0
            latencies_ms.append(elapsed_s * 1000)
            rtf_values.append(elapsed_s / max(0.01, audio_duration_s))

        return {
            "model": model_name,
            "compute_type": compute_type,
            "device": self.device,
            "cold_load_time_ms": round(t_model_load_ms, 2),
            "sample_count": len(latencies_ms),
            "latency_ms": calculate_distribution_stats(latencies_ms),
            "real_time_factor": {
                "mean": round(float(np.mean(rtf_values)), 3),
                "min": round(float(np.min(rtf_values)), 3),
                "max": round(float(np.max(rtf_values)), 3),
            },
        }


class LLMProfiler:
    """Measures Ollama Qwen 2.5 7B TTFT, prompt eval, tokens/sec, context size, and response brevity."""

    def __init__(
        self,
        model: str = "qwen2.5:7b",
        base_url: str = "http://127.0.0.1:11434",
    ) -> None:
        self.model = model
        self.base_url = base_url

    async def benchmark_llm_inference(
        self,
        iterations: int = 25,
        warmup_iterations: int = 3,
    ) -> dict[str, Any]:
        """Profile TTFT, prompt eval, and generation throughput on Ollama."""
        ttft_no_tool_ms: list[float] = []
        total_no_tool_ms: list[float] = []
        tokens_per_sec_no_tool: list[float] = []

        ttft_tool_ms: list[float] = []
        total_tool_ms: list[float] = []
        tokens_per_sec_tool: list[float] = []

        async with httpx.AsyncClient(timeout=30.0) as client:
            # 1. Warm-up
            for _ in range(warmup_iterations):
                await client.post(
                    f"{self.base_url}/api/chat",
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": "You are a concise voice assistant."},
                            {"role": "user", "content": "Hi, I am looking for an apartment."},
                        ],
                        "stream": False,
                    },
                )

            # 2. Benchmark No-Tool Utterances
            no_tool_prompts = [u.text for u in BENCHMARK_UTTERANCES if not u.has_tool][:iterations]
            for prompt_text in no_tool_prompts:
                t0 = time.perf_counter()
                res = await client.post(
                    f"{self.base_url}/api/chat",
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": CONCISE_AGENT_INSTRUCTIONS},
                            {"role": "user", "content": prompt_text},
                        ],
                        "stream": False,
                        "options": {"temperature": 0.1, "num_predict": 100},
                    },
                )
                elapsed_ms = (time.perf_counter() - t0) * 1000
                total_no_tool_ms.append(elapsed_ms)

                if res.status_code == 200:
                    data = res.json()
                    eval_count = data.get("eval_count", 1)
                    eval_dur_ns = data.get("eval_duration", 1)
                    prompt_eval_ns = data.get("prompt_eval_duration", 0)
                    ttft_est_ms = prompt_eval_ns / 1_000_000.0
                    ttft_no_tool_ms.append(ttft_est_ms)
                    tps = (eval_count / (eval_dur_ns / 1e9)) if eval_dur_ns > 0 else 0.0
                    tokens_per_sec_no_tool.append(tps)

            # 3. Benchmark Tool-Call Prompts
            tool_prompts = [u.text for u in BENCHMARK_UTTERANCES if u.has_tool][:iterations]
            for prompt_text in tool_prompts:
                t0 = time.perf_counter()
                res = await client.post(
                    f"{self.base_url}/api/chat",
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": CONCISE_AGENT_INSTRUCTIONS},
                            {"role": "user", "content": prompt_text},
                        ],
                        "stream": False,
                        "options": {"temperature": 0.1, "num_predict": 150},
                    },
                )
                elapsed_ms = (time.perf_counter() - t0) * 1000
                total_tool_ms.append(elapsed_ms)

                if res.status_code == 200:
                    data = res.json()
                    eval_count = data.get("eval_count", 1)
                    eval_dur_ns = data.get("eval_duration", 1)
                    prompt_eval_ns = data.get("prompt_eval_duration", 0)
                    ttft_est_ms = prompt_eval_ns / 1_000_000.0
                    ttft_tool_ms.append(ttft_est_ms)
                    tps = (eval_count / (eval_dur_ns / 1e9)) if eval_dur_ns > 0 else 0.0
                    tokens_per_sec_tool.append(tps)

        return {
            "model": self.model,
            "no_tool": {
                "sample_count": len(total_no_tool_ms),
                "ttft_ms": calculate_distribution_stats(ttft_no_tool_ms),
                "total_ms": calculate_distribution_stats(total_no_tool_ms),
                "tokens_per_second": round(float(np.mean(tokens_per_sec_no_tool)), 1)
                if tokens_per_sec_no_tool
                else 0.0,
            },
            "tool_calling": {
                "sample_count": len(total_tool_ms),
                "ttft_ms": calculate_distribution_stats(ttft_tool_ms),
                "total_ms": calculate_distribution_stats(total_tool_ms),
                "tokens_per_second": round(float(np.mean(tokens_per_sec_tool)), 1)
                if tokens_per_sec_tool
                else 0.0,
            },
        }

    async def benchmark_prompt_length_tradeoff(self) -> dict[str, Any]:
        """Compare TTFT and output token length between verbose instructions and concise instructions."""
        test_query = "What apartments are available in Downtown under three thousand dollars?"

        async with httpx.AsyncClient(timeout=30.0) as client:
            # 1. Verbose instructions
            t0 = time.perf_counter()
            res_v = await client.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": DEFAULT_AGENT_INSTRUCTIONS},
                        {"role": "user", "content": test_query},
                    ],
                    "stream": False,
                },
            )
            dur_v = (time.perf_counter() - t0) * 1000
            data_v = res_v.json() if res_v.status_code == 200 else {}

            # 2. Concise instructions
            t0 = time.perf_counter()
            res_c = await client.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": CONCISE_AGENT_INSTRUCTIONS},
                        {"role": "user", "content": test_query},
                    ],
                    "stream": False,
                },
            )
            dur_c = (time.perf_counter() - t0) * 1000
            data_c = res_c.json() if res_c.status_code == 200 else {}

        return {
            "verbose": {
                "system_prompt_chars": len(DEFAULT_AGENT_INSTRUCTIONS),
                "prompt_eval_ms": round(data_v.get("prompt_eval_duration", 0) / 1e6, 2),
                "total_ms": round(dur_v, 2),
                "eval_tokens": data_v.get("eval_count", 0),
            },
            "concise": {
                "system_prompt_chars": len(CONCISE_AGENT_INSTRUCTIONS),
                "prompt_eval_ms": round(data_c.get("prompt_eval_duration", 0) / 1e6, 2),
                "total_ms": round(dur_c, 2),
                "eval_tokens": data_c.get("eval_count", 0),
            },
        }


class TTSProfiler:
    """Measures Kokoro TTS synthesis latency, HTTP roundtrip overhead, first-chunk TTFB, and chunking."""

    def __init__(self, kokoro_url: str = "http://127.0.0.1:8880") -> None:
        self.kokoro_url = kokoro_url

    async def benchmark_tts_latency(self, iterations: int = 25) -> dict[str, Any]:
        """Profile TTS HTTP endpoint for short, medium, and multi-sentence utterances."""
        short_text = "I found two matching apartments in Downtown."
        medium_text = (
            "The Grandview has a two bedroom unit for twenty-eight hundred dollars per month."
        )
        multi_sentence_text = (
            "I found two properties in Downtown. The first is The Grandview at twenty-eight hundred dollars. "
            "The second is Skyline Tower at twenty-four hundred dollars. Would you like to schedule a showing for one of them?"
        )

        short_latencies: list[float] = []
        medium_latencies: list[float] = []
        full_latencies: list[float] = []
        sentence1_latencies: list[float] = []

        async with httpx.AsyncClient(timeout=10.0) as client:
            # Short utterance
            for _ in range(iterations):
                t0 = time.perf_counter()
                _ = await client.post(
                    f"{self.kokoro_url}/v1/audio/speech",
                    json={"input": short_text, "voice": "af_alloy"},
                )
                short_latencies.append((time.perf_counter() - t0) * 1000)

            # Medium utterance
            for _ in range(iterations):
                t0 = time.perf_counter()
                _ = await client.post(
                    f"{self.kokoro_url}/v1/audio/speech",
                    json={"input": medium_text, "voice": "af_alloy"},
                )
                medium_latencies.append((time.perf_counter() - t0) * 1000)

            # Multi-sentence: Full text vs First sentence chunk
            for _ in range(iterations):
                # Full 3 sentences
                t0 = time.perf_counter()
                _ = await client.post(
                    f"{self.kokoro_url}/v1/audio/speech",
                    json={"input": multi_sentence_text, "voice": "af_alloy"},
                )
                full_latencies.append((time.perf_counter() - t0) * 1000)

                # First sentence only (streaming chunking benefit)
                t0 = time.perf_counter()
                _ = await client.post(
                    f"{self.kokoro_url}/v1/audio/speech",
                    json={
                        "input": "I found two properties in Downtown.",
                        "voice": "af_alloy",
                    },
                )
                sentence1_latencies.append((time.perf_counter() - t0) * 1000)

        return {
            "short_utterance_ms": calculate_distribution_stats(short_latencies),
            "medium_utterance_ms": calculate_distribution_stats(medium_latencies),
            "multi_sentence_full_ms": calculate_distribution_stats(full_latencies),
            "multi_sentence_first_chunk_ms": calculate_distribution_stats(sentence1_latencies),
            "chunking_ttfb_improvement_ms": round(
                float(np.mean(full_latencies) - np.mean(sentence1_latencies)), 2
            ),
        }


class DomainAndEventProfiler:
    """Measures local domain operations, repository lookups, SafeReadOnlyCache impact, and Event Journal."""

    def __init__(self, clock: Clock | None = None) -> None:
        self.clock = clock or SystemClock()

    async def benchmark_domain_and_cache(self, iterations: int = 100) -> dict[str, Any]:
        """Profile catalog search, property lookup, booking policy, and cache speedup."""
        prop_repo = InMemoryPropertyRepository.from_json_file("data/listings.json")
        showing_repo = InMemoryShowingRepository.from_json_file("data/showings.json")
        booking_repo = InMemoryBookingRepository()
        policy = BookingPolicyService(
            property_repo=prop_repo,
            showing_repo=showing_repo,
            booking_repo=booking_repo,
            clock=self.clock,
        )
        cache = SafeReadOnlyCache()

        # 1. Uncached property lookup
        uncached_get_times: list[float] = []
        for _ in range(iterations):
            t0 = time.perf_counter()
            _ = await prop_repo.get_by_id("prop-101")
            uncached_get_times.append((time.perf_counter() - t0) * 1000)

        # 2. Cached property lookup via SafeReadOnlyCache
        cached_get_times: list[float] = []
        prop_obj = await prop_repo.get_by_id("prop-101")
        cache.put_property("prop-101", prop_obj)
        for _ in range(iterations):
            t0 = time.perf_counter()
            _ = cache.get_property("prop-101")
            cached_get_times.append((time.perf_counter() - t0) * 1000)

        # 3. Uncached search
        uncached_search_times: list[float] = []
        for _ in range(iterations):
            t0 = time.perf_counter()
            _ = await prop_repo.search(max_rent=3000, bedrooms=2)
            uncached_search_times.append((time.perf_counter() - t0) * 1000)

        # 4. Cached search
        cached_search_times: list[float] = []
        s_res = await prop_repo.search(max_rent=3000, bedrooms=2)
        cache.put_search_results("search_3000_2", s_res)
        for _ in range(iterations):
            t0 = time.perf_counter()
            _ = cache.get_search_results("search_3000_2")
            cached_search_times.append((time.perf_counter() - t0) * 1000)

        # 5. Availability lookup (Always dynamic, never cached)
        avail_times: list[float] = []
        for _ in range(iterations):
            t0 = time.perf_counter()
            _ = await showing_repo.list_by_property("prop-101", available_only=True)
            avail_times.append((time.perf_counter() - t0) * 1000)

        # 6. Policy validation (book showing)
        policy_times: list[float] = []
        slots = await showing_repo.list_by_property("prop-101", available_only=True)
        for i in range(min(iterations, 10)):
            if not slots or i >= len(slots):
                break
            slot = slots[i]
            req = BookingRequest(
                property_id="prop-101",
                slot_id=slot.slot_id,
                renter_name=f"Test Lead {i}",
                renter_phone="+1-555-432-8765",
                renter_email="lead@example.com",
            )
            t0 = time.perf_counter()
            _booking_res = await policy.validate_and_reserve(req)
            policy_times.append((time.perf_counter() - t0) * 1000)

        return {
            "property_lookup_uncached_ms": calculate_distribution_stats(uncached_get_times),
            "property_lookup_cached_ms": calculate_distribution_stats(cached_get_times),
            "search_uncached_ms": calculate_distribution_stats(uncached_search_times),
            "search_cached_ms": calculate_distribution_stats(cached_search_times),
            "availability_lookup_ms": calculate_distribution_stats(avail_times),
            "booking_policy_exec_ms": calculate_distribution_stats(policy_times)
            if policy_times
            else "N/A",
            "cache_telemetry": {
                "hits": cache.hits,
                "misses": cache.misses,
                "hit_ratio": cache.hit_ratio,
            },
        }

    async def benchmark_event_journal(self, iterations: int = 50) -> dict[str, Any]:
        """Profile EventJournal SHA-256 chaining, serialization, PII masking, and disk flush."""
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as tmp:
            journal_path = tmp.name

        journal = EventJournal(file_path=journal_path)

        append_times: list[float] = []
        payload_sizes_bytes: list[int] = []

        for i in range(iterations):
            ev = DomainEvent(
                event_type=EventType.SHOWING_BOOKED.value,
                timestamp=datetime.datetime.now(datetime.UTC),
                session_id=f"sess-bench-{i}",
                workflow_id="wf-bench",
                turn_id=str(i),
                payload={
                    "booking_id": f"book-{i}",
                    "property_id": "prop-101",
                    "slot_id": "slot-201",
                    "lead_name": "Test User",
                    "phone": "+1-555-432-8765",
                    "email": "test.user@example.com",
                },
            )
            t0 = time.perf_counter()
            await journal.append(ev)
            append_times.append((time.perf_counter() - t0) * 1000)

            # Measure serialized JSON size
            raw_json = ev.model_dump_json()
            payload_sizes_bytes.append(len(raw_json.encode("utf-8")))

        # Verify integrity check cost
        t0 = time.perf_counter()
        integrity_valid = journal.verify_integrity()
        integrity_check_ms = (time.perf_counter() - t0) * 1000

        # Cleanup
        with contextlib.suppress(Exception):
            os.remove(journal_path)

        return {
            "event_append_with_sha256_ms": calculate_distribution_stats(append_times),
            "integrity_verification_ms": round(integrity_check_ms, 2),
            "integrity_valid": integrity_valid,
            "payload_size_bytes": {
                "mean": round(float(np.mean(payload_sizes_bytes)), 1),
                "min": int(np.min(payload_sizes_bytes)),
                "max": int(np.max(payload_sizes_bytes)),
            },
        }
