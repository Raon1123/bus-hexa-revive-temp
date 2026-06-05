"""W11 TimetableEditor 테스트 (E-13 준수).

기대값은 spec에서: 25:00은 out_of_range로 거부됨(spec), 백업은 저장 전 생성.
구현 출력 복사 금지.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from bushexa.services.timetable_editor import (
    SaveResult,
    TimetableEditor,
    ValidationError,
)

# ──────────────────────────────────────────────────────────────────────────
# 테스트 픽스처 데이터
# ──────────────────────────────────────────────────────────────────────────

# 검증에 통과하는 최소 시간표 (spec 상 유효한 값)
_VALID_DATA: dict = {
    "0": {"UNIST": ["06:00", "07:00", "08:00"]},
    "1": {"UNIST": ["09:00"]},
    "2": {"UNIST": ["10:00"]},
}

# 잘못된 시각이 포함된 시간표: "25:00"은 out_of_range (spec 근거)
_INVALID_DATA: dict = {
    "0": {"UNIST": ["25:00", "07:00"]},
    "1": {"UNIST": ["09:00"]},
    "2": {"UNIST": ["10:00"]},
}


class FakeClock:
    """결정적 타임스탬프 주입 (ADR-008)."""

    def __init__(self, ts_str: str = "20260601-120000") -> None:
        self._ts = ts_str
        import datetime
        from zoneinfo import ZoneInfo
        # strftime 호환을 위해 datetime 반환
        self._dt = datetime.datetime(2026, 6, 1, 12, 0, 0,
                                     tzinfo=ZoneInfo("Asia/Seoul"))

    def now(self):
        return self._dt


def _make_editor(tmp_path: Path, clock=None) -> tuple[TimetableEditor, Path, Path]:
    tdir = tmp_path / "timetable"
    bdir = tmp_path / "backup"
    tdir.mkdir()
    bdir.mkdir()
    clock = clock or FakeClock()
    editor = TimetableEditor(dir=tdir, backup_dir=bdir, clock=clock)
    return editor, tdir, bdir


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=4), encoding="utf-8")


# ──────────────────────────────────────────────────────────────────────────
# AC-1: save 시 backup_dir에 타임스탬프 백업 생성
# ──────────────────────────────────────────────────────────────────────────

def test_save_backup(tmp_path):
    """713.json 편집·저장 시 backup_dir에 713.{ts}.json 생성 (AC-1)."""
    clock = FakeClock("20260601-120000")
    editor, tdir, bdir = _make_editor(tmp_path, clock)

    # 기존 파일 작성
    _write_json(tdir / "713.json", _VALID_DATA)

    result = editor.save("713", _VALID_DATA)

    assert isinstance(result, SaveResult)
    assert result.busno == "713"

    # 백업 파일 확인: 713.20260601-120000.json
    expected_ts = "20260601-120000"
    backup_files = list(bdir.glob("713.*.json"))
    assert len(backup_files) == 1, f"백업 파일이 1개여야 함: {list(bdir.iterdir())}"
    assert backup_files[0].name == f"713.{expected_ts}.json"


# ──────────────────────────────────────────────────────────────────────────
# AC-2: 잘못된 형식 저장 시 ValidationError + 디스크 원본 보존
# ──────────────────────────────────────────────────────────────────────────

def test_invalid_preserves_original(tmp_path):
    """'25:00' 저장시도 시 ValidationError + 원본 바이트 불변 (AC-2).

    저장 전에 원본을 읽어 저장 후와 비교한다(spec: 잘못된 값은 거부됨).
    """
    editor, tdir, bdir = _make_editor(tmp_path)

    # 원본 파일 생성
    original_path = tdir / "713.json"
    _write_json(original_path, _VALID_DATA)
    original_bytes = original_path.read_bytes()

    # 잘못된 데이터로 save 시도
    with pytest.raises(ValidationError) as exc_info:
        editor.save("713", _INVALID_DATA)

    # ValidationError에 issues가 있어야 함
    assert len(exc_info.value.issues) > 0

    # 디스크 원본이 변경되지 않았어야 함
    assert original_path.read_bytes() == original_bytes, "원본 파일이 변경되면 안 됨"

    # 백업도 생성되면 안 됨 (validate 먼저이므로)
    assert list(bdir.glob("*.json")) == [], "검증 실패 시 백업이 생성되면 안 됨"


# ──────────────────────────────────────────────────────────────────────────
# test_atomic_rename: rename/write 실패 주입해도 원본 무손상
# ──────────────────────────────────────────────────────────────────────────

def test_atomic_rename(tmp_path):
    """atomic_write_json(save_timetable 경로) 실패 주입 시 원본 파일 무손상."""
    editor, tdir, bdir = _make_editor(tmp_path)

    original_path = tdir / "713.json"
    _write_json(original_path, _VALID_DATA)
    original_bytes = original_path.read_bytes()

    # bushexa.data.timetable 모듈이 fileio를 직접 임포트해 사용하므로
    # bushexa.data.timetable.fileio.atomic_write_json 에 실패 주입.
    with patch("bushexa.data.timetable.fileio.atomic_write_json",
               side_effect=OSError("disk full simulated")):
        with pytest.raises(OSError, match="disk full simulated"):
            editor.save("713", _VALID_DATA)

    # 원본 파일 무손상 확인
    assert original_path.read_bytes() == original_bytes, "rename 실패 후 원본이 손상되면 안 됨"


# ──────────────────────────────────────────────────────────────────────────
# 추가: 새 파일 저장 시 백업 없음
# ──────────────────────────────────────────────────────────────────────────

def test_save_new_file_no_backup(tmp_path):
    """기존 파일이 없으면 백업을 생성하지 않는다."""
    editor, tdir, bdir = _make_editor(tmp_path)
    # tdir에 713.json 미생성

    result = editor.save("713", _VALID_DATA)

    assert result.backup_path is None
    assert list(bdir.glob("*.json")) == []
    assert (tdir / "713.json").exists()


# ──────────────────────────────────────────────────────────────────────────
# validate — P1 위임 확인
# ──────────────────────────────────────────────────────────────────────────

def test_validate_delegates_to_p1(tmp_path):
    """validate가 P1 validate_timetable에 위임해 올바른 issue를 반환한다."""
    editor, _, _ = _make_editor(tmp_path)

    issues = editor.validate(_INVALID_DATA)

    # "25:00"은 out_of_range — P1 spec 상 코드
    assert any(i.code == "out_of_range" for i in issues), \
        f"out_of_range 이슈가 없음: {issues}"


def test_validate_valid_data_no_issues(tmp_path):
    """유효한 데이터에서 이슈가 없어야 한다."""
    editor, _, _ = _make_editor(tmp_path)

    issues = editor.validate(_VALID_DATA)

    assert issues == []


# ──────────────────────────────────────────────────────────────────────────
# list_routes — get_busroute_info 재사용
# ──────────────────────────────────────────────────────────────────────────

def test_list_routes_returns_summaries(tmp_path):
    """list_routes가 RouteSummary 목록을 반환하고 busno가 있어야 함."""
    editor, _, _ = _make_editor(tmp_path)

    routes = editor.list_routes()

    assert len(routes) > 0
    for r in routes:
        assert isinstance(r.busno, str)
        assert r.busno  # 비어 있지 않음


# ──────────────────────────────────────────────────────────────────────────
# load — 파일 읽기
# ──────────────────────────────────────────────────────────────────────────

def test_load_returns_timetable_data(tmp_path):
    """load가 JSON 파일을 읽어 TimetableData를 반환한다."""
    editor, tdir, _ = _make_editor(tmp_path)
    _write_json(tdir / "713.json", _VALID_DATA)

    data = editor.load("713")

    assert data == _VALID_DATA
