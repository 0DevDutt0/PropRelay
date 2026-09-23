"""Unit tests for PropRelay LiveKit worker initialization."""

from __future__ import annotations

from proprelay.agent.worker import _init_domain_stack, server


def test_init_domain_stack() -> None:
    tools, journal = _init_domain_stack()
    assert tools is not None
    assert journal is not None
    # Repositories should have loaded fixture listings
    assert tools._property_repo is not None


def test_server_instance() -> None:
    assert server is not None
    assert hasattr(server, "rtc_session")
