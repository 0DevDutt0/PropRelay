"""Tests for PropRelay environment diagnostics tool."""

from __future__ import annotations

import pytest

from proprelay.diagnostics import check_fixtures_and_data, check_python, run_all_diagnostics


@pytest.mark.asyncio
async def test_check_python():
    res = await check_python()
    assert res.category == "Core Environment"
    assert res.status == "PASS"
    assert "Python 3." in res.details


@pytest.mark.asyncio
async def test_check_fixtures_and_data():
    res = await check_fixtures_and_data()
    assert res.category == "Storage & Catalog"
    assert res.status == "PASS"


@pytest.mark.asyncio
async def test_run_all_diagnostics():
    checks = await run_all_diagnostics()
    assert len(checks) >= 6
    names = {c.name for c in checks}
    assert "Python Runtime" in names
    assert "Catalog Fixtures & Data" in names
    assert "Faster-Whisper STT" in names
