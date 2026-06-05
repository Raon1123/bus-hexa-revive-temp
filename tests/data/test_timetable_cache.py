"""E-13: get_timetable mtime 기반 캐시 검증.

테스트 목록:
- test_cache_hit_no_reopen   : 같은 mtime/size면 두 번째 호출에서 파일을 다시 열지 않음
- test_cache_invalidation    : atomic_write(os.replace) 교체 후 새 내용을 반환
- test_fnf_preserved         : 파일 없으면 FileNotFoundError 유지 (호출자 계약 불변)
- test_clear_cache_helper    : _clear_cache()가 내부 캐시를 비움을 확인
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from unittest.mock import patch, call

import pytest

from bushexa.data import timetable as tt


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------

def _write_json(p: Path, obj: dict) -> None:
    """원자적 쓰기 시뮬레이션 — tmp→os.replace 패턴(fileio.atomic_write_json과 동일)."""
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)


# 각 테스트는 tmp_path가 다르므로 캐시 키 충돌 없음.
# 명시적 격리를 위해 autouse fixture로 캐시를 비움.
@pytest.fixture(autouse=True)
def _isolated_cache():
    """각 테스트 전·후 캐시를 초기화해 테스트 간 캐시 오염을 방지."""
    tt._clear_cache()
    yield
    tt._clear_cache()


# ---------------------------------------------------------------------------
# TC-1: 캐시 히트 — 두 번째 호출에서 open()을 호출하지 않음
# ---------------------------------------------------------------------------

def test_cache_hit_no_reopen(tmp_path: Path) -> None:
    """같은 파일을 두 번 호출하면 두 번째 호출에서 open()이 실행되지 않음을 확인.

    monkeypatch로 open을 래핑해 호출 횟수를 센다. 실제 파일 I/O는 통과시켜
    첫 번째 로드는 정상 동작하게 한다.
    """
    timetable_file = tmp_path / "713.json"
    _write_json(timetable_file, {"0": {"UNIST": ["07:00", "08:00"]}, "1": {}, "2": {}})

    open_count = 0
    _real_open = open  # 원본 참조 보관

    def _counting_open(path, *args, **kwargs):
        nonlocal open_count
        # 대상 파일에 대한 open()만 카운트
        if os.path.abspath(str(path)) == os.path.abspath(str(timetable_file)):
            open_count += 1
        return _real_open(path, *args, **kwargs)

    with patch("builtins.open", side_effect=_counting_open):
        result1 = tt.get_timetable("713", 0, "UNIST", dir=tmp_path)
        open_count_after_first = open_count
        result2 = tt.get_timetable("713", 0, "UNIST", dir=tmp_path)
        open_count_after_second = open_count

    assert result1 == ["07:00", "08:00"]
    assert result2 == ["07:00", "08:00"]
    assert open_count_after_first == 1, "첫 번째 호출은 파일을 1회 열어야 함"
    assert open_count_after_second == 1, "두 번째 호출(캐시 히트)은 파일을 다시 열면 안 됨"


# ---------------------------------------------------------------------------
# TC-2: 캐시 무효화 — os.replace(atomic) 교체 후 새 내용 반환
# ---------------------------------------------------------------------------

def test_cache_invalidation(tmp_path: Path) -> None:
    """파일을 atomic replace로 교체하면 다음 호출에서 새 내용을 반환함.

    주의: 교체 전·후 파일 크기를 다르게 해 (mtime_ns, size) 서명이 반드시 변하도록 한다
    (동일 타임스탬프 + 동일 크기 충돌 방어).
    """
    timetable_file = tmp_path / "513.json"
    # 초기 내용 — 3건
    _write_json(timetable_file, {"0": {"덕하": ["06:00", "07:00", "08:00"]}})

    first_result = tt.get_timetable("513", 0, "덕하", dir=tmp_path)
    assert first_result == ["06:00", "07:00", "08:00"]

    # atomic replace — 다른 크기(2건)로 교체해 서명 변경을 보장
    _write_json(timetable_file, {"0": {"덕하": ["09:00", "10:00"]}})

    second_result = tt.get_timetable("513", 0, "덕하", dir=tmp_path)
    assert second_result == ["09:00", "10:00"], (
        "atomic replace 후 캐시가 무효화되어 새 내용을 반환해야 함"
    )


# ---------------------------------------------------------------------------
# TC-3: FileNotFoundError 계약 유지
# ---------------------------------------------------------------------------

def test_fnf_preserved(tmp_path: Path) -> None:
    """존재하지 않는 파일 조회 시 FileNotFoundError가 발생함 (호출자 계약 불변)."""
    with pytest.raises(FileNotFoundError):
        tt.get_timetable("999", 0, "없는기점", dir=tmp_path)


# ---------------------------------------------------------------------------
# TC-4: _clear_cache 헬퍼 동작 확인
# ---------------------------------------------------------------------------

def test_clear_cache_helper(tmp_path: Path) -> None:
    """_clear_cache() 호출 후 캐시가 비어 다음 호출이 파일을 다시 읽음을 확인."""
    timetable_file = tmp_path / "743.json"
    _write_json(timetable_file, {"0": {"UNIST": ["05:30"]}})

    # 1회 로드해 캐시 채움
    tt.get_timetable("743", 0, "UNIST", dir=tmp_path)
    assert len(tt._cache) > 0, "로드 후 캐시에 1개 이상의 항목이 있어야 함"

    # 캐시 비움
    tt._clear_cache()
    assert len(tt._cache) == 0, "_clear_cache() 후 캐시가 비어야 함"


# ---------------------------------------------------------------------------
# TC-5: 반환 리스트 변형이 캐시를 오염시키지 않음
# ---------------------------------------------------------------------------

def test_return_list_isolation(tmp_path: Path) -> None:
    """반환된 리스트를 변형(append/sort)해도 캐시 내부가 오염되지 않음.

    리뷰 #2 캐시 오염 재발 방지: list() 얕은 복사 효과 검증.
    """
    timetable_file = tmp_path / "753.json"
    _write_json(timetable_file, {"0": {"UNIST": ["07:00", "08:00"]}})

    result1 = tt.get_timetable("753", 0, "UNIST", dir=tmp_path)
    # 반환된 리스트를 변형
    result1.append("23:59")
    result1.sort()

    # 두 번째 호출 — 캐시에서 읽어야 하며 오염되지 않아야 함
    result2 = tt.get_timetable("753", 0, "UNIST", dir=tmp_path)
    assert result2 == ["07:00", "08:00"], (
        "반환 리스트 변형이 캐시를 오염시키면 안 됨 (리뷰 #2 방어)"
    )
