"""Unit tests for deterministic natural-language date and time normalization."""

from __future__ import annotations

import datetime

import pytest

from proprelay.agent.date_normalization import (
    match_slot_reference,
    normalize_date_expression,
    normalize_time_expression,
)
from proprelay.domain.clock import FrozenClock
from proprelay.domain.models import ShowingSlot, ShowingSlotStatus


@pytest.fixture
def frozen_clock() -> FrozenClock:
    # 2026-10-01 is a Thursday (weekday = 3)
    # Friday is 2026-10-02 (weekday = 4)
    # Saturday is 2026-10-03 (weekday = 5)
    # Sunday is 2026-10-04 (weekday = 6)
    # Next Saturday is 2026-10-10 (weekday = 5)
    dt = datetime.datetime(2026, 10, 1, 9, 0, 0)
    return FrozenClock(dt)


def test_normalize_direct_iso(frozen_clock: FrozenClock) -> None:
    ref = frozen_clock.today()
    assert normalize_date_expression("2026-10-05", ref) == datetime.date(2026, 10, 5)
    assert normalize_date_expression("2026-12-25", ref) == datetime.date(2026, 12, 25)


def test_normalize_tomorrow(frozen_clock: FrozenClock) -> None:
    ref = frozen_clock.today()  # 2026-10-01 (Thursday)
    assert normalize_date_expression("tomorrow", ref) == datetime.date(2026, 10, 2)
    assert normalize_date_expression("tmrw", ref) == datetime.date(2026, 10, 2)


def test_normalize_saturday(frozen_clock: FrozenClock) -> None:
    ref = frozen_clock.today()  # 2026-10-01 (Thursday)
    # Upcoming Saturday is 2026-10-03
    assert normalize_date_expression("Saturday", ref) == datetime.date(2026, 10, 3)
    assert normalize_date_expression("this Saturday", ref) == datetime.date(2026, 10, 3)


def test_normalize_next_saturday(frozen_clock: FrozenClock) -> None:
    ref = frozen_clock.today()  # 2026-10-01 (Thursday)
    # Next Saturday is 2026-10-10
    assert normalize_date_expression("next Saturday", ref) == datetime.date(2026, 10, 10)


def test_normalize_saturday_afternoon(frozen_clock: FrozenClock) -> None:
    ref = frozen_clock.today()
    assert normalize_date_expression("Saturday afternoon", ref) == datetime.date(2026, 10, 3)


def test_normalize_weekend(frozen_clock: FrozenClock) -> None:
    ref = frozen_clock.today()
    assert normalize_date_expression("this weekend", ref) == datetime.date(2026, 10, 3)


def test_normalize_month_day(frozen_clock: FrozenClock) -> None:
    ref = frozen_clock.today()  # 2026-10-01
    assert normalize_date_expression("October 5th", ref) == datetime.date(2026, 10, 5)
    assert normalize_date_expression("5th of October", ref) == datetime.date(2026, 10, 5)


def test_normalize_time_expressions() -> None:
    assert normalize_time_expression("around 3 PM") == datetime.time(15, 0)
    assert normalize_time_expression("3 PM") == datetime.time(15, 0)
    assert normalize_time_expression("3:30 pm") == datetime.time(15, 30)
    assert normalize_time_expression("10 AM") == datetime.time(10, 0)
    assert normalize_time_expression("10:00 am") == datetime.time(10, 0)
    assert normalize_time_expression("15:00") == datetime.time(15, 0)
    assert normalize_time_expression("invalid text") is None


def test_match_slot_reference() -> None:
    slot_1 = ShowingSlot(
        slot_id="slot-101-01",
        property_id="prop-101",
        date=datetime.date(2026, 10, 3),
        start_time=datetime.time(10, 0),
        end_time=datetime.time(10, 45),
        status=ShowingSlotStatus.AVAILABLE,
    )
    slot_2 = ShowingSlot(
        slot_id="slot-101-02",
        property_id="prop-101",
        date=datetime.date(2026, 10, 3),
        start_time=datetime.time(15, 0),
        end_time=datetime.time(15, 45),
        status=ShowingSlotStatus.AVAILABLE,
    )
    slots = [slot_1, slot_2]

    # Exact slot ID
    assert match_slot_reference(slots, "slot-101-01") == slot_1

    # Time expression
    assert match_slot_reference(slots, "The 3 PM one") == slot_2
    assert match_slot_reference(slots, "10:00 AM") == slot_1

    # Positional
    assert match_slot_reference(slots, "the first one") == slot_1
    assert match_slot_reference(slots, "the second one") == slot_2
    assert match_slot_reference(slots, "the last slot") == slot_2

    # Period of day (unambiguous)
    assert match_slot_reference(slots, "the afternoon appointment") == slot_2
    assert match_slot_reference(slots, "morning slot") == slot_1

    # Ambiguous or non-matching
    assert match_slot_reference(slots, "evening") is None
    assert match_slot_reference(slots, "5 PM") is None
