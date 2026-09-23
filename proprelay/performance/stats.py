"""Statistical calculation utilities with strict sample-size integrity guards."""

from __future__ import annotations

import math
from typing import Any


def calculate_distribution_stats(
    values: list[float],
    min_samples_p95: int = 20,
    min_samples_p99: int = 100,
) -> dict[str, Any]:
    """Calculate summary statistics and percentiles with explicit sample-size guards.

    Prevents fabricated statistics (e.g. p95=0.0 when N=1).
    """
    n = len(values)
    if n == 0:
        return {
            "count": 0,
            "min_ms": None,
            "max_ms": None,
            "mean_ms": None,
            "stddev_ms": None,
            "p50_ms": "insufficient samples (N=0)",
            "p90_ms": "insufficient samples (N=0)",
            "p95_ms": "insufficient samples (N=0)",
            "p99_ms": "insufficient samples (N=0)",
        }

    sorted_vals = sorted(values)
    min_val = round(sorted_vals[0], 2)
    max_val = round(sorted_vals[-1], 2)
    mean_val = round(sum(sorted_vals) / n, 2)

    # Standard deviation requires N >= 2
    if n >= 2:
        variance = sum((x - mean_val) ** 2 for x in sorted_vals) / (n - 1)
        stddev_val = round(math.sqrt(variance), 2)
    else:
        stddev_val = 0.0

    # Strict sample-size guards for percentiles
    if n < 3:
        p50: Any = f"insufficient samples (N={n})"
        p90: Any = f"insufficient samples (N={n})"
        p95: Any = f"insufficient samples (N={n})"
        p99: Any = f"insufficient samples (N={n})"
    else:
        # Standard nearest-rank / linear interpolation percentile helper
        def _get_percentile(p: float) -> float:
            k = (n - 1) * p
            f = math.floor(k)
            c = math.ceil(k)
            if f == c:
                return round(sorted_vals[int(k)], 2)
            d0 = sorted_vals[int(f)] * (c - k)
            d1 = sorted_vals[int(c)] * (k - f)
            return round(d0 + d1, 2)

        p50 = _get_percentile(0.50)
        p90 = _get_percentile(0.90) if n >= 5 else f"insufficient samples for p90 (N={n})"

        if n >= min_samples_p95:
            p95 = _get_percentile(0.95)
        else:
            p95 = f"insufficient samples for p95 (requires N>={min_samples_p95}, got N={n})"

        if n >= min_samples_p99:
            p99 = _get_percentile(0.99)
        else:
            p99 = f"insufficient samples for p99 (requires N>={min_samples_p99}, got N={n})"

    return {
        "count": n,
        "min_ms": min_val,
        "max_ms": max_val,
        "mean_ms": mean_val,
        "stddev_ms": stddev_val,
        "p50_ms": p50,
        "p90_ms": p90,
        "p95_ms": p95,
        "p99_ms": p99,
    }
