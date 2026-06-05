"""Shared pytest fixtures.

These provide deterministic time, a throwaway SQLite path, a network guard, a
TAGO-client stand-in, and a ready-made test ``AppConfig`` so later phases can
write hermetic unit tests without touching real env, disk, or network.
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest
import requests

KST = ZoneInfo("Asia/Seoul")

# Directory holding API response samples (W7).
FIXTURES = Path(__file__).parent / "fixtures"


class FakeClock:
    """Deterministic clock (ADR-008). ``now()`` always returns the fixed value."""

    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


@pytest.fixture
def fake_clock() -> FakeClock:
    """A clock frozen at 2026-06-01 08:30:00 KST (a weekday morning)."""
    return FakeClock(datetime(2026, 6, 1, 8, 30, 0, tzinfo=KST))


@pytest.fixture
def tmp_sqlite_db():
    """Yield a path to a fresh temp SQLite file, deleted on teardown."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        yield Path(path)
    finally:
        Path(path).unlink(missing_ok=True)


@pytest.fixture
def mock_tago_client() -> MagicMock:
    """A MagicMock standing in for the (later-phase) TAGO API client."""
    return MagicMock(name="TagoClient")


@pytest.fixture
def app_config_test(tmp_path: Path):
    """An env-less :class:`AppConfig` backed by an in-memory SQLite URL."""
    from bushexa.config import AppConfig

    return AppConfig(
        api_key="test-api-key",
        database_url="sqlite:///:memory:",
        session_secret="test-session-secret",
        manager_password_path=tmp_path / "manager_password.txt",
        data_dir=tmp_path / "data",
        tz=KST,
        log_level="DEBUG",
        log_dir=tmp_path / "logs",
    )


@pytest.fixture
def no_network(monkeypatch: pytest.MonkeyPatch):
    """Opt-in guard: any ``requests.get``/``post`` during the test raises."""

    def _raise(*args, **kwargs):
        raise RuntimeError("network access is blocked in tests (use a fixture)")

    monkeypatch.setattr(requests, "get", _raise)
    monkeypatch.setattr(requests, "post", _raise)
    return None
