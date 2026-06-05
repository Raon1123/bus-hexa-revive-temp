"""HolidayEditor 서비스 단위 테스트.

기대값은 구현 독립 출처(날짜 포맷 규칙, 집합 연산)에서 정해짐.
"""
from __future__ import annotations

import pytest
from bushexa.services.holiday_editor import HolidayEditor, default_holidays_path


def test_load_empty_when_file_missing(tmp_path):
    """파일 부재 시 빈 set 반환."""
    ed = HolidayEditor(tmp_path / "holidays.json")
    assert ed.load() == set()


def test_add_and_load(tmp_path):
    """날짜 추가 후 로드하면 해당 날짜가 포함된다."""
    ed = HolidayEditor(tmp_path / "holidays.json")
    result = ed.add("20261001")
    assert result is True
    assert "20261001" in ed.load()


def test_add_invalid_format_returns_false(tmp_path):
    """YYYYMMDD 형식이 아닌 날짜는 False 반환, 파일 미변경."""
    ed = HolidayEditor(tmp_path / "holidays.json")
    assert ed.add("2026-10-01") is False   # 하이픈 포함
    assert ed.add("2026101") is False       # 7자리
    assert ed.add("202610011") is False     # 9자리
    assert ed.load() == set()


def test_remove_existing(tmp_path):
    """추가한 날짜를 제거하면 load에서 사라진다."""
    ed = HolidayEditor(tmp_path / "holidays.json")
    ed.add("20261001")
    ed.add("20261009")
    result = ed.remove("20261001")
    assert result is True
    dates = ed.load()
    assert "20261001" not in dates
    assert "20261009" in dates


def test_remove_nonexistent_returns_false(tmp_path):
    """없는 날짜 제거 시 False 반환."""
    ed = HolidayEditor(tmp_path / "holidays.json")
    assert ed.remove("20261001") is False


def test_save_and_load_roundtrip(tmp_path):
    """save → load 왕복."""
    ed = HolidayEditor(tmp_path / "holidays.json")
    dates = {"20261001", "20261009", "20261225"}
    ed.save(dates)
    assert ed.load() == dates


def test_corrupt_file_returns_empty(tmp_path):
    """파손 JSON은 빈 set로 처리."""
    p = tmp_path / "holidays.json"
    p.write_text("{not json", encoding="utf-8")
    assert HolidayEditor(p).load() == set()


def test_default_path(tmp_path):
    """default_holidays_path가 올바른 경로를 반환한다."""
    p = default_holidays_path(tmp_path)
    assert p.name == "holidays.json"
    assert p.parent == tmp_path
