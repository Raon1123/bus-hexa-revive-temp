"""SpecialTimetableService 단위 테스트.

기대값은 구현 독립 출처(날짜 포맷, 에디션 ID 규칙, 파일 레이아웃)에서 정해짐.
"""
from __future__ import annotations

import json

import pytest

from bushexa.services.special_timetable import (
    SpecialTimetableService,
    _validate_edition_id,
    default_special_path,
    special_timetable_dir,
)


@pytest.fixture
def svc(tmp_path):
    tt_dir = tmp_path / "timetable"
    tt_dir.mkdir()
    return SpecialTimetableService(
        map_path=tmp_path / "special_timetables.json",
        timetable_dir=tt_dir,
    )


# ── 에디션 ID 검증 ─────────────────────────────────────────────────────────

def test_valid_edition_ids():
    assert _validate_edition_id("exam-2026-06") is True
    assert _validate_edition_id("festival_summer") is True
    assert _validate_edition_id("A1") is True


def test_invalid_edition_ids():
    assert _validate_edition_id("") is False
    assert _validate_edition_id("../etc/passwd") is False
    assert _validate_edition_id("with space") is False
    assert _validate_edition_id("a" * 65) is False


# ── 날짜→에디션 매핑 ────────────────────────────────────────────────────────

def test_load_map_empty_when_missing(svc):
    assert svc.load_map() == {}


def test_assign_and_load(svc):
    result = svc.assign("20260610", "exam-2026-06")
    assert result is True
    assert svc.load_map() == {"20260610": "exam-2026-06"}


def test_assign_invalid_date_returns_false(svc):
    assert svc.assign("2026-06-10", "exam") is False
    assert svc.load_map() == {}


def test_assign_invalid_edition_returns_false(svc):
    assert svc.assign("20260610", "../bad") is False
    assert svc.load_map() == {}


def test_unassign(svc):
    svc.assign("20260610", "exam")
    result = svc.unassign("20260610")
    assert result is True
    assert svc.load_map() == {}


def test_unassign_nonexistent_returns_false(svc):
    assert svc.unassign("20260610") is False


def test_get_edition_for_date(svc):
    svc.assign("20260610", "exam")
    assert svc.get_edition_for_date("20260610") == "exam"
    assert svc.get_edition_for_date("20260611") is None


# ── 에디션 디렉터리 목록 ────────────────────────────────────────────────────

def test_list_editions_empty(svc):
    assert svc.list_editions() == []


def test_list_editions(svc, tmp_path):
    tt_dir = tmp_path / "timetable"
    (tt_dir / "special" / "exam").mkdir(parents=True)
    (tt_dir / "special" / "festival").mkdir(parents=True)
    editions = svc.list_editions()
    assert "exam" in editions
    assert "festival" in editions


def test_edition_exists(svc, tmp_path):
    tt_dir = tmp_path / "timetable"
    (tt_dir / "special" / "exam").mkdir(parents=True)
    assert svc.edition_exists("exam") is True
    assert svc.edition_exists("nonexistent") is False


def test_edition_dir_invalid_id_returns_none(svc):
    assert svc.edition_dir("../bad") is None


def test_assignments_for_edition(svc):
    svc.assign("20260610", "exam")
    svc.assign("20260611", "exam")
    svc.assign("20260612", "other")
    assignments = svc.assignments_for_edition("exam")
    assert sorted(assignments) == ["20260610", "20260611"]


# ── 경로 유틸 ──────────────────────────────────────────────────────────────

def test_default_special_path(tmp_path):
    p = default_special_path(tmp_path)
    assert p.name == "special_timetables.json"


def test_special_timetable_dir(tmp_path):
    tt_dir = tmp_path / "timetable"
    d = special_timetable_dir(tt_dir, "exam-2026")
    assert d == tt_dir / "special" / "exam-2026"
