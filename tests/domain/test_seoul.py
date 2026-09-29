"""서울 가는 길 뷰모델 검증 — 513 실시간 연결, 덕하 기점 분리(D1), 행선 필터."""
from __future__ import annotations

from datetime import datetime

from bushexa.api_clients.ulsan_bis import Arrival
from bushexa.data.constants import BUSAN_513_ROUTE_ID, RAIL_SEOUL, RAIL_SUSEO, RAIL_ULSAN
from bushexa.domain.seoul import build_seoul_snapshot
from bushexa.time_utils import KST

NOW = datetime(2026, 9, 30, 8, 0, tzinfo=KST)


def _day(*deps):
    return {"trains": [{"grade": "KTX", "dep": f"2026-09-30T{d}:00+09:00",
                        "arr": f"2026-09-30T{a}:00+09:00"} for d, a in deps]}


def _snap(**kw):
    base = dict(timetable_provider=lambda b, w, o: ["07:30", "08:20"],
                seoul_day=_day(("08:10", "10:30"), ("08:40", "11:00")),
                suseo_day=_day(("08:30", "10:40"), ("09:00", "11:10")),
                seoul_ids=(RAIL_ULSAN, RAIL_SEOUL), suseo_ids=(RAIL_ULSAN, RAIL_SUSEO))
    base.update(kw)
    return build_seoul_snapshot(NOW, 0, **base)


def test_live_513_connects_first_seoul_and_suseo_trains_and_marks_board():
    """UNIST 3분 후 513 → 울산역 08:19 → 08:29 이후 첫 서울행(08:40)·수서행(08:30), 안내판 첫 연결 열차 표시."""
    snap = _snap(unist_arrivals=[Arrival(BUSAN_513_ROUTE_ID, "진목회관", "울산70자1", 180)])
    bus = snap.live[0]
    assert (bus.unist_at, bus.station_at) == ("08:03", "08:19")
    assert bus.seoul.dep == "08:40" and bus.suseo.dep == "08:30"
    assert [t.dep for t in snap.board if t.connect] == ["08:30"]


def test_no_live_bus_keeps_origin_times_separate():
    """실시간이 없으면 연결 행을 만들지 않고, 덕하 출발 시각은 따로(라벨 대상) 돌려준다(D1)."""
    snap = _snap()
    assert snap.live == [] and snap.origin_513 == ["08:20"]
    assert not any(t.connect for t in snap.board)


def test_destination_filter_and_missing_state():
    """?to=suseo 는 수서행만, 알 수 없는 값은 전체. 데이터가 없는 행선은 missing 상태."""
    assert {t.dest for t in _snap(dest="suseo").board} == {"수서"}
    assert _snap(dest="nope").dest == "all"
    assert _snap(seoul_day=None).states["서울"] == "missing"
