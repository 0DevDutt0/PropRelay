"""Validation tests verifying static fixture integrity for listings.json and showings.json."""

from __future__ import annotations

import json
from pathlib import Path

from proprelay.domain.models import Property, ShowingSlot


def test_fixture_listings_integrity() -> None:
    listings_path = Path("data/listings.json")
    assert listings_path.exists(), "data/listings.json fixture file must exist"

    with open(listings_path, encoding="utf-8") as f:
        raw_listings = json.load(f)

    assert len(raw_listings) >= 6, "Expected at least 6 demo property listings"

    seen_property_ids: set[str] = set()
    two_bedroom_count = 0

    for item in raw_listings:
        # Validate Pydantic schema parsing
        prop = Property.model_validate(item)
        assert prop.property_id not in seen_property_ids, (
            f"Duplicate property_id: {prop.property_id}"
        )
        seen_property_ids.add(prop.property_id)

        if prop.bedrooms == 2:
            two_bedroom_count += 1

    assert two_bedroom_count >= 2, (
        f"Expected at least two 2-bedroom listings, found {two_bedroom_count}"
    )


def test_fixture_showings_integrity() -> None:
    listings_path = Path("data/listings.json")
    showings_path = Path("data/showings.json")
    assert showings_path.exists(), "data/showings.json fixture file must exist"

    with open(listings_path, encoding="utf-8") as f:
        raw_listings = json.load(f)
    valid_property_ids = {item["property_id"] for item in raw_listings}

    with open(showings_path, encoding="utf-8") as f:
        raw_showings = json.load(f)

    assert len(raw_showings) >= 5, "Expected showing slots in fixture"

    seen_slot_ids: set[str] = set()

    for item in raw_showings:
        slot = ShowingSlot.model_validate(item)
        assert slot.slot_id not in seen_slot_ids, f"Duplicate slot_id: {slot.slot_id}"
        seen_slot_ids.add(slot.slot_id)

        # Integrity check: every showing slot references an existing property in listings.json
        assert slot.property_id in valid_property_ids, (
            f"Orphan showing slot '{slot.slot_id}' references unknown property '{slot.property_id}'"
        )
