"""HolidayService 단위 테스트.

실효 공휴일 집합 = admin 지정 UNION API 공휴일.
API 실패는 빈 set + 로그(500 없음).
"""
from __future__ import annotations

import datetime
from unittest.mock import MagicMock

import pytest
from zoneinfo import ZoneInfo

from bushexa.services.holiday_editor import HolidayEditor
from bushexa.services.holiday_service import get_effective_holiday_set, _fetch_api_holidays

KST = ZoneInfo("Asia/Seoul")
TODAY = datetime.date(2026, 6, 1)


def _make_client(dates: list[datetime.date]):
    """HolidayClient 대역: fetch() → 지정 date 목록."""
    client = MagicMock()
    client.fetch.return_value = dates
    return client


def _make_failing_client(exc=RuntimeError("network blocked")):
    """HolidayClient 대역: fetch() → 예외."""
    client = MagicMock()
    client.fetch.side_effect = exc
    return client


# ── union ─────────────────────────────────────────────────────────────────

def test_union_of_admin_and_api(tmp_path):
    """admin 날짜 + API 날짜의 합집합을 반환한다."""
    ed = HolidayEditor(tmp_path / "holidays.json")
    ed.save({"20260601"})

    api_dates = [datetime.date(2026, 6, 9)]   # 현충일 (예시)
    client = _make_client(api_dates)
    cache: dict = {}

    result = get_effective_holiday_set(
        TODAY, holiday_editor=ed, holiday_client=client, cache=cache
    )

    assert "20260601" in result   # admin 지정
    assert "20260609" in result   # API 반환


def test_api_only_when_no_admin(tmp_path):
    """admin 지정 없이 API 날짜만 있으면 API 날짜가 포함된다."""
    ed = HolidayEditor(tmp_path / "holidays.json")
    client = _make_client([datetime.date(2026, 6, 9)])
    cache: dict = {}

    result = get_effective_holiday_set(
        TODAY, holiday_editor=ed, holiday_client=client, cache=cache
    )
    assert "20260609" in result


def test_admin_only_when_api_fails(tmp_path):
    """API 실패 시 admin 날짜만 반환 (500 없음)."""
    ed = HolidayEditor(tmp_path / "holidays.json")
    ed.save({"20260601"})

    client = _make_failing_client()
    cache: dict = {}

    result = get_effective_holiday_set(
        TODAY, holiday_editor=ed, holiday_client=client, cache=cache
    )
    assert "20260601" in result
    assert len(result) == 1   # API 실패 → API 날짜 없음


def test_api_result_is_cached(tmp_path):
    """동일 연·월의 두 번째 호출은 API를 다시 호출하지 않는다."""
    ed = HolidayEditor(tmp_path / "holidays.json")
    client = _make_client([datetime.date(2026, 6, 9)])
    cache: dict = {}

    get_effective_holiday_set(
        TODAY, holiday_editor=ed, holiday_client=client, cache=cache
    )
    get_effective_holiday_set(
        TODAY, holiday_editor=ed, holiday_client=client, cache=cache
    )

    # fetch는 정확히 1번만 호출돼야 한다 (두 번째는 cache hit)
    assert client.fetch.call_count == 1


def test_empty_when_both_empty(tmp_path):
    """admin·API 모두 없으면 빈 set."""
    ed = HolidayEditor(tmp_path / "holidays.json")
    client = _make_client([])
    cache: dict = {}

    result = get_effective_holiday_set(
        TODAY, holiday_editor=ed, holiday_client=client, cache=cache
    )
    assert result == set()
