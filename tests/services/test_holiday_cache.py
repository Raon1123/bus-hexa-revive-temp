"""HolidayCache + read_effective_holidays 단위 테스트.

읽기 경로는 외부 API를 호출하지 않고 영속 캐시(holiday_cache.json) + admin(holidays.json)만
읽는다. 백엔드 refresh만 API를 호출하며, 월별로 안전하게 갱신한다(실패 월 보존, 빈 달 캐시).
"""
from __future__ import annotations

import datetime
import json
from unittest.mock import MagicMock

from bushexa.services.holiday_editor import HolidayEditor
from bushexa.services.holiday_service import (
    HolidayCache,
    read_effective_holidays,
    upcoming_months,
)


def _client(mapping):
    """HolidayClient 대역: fetch(y, m) → mapping[(y,m)] 의 date 목록."""
    c = MagicMock()
    c.fetch.side_effect = lambda y, m: mapping[(y, m)]
    return c


# ── upcoming_months ─────────────────────────────────────────────────────────

def test_upcoming_months_rolls_over_year():
    assert upcoming_months(datetime.date(2026, 12, 15), 2) == [(2026, 12), (2027, 1)]


def test_upcoming_months_default_two():
    assert upcoming_months(datetime.date(2026, 6, 1)) == [(2026, 6), (2026, 7)]


# ── HolidayCache load ────────────────────────────────────────────────────────

def test_load_missing_file_is_empty(tmp_path):
    assert HolidayCache(tmp_path / "nope.json").load() == set()


def test_load_corrupt_file_is_empty(tmp_path):
    p = tmp_path / "holiday_cache.json"
    p.write_text("{ not json", encoding="utf-8")
    assert HolidayCache(p).load() == set()


def test_load_flattens_months(tmp_path):
    p = tmp_path / "holiday_cache.json"
    p.write_text(json.dumps({"202606": ["20260606"], "202607": []}), encoding="utf-8")
    assert HolidayCache(p).load() == {"20260606"}


# ── HolidayCache refresh ─────────────────────────────────────────────────────

def test_refresh_writes_and_returns(tmp_path):
    p = tmp_path / "holiday_cache.json"
    cache = HolidayCache(p)
    client = _client({(2026, 6): [datetime.date(2026, 6, 6)], (2026, 7): []})

    result = cache.refresh(client, [(2026, 6), (2026, 7)])

    assert result == {"20260606"}
    raw = json.loads(p.read_text(encoding="utf-8"))
    assert raw == {"202606": ["20260606"], "202607": []}  # 빈 달도 캐시됨


def test_refresh_preserves_other_months_on_failure(tmp_path):
    p = tmp_path / "holiday_cache.json"
    p.write_text(json.dumps({"202606": ["20260606"]}), encoding="utf-8")
    cache = HolidayCache(p)

    client = MagicMock()
    client.fetch.side_effect = RuntimeError("network blocked")

    # 7월 갱신이 실패해도 기존 6월 캐시는 보존되어야 한다
    # (실패한 7월 자체는 오프라인 폴백으로 gap-fill — 2026-07은 법정공휴일 없음 → 빈 달 캐시)
    result = cache.refresh(client, [(2026, 7)])
    assert result == {"20260606"}
    raw = json.loads(p.read_text(encoding="utf-8"))
    assert raw["202606"] == ["20260606"]
    assert raw.get("202607", []) == []  # 제헌절은 비공휴일이라 제외 → 빈 달


def test_refresh_partial_success_updates_only_succeeded(tmp_path, monkeypatch):
    p = tmp_path / "holiday_cache.json"
    cache = HolidayCache(p)

    def fetch(y, m):
        if (y, m) == (2026, 7):
            raise RuntimeError("boom")
        return [datetime.date(2026, 6, 6)]

    client = MagicMock()
    client.fetch.side_effect = fetch
    # 오프라인 폴백까지 막아 '실패 월은 기록되지 않음'을 검증(폴백 동작은 별도 테스트)
    monkeypatch.setattr("bushexa.services.holiday_service.offline_month_holidays",
                        MagicMock(side_effect=RuntimeError("offline off")))

    result = cache.refresh(client, [(2026, 6), (2026, 7)])
    assert result == {"20260606"}
    raw = json.loads(p.read_text(encoding="utf-8"))
    assert "202606" in raw and "202607" not in raw


# ── 오프라인 폴백 (gap-fill) ─────────────────────────────────────────────────

def test_refresh_offline_fallback_fills_missing_month(tmp_path):
    """API 실패 + 캐시에 없는 월은 오프라인 계산(holidays 패키지)으로 채워지는지.

    2026-06은 현충일(0606)이 반드시 포함되어야 한다(지방선거일 0603도 패키지가 계산).
    """
    p = tmp_path / "holiday_cache.json"
    cache = HolidayCache(p)
    client = MagicMock()
    client.fetch.side_effect = RuntimeError("api down")

    result = cache.refresh(client, [(2026, 6)])

    assert "20260606" in result  # 현충일 — 오프라인 계산으로 확보
    raw = json.loads(p.read_text(encoding="utf-8"))
    assert "20260606" in raw["202606"]


def test_refresh_offline_fallback_never_overwrites_cached_month(tmp_path):
    """이미 캐시된 월은 API 실패 시 오프라인 값으로 덮어쓰지 않는지 — API 결과(임시공휴일
    포함 가능)가 법정공휴일만 아는 오프라인 계산보다 우선한다(gap-fill 전용)."""
    p = tmp_path / "holiday_cache.json"
    # 임시공휴일(0615 가정)이 포함된 기존 API 캐시
    p.write_text(json.dumps({"202606": ["20260606", "20260615"]}), encoding="utf-8")
    cache = HolidayCache(p)
    client = MagicMock()
    client.fetch.side_effect = RuntimeError("api down")

    result = cache.refresh(client, [(2026, 6)])

    assert result == {"20260606", "20260615"}  # 임시공휴일 보존
    raw = json.loads(p.read_text(encoding="utf-8"))
    assert raw["202606"] == ["20260606", "20260615"]


def test_offline_month_holidays_excludes_constitution_day():
    """holidays 패키지가 제헌절(7/17)을 공휴일로 잘못 분류하는 것을 제외하는지
    (2008년부터 비공휴일 — 버스는 평일 운행)."""
    from bushexa.services.holiday_service import offline_month_holidays

    july = offline_month_holidays(2026, 7)
    assert datetime.date(2026, 7, 17) not in july


# ── read_effective_holidays (읽기 경로, API 미호출) ──────────────────────────

def test_read_unions_admin_and_cache(tmp_path):
    HolidayEditor(tmp_path / "holidays.json").save({"20260601"})
    (tmp_path / "holiday_cache.json").write_text(
        json.dumps({"202606": ["20260606"]}), encoding="utf-8"
    )
    assert read_effective_holidays(tmp_path) == {"20260601", "20260606"}


def test_read_empty_when_no_files(tmp_path):
    assert read_effective_holidays(tmp_path) == set()
