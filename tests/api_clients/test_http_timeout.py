"""API HTTP timeout 해석(_http.resolve_api_timeout) — env 설정화(2026-06-06).

울산 API 느린 응답이 10초 timeout에 잘리는 문제 대응: 기본 15초, env로 조정.
"""
from __future__ import annotations

from bushexa.api_clients._http import resolve_api_timeout
from bushexa.api_clients.holiday import HolidayClient
from bushexa.api_clients.tago import TagoClient
from bushexa.api_clients.ulsan_bis import UlsanBisClient


def test_default_is_15(monkeypatch):
    monkeypatch.delenv("BUSHEXA_API_TIMEOUT_SECONDS", raising=False)
    assert resolve_api_timeout() == 15.0


def test_env_override(monkeypatch):
    monkeypatch.setenv("BUSHEXA_API_TIMEOUT_SECONDS", "10")
    assert resolve_api_timeout() == 10.0


def test_explicit_beats_env(monkeypatch):
    monkeypatch.setenv("BUSHEXA_API_TIMEOUT_SECONDS", "10")
    assert resolve_api_timeout(3.0) == 3.0


def test_all_clients_use_resolved_default(monkeypatch):
    """세 클라이언트(TAGO·울산 BIS·공휴일) 모두 timeout 미지정 시 env 값을 쓴다."""
    monkeypatch.setenv("BUSHEXA_API_TIMEOUT_SECONDS", "12.5")
    for cls in (TagoClient, UlsanBisClient, HolidayClient):
        assert cls("dummy-key").timeout == 12.5


def test_explicit_constructor_timeout_preserved(monkeypatch):
    """명시 timeout 인자는 env와 무관하게 그대로(기존 호출부 하위호환)."""
    monkeypatch.setenv("BUSHEXA_API_TIMEOUT_SECONDS", "12.5")
    assert TagoClient("dummy-key", timeout=10.0).timeout == 10.0
