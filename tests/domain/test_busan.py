"""부산 가는 길 뷰모델 검증 — 주입한 도착·시간표·철도 데이터만 쓴다(네트워크·파일 없음)."""
from __future__ import annotations

from datetime import datetime

from bushexa.api_clients.ulsan_bis import Arrival
from bushexa.data.constants import BUSAN_513_ROUTE_ID
from bushexa.domain.busan import build_busan_snapshot
from bushexa.time_utils import KST

NOW = datetime(2026, 9, 30, 8, 0, tzinfo=KST)   # 수요일(평일)


def _provider(table):
    """{(busno, origin): [...]} 시간표 대역. 없는 키는 실제 provider 처럼 KeyError."""
    def provider(busno, weekday, origin):
        return table[(busno, origin)]
    return provider


def _day(*trains, suspect=False):
    rows = [{"no": f"{i:05d}", "grade": g, "dep": f"2026-09-30T{d}:00+09:00",
             "arr": f"2026-09-30T{a}:00+09:00", "charge": 7500} for i, (d, a, g) in enumerate(trains)]
    return {"fetched_at": "2026-09-30T02:30:00+09:00", "trains": rows, "suspect": suspect}


def _metro(*pairs, day_type="01"):
    return {"day_type": day_type, "run_minutes": 55.5,
            "trips": [{"dep": d, "arr": a, "end_name": "부전"} for d, a in pairs]}


BASE_TT = {("513", "덕하"): ["07:30", "08:20", "09:00"],
           ("743", "UNIST"): ["08:10"], ("753", "UNIST"): ["08:05"],
           ("713", "UNIST"): ["08:00"], ("1115", "UNIST"): ["09:00"]}


def test_live_513_picks_first_ktx_after_station_arrival_and_margin():
    """UNIST 5분 후 도착 513 → 울산역 08:21 → 10분 여유 뒤 첫 KTX(08:35)를 고른다. 08:29 는 놓친다."""
    snap = build_busan_snapshot(
        NOW, 0, timetable_provider=_provider(BASE_TT),
        unist_arrivals=[Arrival(BUSAN_513_ROUTE_ID, "진목회관", "울산70자1", 300),
                        Arrival("196000422", "구영리", "울산70자2", 120)],   # 반대 방향은 무시
        ktx_day=_day(("08:29", "08:50", "KTX"), ("08:35", "08:56", "KTX-산천")),
    )
    assert len(snap.ktx_live) == 1
    row = snap.ktx_live[0]
    assert (row.eta_min, row.unist_at, row.station_at) == (5, "08:05", "08:21")
    assert row.train.dep == "08:35" and row.train.arr == "08:56"


def test_513_origin_times_are_never_used_as_unist_times():
    """실시간이 없으면 덕하 출발 시각을 따로(라벨 대상) 돌려주고, UNIST 통과 행을 지어내지 않는다(D1)."""
    snap = build_busan_snapshot(NOW, 0, timetable_provider=_provider(BASE_TT),
                                ktx_day=_day(("08:29", "08:50", "KTX")))
    assert snap.ktx_live == []
    assert snap.origin_513 == ["08:20", "09:00"]      # 지금(08:00) 이후 덕하 출발만


def test_coupled_trains_shown_once_and_states():
    """같은 시각 중련 열차는 한 줄, 급감 표시(suspect)는 상태로 전달, 데이터가 없으면 missing."""
    snap = build_busan_snapshot(
        NOW, 0, timetable_provider=_provider(BASE_TT),
        ktx_day=_day(("21:49", "22:10", "KTX-산천"), ("21:49", "22:10", "KTX-산천(A-type)"), suspect=True))
    assert [t.dep for t in snap.ktx_trains] == ["21:49"]
    assert snap.ktx_state == "suspect"
    assert build_busan_snapshot(NOW, 0, timetable_provider=_provider(BASE_TT)).ktx_state == "missing"


def test_donghae_row_uses_route_median_and_walk_margin():
    """713 08:00 출발 → 평일 65분 → 태화강 09:05, 도보 5분 뒤 첫 동해선 09:18 → 벡스코·부전 도착을 잇는다."""
    snap = build_busan_snapshot(
        NOW, 0, timetable_provider=_provider(BASE_TT),
        metro_to_bexco=_metro(("09:02:00", "09:57:30"), ("09:18:00", "10:13:30")),
        metro_to_bujeon=_metro(("09:02:00", "10:18:00"), ("09:18:00", "10:39:30")),
    )
    row = next(r for r in snap.donghae if r.busno == "713")
    assert (row.unist_dep, row.taehwagang_at) == ("08:00", "09:05")
    assert (row.metro_dep, row.bexco_at, row.bujeon_at) == ("09:18", "10:13", "10:39")
    assert snap.metro_state == "ok"


def test_donghae_without_metro_data_has_no_connection_and_missing_state():
    """동해선 시간표가 없으면 '운행 없음'이 아니라 missing 상태이고 연결 열차를 지어내지 않는다."""
    snap = build_busan_snapshot(NOW, 0, timetable_provider=_provider(BASE_TT))
    assert snap.metro_state == "missing"
    assert snap.donghae and all(r.metro_dep is None for r in snap.donghae)


def test_saturday_metro_fallback_state():
    """토요일(weekday=1)에 휴일(03) 시간표가 쓰였으면 saturday_fallback 으로 알린다."""
    snap = build_busan_snapshot(NOW, 1, timetable_provider=_provider(BASE_TT),
                                metro_to_bexco=_metro(("09:18:00", "10:13:30"), day_type="03"))
    assert snap.metro_state == "saturday_fallback"


def test_missing_timetable_file_does_not_raise():
    """시간표 파일·키가 없어도 예외 없이 빈 목록과 오류 메모로 처리한다(500 금지)."""
    def broken(busno, weekday, origin):
        raise FileNotFoundError(busno)
    snap = build_busan_snapshot(NOW, 0, timetable_provider=broken)
    assert snap.origin_513 == [] and snap.nopo_buses == [] and snap.donghae == []
    assert snap.errors


def test_nopo_lists_743_753_unist_departures_in_time_order():
    """노포 루트는 743·753 UNIST 출발을 시각순으로 합친다."""
    snap = build_busan_snapshot(NOW, 0, timetable_provider=_provider(BASE_TT))
    assert [(r.busno, r.unist_dep) for r in snap.nopo_buses] == [("753", "08:05"), ("743", "08:10")]
