"""Deterministic natural-language date and time normalization utility for showings."""

from __future__ import annotations

import datetime
import re
from typing import Any

WEEKDAYS = {
    "monday": 0,
    "mon": 0,
    "tuesday": 1,
    "tue": 1,
    "wednesday": 2,
    "wed": 2,
    "thursday": 3,
    "thu": 3,
    "friday": 4,
    "fri": 4,
    "saturday": 5,
    "sat": 5,
    "sunday": 6,
    "sun": 6,
}

MONTHS = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sep": 9,
    "sept": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}


def normalize_date_expression(
    expr: str | None,
    reference_date: datetime.date,
) -> datetime.date | None:
    """Normalize a natural language date expression into a deterministic datetime.date.

    CRITICAL INVARIANT:
    All date calculations are strictly relative to reference_date (injected from Clock).
    Never calls datetime.now() or datetime.today().
    """
    if not expr or not expr.strip():
        return None

    cleaned = expr.strip().lower()

    # 1. Direct ISO format YYYY-MM-DD
    try:
        return datetime.date.fromisoformat(cleaned)
    except ValueError:
        pass

    # 2. Relative offsets: today, tomorrow, day after tomorrow
    if cleaned in ("today", "this day"):
        return reference_date
    if cleaned in ("tomorrow", "tmrw"):
        return reference_date + datetime.timedelta(days=1)
    if cleaned in ("day after tomorrow",):
        return reference_date + datetime.timedelta(days=2)

    # 3. "this weekend" / "the weekend" -> upcoming Saturday
    if "weekend" in cleaned:
        days_ahead = (5 - reference_date.weekday()) % 7
        if days_ahead == 0 and "next" not in cleaned:
            # If today is Saturday
            return reference_date
        if "next" in cleaned:
            days_ahead += 7
        return reference_date + datetime.timedelta(days=days_ahead if days_ahead > 0 else 7)

    # 4. Check for month + day (e.g. "october 5th", "oct 5", "5th of october")
    month_match = re.search(
        r"(?:(\d{1,2})(?:st|nd|rd|th)?\s+of\s+([a-z]+))|([a-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?",
        cleaned,
    )
    if month_match:
        if month_match.group(1) and month_match.group(2):
            day_str = month_match.group(1)
            month_str = month_match.group(2)
        else:
            month_str = month_match.group(3)
            day_str = month_match.group(4)

        if month_str in MONTHS:
            month = MONTHS[month_str]
            day = int(day_str)
            year = reference_date.year
            try:
                candidate = datetime.date(year, month, day)
                if candidate < reference_date:
                    candidate = datetime.date(year + 1, month, day)
                return candidate
            except ValueError:
                return None

    # 5. Weekday references: e.g. "next saturday", "this saturday", "saturday afternoon"
    is_next = "next" in cleaned
    is_this = "this" in cleaned

    for name, target_wd in WEEKDAYS.items():
        if re.search(r"\b" + name + r"\b", cleaned):
            ref_wd = reference_date.weekday()
            diff = (target_wd - ref_wd) % 7

            if is_next:
                # "next saturday" means the saturday of next week
                days_ahead = diff + 7 if diff > 0 else 7
            elif is_this:
                # "this saturday" means the saturday of the current week (or today if today is saturday)
                days_ahead = diff
            else:
                # Just "saturday": upcoming saturday (if today is saturday, treat as today or upcoming)
                days_ahead = diff if diff > 0 else 7

            return reference_date + datetime.timedelta(days=days_ahead)

    return None


def normalize_time_expression(expr: str | None) -> datetime.time | None:
    """Extract a normalized datetime.time from an expression like '3 PM', '15:00', '10:30 am'."""
    if not expr or not expr.strip():
        return None

    cleaned = expr.strip().lower()

    # Pattern: HH:MM or HH with optional AM/PM
    match = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", cleaned)
    if not match:
        return None

    hour = int(match.group(1))
    minute = int(match.group(2)) if match.group(2) else 0
    meridiem = match.group(3)

    if meridiem == "pm" and hour < 12:
        hour += 12
    elif meridiem == "am" and hour == 12:
        hour = 0

    if 0 <= hour <= 23 and 0 <= minute <= 59:
        return datetime.time(hour, minute)

    return None


def match_slot_reference(
    slots: list[Any],
    ref: str | None,
) -> Any | None:
    """Deterministically resolve a slot from an available slots list given a user reference.

    Supports:
    - Exact slot_id ('slot-101-01')
    - Time matches ('3 PM', '15:00', '3:00')
    - Positional words ('the first one', 'first', 'second', 'the last slot', 'last')
    - Time-of-day phrases ('the afternoon appointment', 'morning slot', 'evening slot')
    """
    if not ref or not ref.strip() or not slots:
        return None

    cleaned = ref.strip().lower()

    # 1. Exact slot_id match
    for slot in slots:
        slot_id = getattr(slot, "slot_id", None) or (
            slot.get("slot_id") if isinstance(slot, dict) else None
        )
        if slot_id and slot_id.lower() == cleaned:
            return slot

    # 2. Positional references
    if re.search(r"\b(first|1st|first one|1)\b", cleaned):
        return slots[0]
    if re.search(r"\b(second|2nd|second one|2)\b", cleaned) and len(slots) >= 2:
        return slots[1]
    if re.search(r"\b(third|3rd|third one|3)\b", cleaned) and len(slots) >= 3:
        return slots[2]
    if re.search(r"\b(last|last one|final)\b", cleaned):
        return slots[-1]

    # 3. Specific time match (e.g. "3 PM", "15:00", "10:30")
    target_time = normalize_time_expression(cleaned)
    if target_time:
        for slot in slots:
            start_time = getattr(slot, "start_time", None) or (
                slot.get("start_time") if isinstance(slot, dict) else None
            )
            if start_time:
                if isinstance(start_time, str):
                    try:
                        start_time = datetime.time.fromisoformat(start_time)
                    except ValueError:
                        continue
                if start_time.hour == target_time.hour and (
                    target_time.minute == 0 or start_time.minute == target_time.minute
                ):
                    return slot

    # 4. Period-of-day matches (only if unambiguous)
    if "morning" in cleaned:
        morning_slots = [
            s
            for s in slots
            if (
                getattr(s, "start_time", None)
                or (
                    datetime.time.fromisoformat(s["start_time"])
                    if isinstance(s, dict) and isinstance(s.get("start_time"), str)
                    else s.get("start_time")
                )
            ).hour
            < 12
        ]
        if len(morning_slots) == 1:
            return morning_slots[0]

    if "afternoon" in cleaned:
        afternoon_slots = [
            s
            for s in slots
            if 12
            <= (
                getattr(s, "start_time", None)
                or (
                    datetime.time.fromisoformat(s["start_time"])
                    if isinstance(s, dict) and isinstance(s.get("start_time"), str)
                    else s.get("start_time")
                )
            ).hour
            < 17
        ]
        if len(afternoon_slots) == 1:
            return afternoon_slots[0]

    if "evening" in cleaned:
        evening_slots = [
            s
            for s in slots
            if (
                getattr(s, "start_time", None)
                or (
                    datetime.time.fromisoformat(s["start_time"])
                    if isinstance(s, dict) and isinstance(s.get("start_time"), str)
                    else s.get("start_time")
                )
            ).hour
            >= 17
        ]
        if len(evening_slots) == 1:
            return evening_slots[0]

    return None
