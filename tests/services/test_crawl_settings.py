"""CrawlSettingsStore 단위 테스트.

기대값은 MIN_POLL_SECONDS·MAX_POLL_SECONDS 상수와 직접 주입한 값에서 도출(E-13).
네트워크 미사용. tmp_path로 격리.
"""
from __future__ import annotations

import json

import pytest

from bushexa.services.crawl_settings import (
    MIN_POLL_SECONDS,
    MAX_POLL_SECONDS,
    CrawlSettingsStore,
    default_crawl_settings_path,
)


# ---------------------------------------------------------------------------
# load() 관대성 검증 (파일 부재·파손·범위 밖 → 기본값 폴백, 데몬 불사)
# ---------------------------------------------------------------------------

def test_load_file_missing_returns_empty(tmp_path):
    """파일이 없으면 빈 dict를 반환하고 예외가 발생하지 않는다."""
    store = CrawlSettingsStore(tmp_path / "crawl_settings.json")
    assert store.load() == {}


def test_load_corrupt_json_returns_empty(tmp_path):
    """파손된 JSON이면 빈 dict를 반환하고 예외가 발생하지 않는다."""
    p = tmp_path / "crawl_settings.json"
    p.write_text("{bad json", encoding="utf-8")
    store = CrawlSettingsStore(p)
    assert store.load() == {}


def test_load_out_of_range_value_ignored(tmp_path):
    """범위 밖 필드는 무시되고(기본값 폴백), 유효한 필드는 유지된다."""
    p = tmp_path / "crawl_settings.json"
    # govtrack_poll_seconds = 1 → MIN 미만 → 무시
    # arrival_poll_seconds = 20 → 유효
    p.write_text(json.dumps({"govtrack_poll_seconds": 1, "arrival_poll_seconds": 20}),
                 encoding="utf-8")
    store = CrawlSettingsStore(p)
    result = store.load()
    assert "govtrack_poll_seconds" not in result   # 범위 밖 → 무시
    assert result["arrival_poll_seconds"] == 20.0  # 유효 → 보존


def test_load_both_out_of_range_returns_empty(tmp_path):
    """두 필드가 모두 범위 밖이면 빈 dict."""
    p = tmp_path / "crawl_settings.json"
    p.write_text(json.dumps({"govtrack_poll_seconds": 0, "arrival_poll_seconds": 9999}),
                 encoding="utf-8")
    store = CrawlSettingsStore(p)
    assert store.load() == {}


def test_load_non_dict_returns_empty(tmp_path):
    """JSON이지만 dict가 아니면(예: 배열) 빈 dict 반환."""
    p = tmp_path / "crawl_settings.json"
    p.write_text(json.dumps([10, 20]), encoding="utf-8")
    store = CrawlSettingsStore(p)
    assert store.load() == {}


# ---------------------------------------------------------------------------
# save() 엄격성 검증 (범위 밖 → ValueError)
# ---------------------------------------------------------------------------

def test_save_below_min_raises(tmp_path):
    """MIN 미만 값은 ValueError."""
    store = CrawlSettingsStore(tmp_path / "crawl_settings.json")
    with pytest.raises(ValueError):
        store.save(govtrack_poll_seconds=MIN_POLL_SECONDS - 0.1)


def test_save_above_max_raises(tmp_path):
    """MAX 초과 값은 ValueError."""
    store = CrawlSettingsStore(tmp_path / "crawl_settings.json")
    with pytest.raises(ValueError):
        store.save(arrival_poll_seconds=MAX_POLL_SECONDS + 1)


def test_save_zero_raises(tmp_path):
    """0 초(busy-loop 방지)는 ValueError."""
    store = CrawlSettingsStore(tmp_path / "crawl_settings.json")
    with pytest.raises(ValueError):
        store.save(govtrack_poll_seconds=0)


def test_save_non_numeric_raises(tmp_path):
    """숫자가 아닌 값은 ValueError."""
    store = CrawlSettingsStore(tmp_path / "crawl_settings.json")
    with pytest.raises(ValueError):
        store.save(govtrack_poll_seconds="abc")


# ---------------------------------------------------------------------------
# save + load 왕복 검증
# ---------------------------------------------------------------------------

def test_save_load_roundtrip(tmp_path):
    """save한 값이 load 후 동일하게 돌아온다."""
    store = CrawlSettingsStore(tmp_path / "crawl_settings.json")
    saved = store.save(govtrack_poll_seconds=15.0, arrival_poll_seconds=8.0)
    assert saved == {"govtrack_poll_seconds": 15.0, "arrival_poll_seconds": 8.0}
    assert store.load() == {"govtrack_poll_seconds": 15.0, "arrival_poll_seconds": 8.0}


def test_save_boundary_values(tmp_path):
    """경계값(MIN·MAX 정확히)은 save/load 모두 허용된다."""
    store = CrawlSettingsStore(tmp_path / "crawl_settings.json")
    store.save(govtrack_poll_seconds=MIN_POLL_SECONDS, arrival_poll_seconds=MAX_POLL_SECONDS)
    result = store.load()
    assert result["govtrack_poll_seconds"] == MIN_POLL_SECONDS
    assert result["arrival_poll_seconds"] == MAX_POLL_SECONDS


# ---------------------------------------------------------------------------
# save(None) → 필드 제거 검증
# ---------------------------------------------------------------------------

def test_save_none_removes_field(tmp_path):
    """None을 전달하면 해당 필드가 제거되고 기본값 폴백 상태로 돌아간다."""
    store = CrawlSettingsStore(tmp_path / "crawl_settings.json")
    store.save(govtrack_poll_seconds=30.0, arrival_poll_seconds=10.0)
    # govtrack만 None으로 → 제거됨
    store.save(govtrack_poll_seconds=None, arrival_poll_seconds=10.0)
    result = store.load()
    assert "govtrack_poll_seconds" not in result
    assert result["arrival_poll_seconds"] == 10.0


def test_save_all_none_removes_all(tmp_path):
    """두 값 모두 None이면 파일이 빈 dict({})로 저장된다."""
    store = CrawlSettingsStore(tmp_path / "crawl_settings.json")
    store.save(govtrack_poll_seconds=20.0, arrival_poll_seconds=5.0)
    store.save(govtrack_poll_seconds=None, arrival_poll_seconds=None)
    assert store.load() == {}


# ---------------------------------------------------------------------------
# govtrack_poll_seconds / arrival_poll_seconds(default) 동작
# ---------------------------------------------------------------------------

def test_govtrack_poll_seconds_uses_file_value(tmp_path):
    """파일에 값이 있으면 그 값을 반환한다."""
    store = CrawlSettingsStore(tmp_path / "crawl_settings.json")
    store.save(govtrack_poll_seconds=45.0)
    assert store.govtrack_poll_seconds(default=10) == 45.0


def test_govtrack_poll_seconds_uses_default_when_missing(tmp_path):
    """파일에 govtrack 값이 없으면 default를 반환한다."""
    store = CrawlSettingsStore(tmp_path / "crawl_settings.json")
    # arrival만 저장 → govtrack 미설정
    store.save(arrival_poll_seconds=7.0)
    assert store.govtrack_poll_seconds(default=10) == 10.0


def test_arrival_poll_seconds_uses_file_value(tmp_path):
    """파일에 값이 있으면 그 값을 반환한다."""
    store = CrawlSettingsStore(tmp_path / "crawl_settings.json")
    store.save(arrival_poll_seconds=12.0)
    assert store.arrival_poll_seconds(default=7) == 12.0


def test_arrival_poll_seconds_uses_default_when_missing(tmp_path):
    """파일에 arrival 값이 없으면 default를 반환한다."""
    store = CrawlSettingsStore(tmp_path / "crawl_settings.json")
    store.save(govtrack_poll_seconds=20.0)
    assert store.arrival_poll_seconds(default=7) == 7.0


def test_file_missing_govtrack_returns_default(tmp_path):
    """파일 자체가 없을 때 govtrack_poll_seconds는 default를 반환한다."""
    store = CrawlSettingsStore(tmp_path / "crawl_settings.json")
    assert store.govtrack_poll_seconds(default=10) == 10.0


def test_file_missing_arrival_returns_default(tmp_path):
    """파일 자체가 없을 때 arrival_poll_seconds는 default를 반환한다."""
    store = CrawlSettingsStore(tmp_path / "crawl_settings.json")
    assert store.arrival_poll_seconds(default=7) == 7.0


# ---------------------------------------------------------------------------
# default_crawl_settings_path 헬퍼
# ---------------------------------------------------------------------------

def test_default_crawl_settings_path(tmp_path):
    """<data_dir>/crawl_settings.json 경로를 반환한다."""
    result = default_crawl_settings_path(tmp_path)
    assert result == tmp_path / "crawl_settings.json"
