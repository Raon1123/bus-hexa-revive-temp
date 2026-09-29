"""역 발차 안내판 행·정차역 띠 검증 (순수 함수)."""
from __future__ import annotations

from datetime import datetime

from bushexa.data.constants import RAIL_BUSAN, RAIL_SEOUL, RAIL_ULSAN
from bushexa.domain.rail_board import board_trains
from bushexa.time_utils import KST

NOW = datetime(2026, 9, 30, 21, 40, tzinfo=KST)


def _t(dep, arr, grade="KTX", stops="absent", arr_date="2026-09-30"):
    row = {"grade": grade, "dep": f"2026-09-30T{dep}:00+09:00", "arr": f"{arr_date}T{arr}:00+09:00"}
    if stops != "absent":
        row["stops"] = stops
    return row


def test_strip_lights_stopping_stations_in_route_order():
    """정차역 띠는 후보역 전체를 운행 순서로 늘어놓고, 선 역만 불을 켠다(도착 시각 포함)."""
    day = {"trains": [_t("21:51", "00:11", stops=[{"name": "동대구", "arr": "22:19"},
                                                 {"name": "대전", "arr": "23:08"}], arr_date="2026-10-01")]}
    rows, state = board_trains(day, NOW, RAIL_ULSAN, RAIL_SEOUL)
    assert state == "ok"
    tr = rows[0]
    assert tr.next_day is True and tr.minutes_left == 11 and not tr.soon
    names = [s.name for s in tr.strip]
    assert names[:3] == ["경주", "동대구", "서대구"]
    lit = [(s.name, s.time) for s in tr.strip if s.stops]
    assert lit == [("동대구", "22:19"), ("대전", "23:08")]


def test_unknown_stops_are_not_drawn_as_passing():
    """정차역 조회가 실패(None)했거나 저장이 없으면 띠를 None 으로 둬 '통과'로 그리지 않는다."""
    day = {"trains": [_t("21:51", "23:50", stops=None), _t("22:04", "23:59")]}
    rows, _ = board_trains(day, NOW, RAIL_ULSAN, RAIL_SEOUL)
    assert [r.strip for r in rows] == [None, None]


def test_pair_without_candidates_gets_empty_strip_and_soon_flag():
    """중간 정차역 후보가 없는 구간(울산→부산)은 빈 띠, 10분 안에 떠나면 곧 출발."""
    rows, _ = board_trains({"trains": [_t("21:45", "22:06")]}, NOW, RAIL_ULSAN, RAIL_BUSAN)
    assert rows[0].strip == () and rows[0].soon is True


def test_departed_and_coupled_trains_filtered():
    """이미 떠난 열차는 빼고, 같은 시각 중련은 한 줄만 남긴다. 데이터가 없으면 missing."""
    day = {"trains": [_t("21:30", "21:51"), _t("21:49", "22:10", "KTX-산천"),
                      _t("21:49", "22:10", "KTX-산천(A-type)")], "suspect": True}
    rows, state = board_trains(day, NOW, RAIL_ULSAN, RAIL_BUSAN)
    assert [r.dep for r in rows] == ["21:49"] and state == "suspect"
    assert board_trains(None, NOW, RAIL_ULSAN, RAIL_BUSAN) == ([], "missing")
