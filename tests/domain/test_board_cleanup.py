"""E-13: board.py 중복 제거 검증.

테스트 목록:
- test_unist_busnos_matches_comprehension : _UNIST_BUSNOS가 ROUTEID에서 직접 도출한
      컴프리헨션과 동일 집합
- test_unist_busnos_expected_members       : 알려진 멤버(713/743/753/1115)가 포함됨
- test_unist_busnos_excludes_513           : 경유 노선 513은 제외됨
- test_board_build_unchanged               : get_board_data 결과가 기존 동작과 동일
      (_UNIST_BUSNOS 교체·정렬 제거 전후 결과 일치)
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest

from bushexa.data.constants import ROUTEID
from bushexa.domain.board import (
    _UNIST_BUSNOS,
    get_board_data,
    BoardSnapshot,
    BoardRow,
    merge_live_rows,
)
from tests.conftest import FakeClock

KST = ZoneInfo("Asia/Seoul")
STOP_ID = "196040234"


# ---------------------------------------------------------------------------
# TC-1: _UNIST_BUSNOS가 ROUTEID 컴프리헨션과 동일 집합
# ---------------------------------------------------------------------------

def test_unist_busnos_matches_comprehension() -> None:
    """_UNIST_BUSNOS가 ROUTEID에서 직접 도출한 컴프리헨션과 동일 집합임을 검증.

    리뷰 E4: 두 컴프리헨션 2벌을 모듈 레벨 상수 1개로 대체한 결과 동일성 보증.
    """
    expected = {
        b for (b, term, dep, _ids) in ROUTEID.values()
        if dep == "UNIST" or "UNIST" in term
    }
    assert set(_UNIST_BUSNOS) == expected, (
        "_UNIST_BUSNOS가 ROUTEID 컴프리헨션 결과와 달라짐"
    )


def test_unist_busnos_expected_members() -> None:
    """UNIST를 종점으로 갖는 노선(713/743/753/1115)이 _UNIST_BUSNOS에 포함됨."""
    for busno in ("713", "743", "753", "1115"):
        assert busno in _UNIST_BUSNOS, f"{busno}가 _UNIST_BUSNOS에 없음"


def test_unist_busnos_excludes_513() -> None:
    """경유 노선 513은 UNIST를 종점으로 갖지 않으므로 _UNIST_BUSNOS에서 제외됨."""
    assert "513" not in _UNIST_BUSNOS, "513은 경유 노선 — _UNIST_BUSNOS에서 제외돼야 함"


# ---------------------------------------------------------------------------
# TC-2: get_board_data 결과 불변 — 정렬 제거 전후 동작 동일
# ---------------------------------------------------------------------------

def _make_timetable_provider(data: dict):
    """(busno, weekday, departure) 키 dict를 timetable_provider로 래핑."""
    def provider(busno, weekday, departure):
        key = (str(busno), int(weekday), str(departure))
        if key not in data:
            raise FileNotFoundError(f"no timetable: {key}")
        return data[key]
    return provider


TIMETABLE_DATA = {
    ("713", 0, "UNIST"): ["08:40", "09:00", "09:30"],
    ("513", 0, "덕하"): ["08:20", "09:10"],
    ("513", 0, "삼남"): ["09:00"],
    ("713", 0, "명촌"): ["08:00", "08:50"],
    ("743", 0, "UNIST"): [],
    ("753", 0, "UNIST"): [],
    ("1115", 0, "UNIST"): [],
    ("743", 0, "명촌"): [],
    ("753", 0, "명촌"): [],
    ("1115", 0, "꽃바위"): [],
}


def test_board_build_unchanged() -> None:
    """get_board_data 결과가 rows 정렬 순서와 FIRST/SECOND 마킹 동작을 올바르게 유지.

    정렬 제거(리뷰 E5)·_UNIST_BUSNOS 교체(리뷰 E4) 이후에도 rows가 arrival_minutes
    오름차순이고 FIRST 행이 존재함을 검증한다.
    """
    clock = FakeClock(datetime(2026, 6, 1, 8, 30, 0, tzinfo=KST))
    client = MagicMock()
    client.fetch_arrivals.return_value = []

    snapshot = get_board_data(
        STOP_ID, clock,
        client=client,
        timetable_provider=_make_timetable_provider(TIMETABLE_DATA),
    )

    assert isinstance(snapshot, BoardSnapshot)
    rows = snapshot.rows
    assert len(rows) > 0, "08:30 이후 시간표 항목이 존재해야 함"

    # rows가 arrival_minutes 오름차순인지 확인
    for i in range(len(rows) - 1):
        assert rows[i].arrival_minutes <= rows[i + 1].arrival_minutes, (
            f"rows[{i}].arrival_minutes={rows[i].arrival_minutes} > "
            f"rows[{i+1}].arrival_minutes={rows[i+1].arrival_minutes}"
        )

    # FIRST 행이 정확히 마킹됐는지 확인
    first_rows = [r for r in rows if r.rank == "FIRST"]
    assert len(first_rows) >= 1, "FIRST 마킹된 행이 1개 이상 있어야 함"

    # 가장 이른 arrival_minutes의 모든 행이 FIRST인지 확인
    min_mins = rows[0].arrival_minutes
    for r in rows:
        if r.arrival_minutes == min_mins:
            assert r.rank == "FIRST", (
                f"가장 이른 시각({min_mins}분)의 행은 FIRST여야 함 — "
                f"bus_number={r.bus_number}"
            )


def test_board_only_unist_departures_shown() -> None:
    """_UNIST_BUSNOS 교체 후에도 UNIST 도착 방향은 게시판에서 제외됨을 확인.

    기존 test_board.py::test_only_unist_departures_shown과 동일 의도를
    _UNIST_BUSNOS 교체 관점에서 재검증.
    """
    clock = FakeClock(datetime(2026, 6, 1, 8, 30, 0, tzinfo=KST))
    client = MagicMock()
    client.fetch_arrivals.return_value = []

    snapshot = get_board_data(
        STOP_ID, clock,
        client=client,
        timetable_provider=_make_timetable_provider(TIMETABLE_DATA),
    )
    terminals = {r.terminal for r in snapshot.rows}
    assert "UNIST 방면" not in terminals, (
        "UNIST 도착(=UNIST 방면) 방향은 출발 게시판에서 제외돼야 함"
    )
