"""Unit tests verifying Clock abstractions."""

from __future__ import annotations

import datetime

from proprelay.domain.clock import FrozenClock, SystemClock


def test_system_clock() -> None:
    clock = SystemClock()
    now = clock.now()
    today = clock.today()
    assert now.tzinfo is not None
    assert today == now.date()


def test_frozen_clock() -> None:
    fixed_time = datetime.datetime(2026, 10, 1, 10, 0, 0, tzinfo=datetime.UTC)
    clock = FrozenClock(fixed_time)
    assert clock.now() == fixed_time
    assert clock.today() == datetime.date(2026, 10, 1)

    # Advance clock with timezone-aware
    advanced_time = datetime.datetime(2026, 10, 2, 12, 0, 0, tzinfo=datetime.UTC)
    clock.set_time(advanced_time)
    assert clock.now() == advanced_time
    assert clock.today() == datetime.date(2026, 10, 2)

    # Test naive datetime handling
    naive_time = datetime.datetime(2026, 10, 3, 14, 0, 0)
    naive_clock = FrozenClock(naive_time)
    assert naive_clock.now().tzinfo == datetime.UTC
    naive_clock.set_time(datetime.datetime(2026, 10, 4, 15, 0, 0))
    assert naive_clock.now().tzinfo == datetime.UTC
