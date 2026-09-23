"""Clock abstraction for deterministic, repeatable time-dependent domain operations and tests."""

from __future__ import annotations

import datetime
from typing import Protocol


class Clock(Protocol):
    """Protocol for time-querying services."""

    def now(self) -> datetime.datetime:
        """Return current datetime (timezone-aware UTC)."""
        ...

    def today(self) -> datetime.date:
        """Return current date in UTC."""
        ...


class SystemClock:
    """Production clock implementation querying the real system wall clock."""

    def now(self) -> datetime.datetime:
        return datetime.datetime.now(datetime.UTC)

    def today(self) -> datetime.date:
        return datetime.datetime.now(datetime.UTC).date()


class FrozenClock:
    """Fixed-point clock for testing deterministic time-based policies."""

    def __init__(self, frozen_time: datetime.datetime) -> None:
        if frozen_time.tzinfo is None:
            # Default to UTC if naive
            self._time = frozen_time.replace(tzinfo=datetime.UTC)
        else:
            self._time = frozen_time

    def set_time(self, new_time: datetime.datetime) -> None:
        """Advance or move frozen time."""
        if new_time.tzinfo is None:
            self._time = new_time.replace(tzinfo=datetime.UTC)
        else:
            self._time = new_time

    def now(self) -> datetime.datetime:
        return self._time

    def today(self) -> datetime.date:
        return self._time.date()
