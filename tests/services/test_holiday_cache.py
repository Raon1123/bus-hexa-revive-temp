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
    result = cache.refresh(client, [(2026, 7)])
    assert result == {"20260606"}
    raw = json.loads(p.read_text(encoding="utf-8"))
    assert raw == {"202606": ["20260606"]}


def test_refresh_partial_success_updates_only_succeeded(tmp_path):
    p = tmp_path / "holiday_cache.json"
    cache = HolidayCache(p)

    def fetch(y, m):
        if (y, m) == (2026, 7):
            raise RuntimeError("boom")
        return [datetime.date(2026, 6, 6)]

    client = MagicMock()
    client.fetch.side_effect = fetch

    result = cache.refresh(client, [(2026, 6), (2026, 7)])
    assert result == {"20260606"}
    raw = json.loads(p.read_text(encoding="utf-8"))
    assert "202606" in raw and "202607" not in raw


# ── read_effective_holidays (읽기 경로, API 미호출) ──────────────────────────

def test_read_unions_admin_and_cache(tmp_path):
    HolidayEditor(tmp_path / "holidays.json").save({"20260601"})
    (tmp_path / "holiday_cache.json").write_text(
        json.dumps({"202606": ["20260606"]}), encoding="utf-8"
    )
    assert read_effective_holidays(tmp_path) == {"20260601", "20260606"}


def test_read_empty_when_no_files(tmp_path):
    assert read_effective_holidays(tmp_path) == set()
