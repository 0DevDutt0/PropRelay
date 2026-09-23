"""Benchmark utterance dataset and synthetic audio fixture generator."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, cast

import numpy as np


@dataclass(frozen=True)
class BenchmarkUtterance:
    id: str
    text: str
    category: (
        str  # "short", "medium", "long", "tool_call", "no_tool", "clarification", "correction"
    )
    expected_intent: str
    has_tool: bool


BENCHMARK_UTTERANCES: list[BenchmarkUtterance] = [
    # Short Utterances (1-5)
    BenchmarkUtterance("UTT-01", "Hello.", "short", "greeting", False),
    BenchmarkUtterance("UTT-02", "Yes, please confirm that.", "short", "confirm", True),
    BenchmarkUtterance("UTT-03", "Sunday at two PM.", "short", "time_selection", False),
    BenchmarkUtterance("UTT-04", "Thank you for the help.", "short", "farewell", False),
    BenchmarkUtterance("UTT-05", "That sounds good to me.", "short", "affirmation", False),
    # Medium Utterances (6-10)
    BenchmarkUtterance(
        "UTT-06",
        "Find a two bedroom apartment under three thousand dollars.",
        "medium",
        "search",
        True,
    ),
    BenchmarkUtterance("UTT-07", "Tell me more about the first one.", "medium", "detail", True),
    BenchmarkUtterance(
        "UTT-08", "What showings are available Saturday?", "medium", "availability", True
    ),
    BenchmarkUtterance(
        "UTT-09", "Is parking included with this listing?", "medium", "inquiry", False
    ),
    BenchmarkUtterance(
        "UTT-10",
        "Book the two PM showing for Sarah Jenkins.",
        "medium",
        "booking_proposal",
        True,
    ),
    # Long Utterances (11-15)
    BenchmarkUtterance(
        "UTT-11",
        "I am looking for a modern pet friendly apartment in Downtown with parking and at least two bedrooms under four thousand dollars.",
        "long",
        "search",
        True,
    ),
    BenchmarkUtterance(
        "UTT-12",
        "Could you give me the full details including square footage, pet policy, deposit amount, and available move in dates for the Grandview?",
        "long",
        "detail",
        True,
    ),
    BenchmarkUtterance(
        "UTT-13",
        "I need to reschedule my existing appointment from Saturday afternoon to Sunday anytime between one PM and four PM.",
        "long",
        "reschedule",
        True,
    ),
    BenchmarkUtterance(
        "UTT-14",
        "Can you check both the Skyline Tower and the Grandview to see which one has an earlier tour available this weekend?",
        "long",
        "comparison",
        True,
    ),
    BenchmarkUtterance(
        "UTT-15",
        "Please cancel my showing for tomorrow afternoon because my schedule changed and I can no longer make it.",
        "long",
        "cancel",
        True,
    ),
    # Tool-Calling Requests (16-20)
    BenchmarkUtterance(
        "UTT-16",
        "Search for apartments in Downtown under twenty five hundred.",
        "tool_call",
        "search",
        True,
    ),
    BenchmarkUtterance(
        "UTT-17",
        "What are the showing slots for property prop-101?",
        "tool_call",
        "availability",
        True,
    ),
    BenchmarkUtterance(
        "UTT-18",
        "Book the Saturday ten AM slot for Michael Chang at michael@example.com.",
        "tool_call",
        "booking_proposal",
        True,
    ),
    BenchmarkUtterance(
        "UTT-19",
        "Reschedule my booking book-201 to the two PM slot.",
        "tool_call",
        "reschedule",
        True,
    ),
    BenchmarkUtterance(
        "UTT-20",
        "Cancel booking book-201 because of a work conflict.",
        "tool_call",
        "cancel",
        True,
    ),
    # No-Tool Conversational Requests (21-24)
    BenchmarkUtterance(
        "UTT-21",
        "What is PropRelay and how do you help renters find properties?",
        "no_tool",
        "general_faq",
        False,
    ),
    BenchmarkUtterance(
        "UTT-22", "Can you repeat what you just said?", "no_tool", "clarification", False
    ),
    BenchmarkUtterance(
        "UTT-23",
        "Who is the leasing company managing these buildings?",
        "no_tool",
        "general_faq",
        False,
    ),
    BenchmarkUtterance("UTT-24", "Goodbye and have a nice day.", "no_tool", "farewell", False),
    # Clarification Requests (25-27)
    BenchmarkUtterance(
        "UTT-25", "I'm looking for a place to rent.", "clarification", "search_unspecified", True
    ),
    BenchmarkUtterance(
        "UTT-26", "Show me the available times.", "clarification", "availability_unspecified", False
    ),
    BenchmarkUtterance(
        "UTT-27", "Can I visit one of them?", "clarification", "tour_inquiry", False
    ),
    # Correction Requests (28-30)
    BenchmarkUtterance(
        "UTT-28", "Actually, use Sunday instead of Saturday.", "correction", "date_correction", True
    ),
    BenchmarkUtterance(
        "UTT-29", "No, don't book that, I changed my mind.", "correction", "rejection", True
    ),
    BenchmarkUtterance(
        "UTT-30",
        "Wait, I said two bedrooms not one bedroom.",
        "correction",
        "filter_correction",
        True,
    ),
]


def export_utterances_to_json(target_path: Path | str = "data/benchmark_utterances.json") -> Path:
    """Save the standard 30 benchmark utterances to a JSON fixture."""
    path = Path(target_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = [asdict(u) for u in BENCHMARK_UTTERANCES]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return path


def generate_synthetic_audio_tensor(
    text: str,
    sample_rate: int = 16000,
    kokoro_engine: Any | None = None,
) -> np.ndarray[Any, Any]:
    """Generate audio waveform for an utterance.

    If Kokoro ONNX is available and loaded, uses Kokoro to synthesize realistic speech,
    then downsamples from 24kHz to 16kHz float32.
    Otherwise generates a clean synthetic voiceband harmonic tone.
    """
    if kokoro_engine is not None and getattr(kokoro_engine, "is_loaded", False):
        try:
            samples, sr = kokoro_engine.synthesize(text, voice="af_alloy", speed=1.0)
            if sr != sample_rate:
                # Simple linear interpolation or decimation from 24k to 16k
                num_target = int(len(samples) * sample_rate / sr)
                indices = np.linspace(0, len(samples) - 1, num_target)
                resampled = np.interp(indices, np.arange(len(samples)), samples).astype(np.float32)
                return cast(np.ndarray[Any, Any], resampled)
            return cast(np.ndarray[Any, Any], samples.astype(np.float32))
        except Exception:
            pass

    # High quality synthetic carrier signal approximating speech cadence (~15 chars/sec)
    duration = max(0.5, len(text) / 15.0)
    t = np.linspace(0, duration, int(duration * sample_rate), endpoint=False, dtype=np.float32)
    # Formant frequencies typical of human vowels (F1=500Hz, F2=1500Hz)
    signal = 0.3 * np.sin(2 * np.pi * 180 * t) + 0.15 * np.sin(2 * np.pi * 500 * t)
    # Apply envelope
    fade_len = int(sample_rate * 0.05)
    fade_in = np.linspace(0, 1, fade_len, dtype=np.float32)
    fade_out = np.linspace(1, 0, fade_len, dtype=np.float32)
    signal[:fade_len] *= fade_in
    signal[-fade_len:] *= fade_out
    return signal.astype(np.float32)
