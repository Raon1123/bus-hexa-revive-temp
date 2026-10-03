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


def _arr(route_id, seconds, vno="울산71자0000"):
    return Arrival(route_id=route_id, present_stop="삼호교", vehicle_no=vno, arrival_time=seconds)


def test_nopo_live_1224_at_transfer_stop_only_nopo_direction():
    """좋은삼정병원앞 도착 캐시에서 1224 노포 방면(195000247)만 골라 시각순으로 보인다. 다른 노선은 제외."""
    snap = build_busan_snapshot(
        NOW, 0, timetable_provider=_provider(BASE_TT),
        transfer_arrivals=[_arr("195000247", 900), _arr("196000374", 60), _arr("195000247", 300)],
    )
    assert [(b.at, b.eta_min) for b in snap.nopo_1224] == [("08:05", 5), ("08:15", 15)]


def test_nopo_live_transfer_catches_first_1224_after_feeder_with_margin():
    """743 이 4분 후 좋은삼정병원앞에 서면, 1분 여유 뒤 오는 첫 1224(6분 후)를 잇는다. 4분 30초 후 1224 는 놓친다."""
    snap = build_busan_snapshot(
        NOW, 0, timetable_provider=_provider(BASE_TT),
        transfer_arrivals=[_arr("195000216", 240), _arr("195000247", 270), _arr("195000247", 360),
                           _arr("195000222", 1200)],
    )
    rows = [(r.busno, r.feeder.at, r.bus_1224.at if r.bus_1224 else None) for r in snap.nopo_live]
    assert rows == [("743", "08:04", "08:06"), ("753", "08:20", None)]


def test_nopo_live_ignores_uni_direction_feeders():
    """743·753 UNIST 방면 route_id 는 환승 연결에 넣지 않는다(노포 방면 정류장이 아님)."""
    snap = build_busan_snapshot(
        NOW, 0, timetable_provider=_provider(BASE_TT),
        transfer_arrivals=[_arr("195000215", 120), _arr("195000221", 180)],
    )
    assert snap.nopo_live == [] and snap.nopo_1224 == []


PLAN_TT = {**BASE_TT, ("1224", "농소"): ["08:10", "08:25", "08:40", "09:00"]}


def test_nopo_plan_links_743_to_first_1224_after_estimated_arrival_with_margin():
    """743(UNIST 08:10)은 35분 뒤 08:45 좋은삼정병원앞에 서고, 1224(농소 출발+35분)는 여유 3분 뒤인 08:48 이후 첫 차(농소 08:25 출발 → 09:00 통과)를 잇는다."""
    snap = build_busan_snapshot(NOW, 0, timetable_provider=_provider(PLAN_TT))
    row = next(r for r in snap.nopo_plan if r.busno == "743")
    assert (row.unist_dep, row.feeder_at, row.bus_1224_at, row.wait_min) == ("08:10", "08:45", "09:00", 15)
    assert not row.feeder_live and not row.bus_1224_live


def test_nopo_plan_uses_live_arrival_when_close_to_estimate():
    """예상 08:45 근처(6분 이내)에 실시간 743 이 있으면 그 시각(08:43)으로 바꾸고, 1224 도 실시간 08:50 을 잇는다."""
    snap = build_busan_snapshot(
        NOW, 0, timetable_provider=_provider(PLAN_TT),
        transfer_arrivals=[_arr("195000216", 43 * 60), _arr("195000247", 50 * 60)],
    )
    row = next(r for r in snap.nopo_plan if r.busno == "743")
    assert (row.feeder_at, row.feeder_live, row.bus_1224_at, row.bus_1224_live) == ("08:43", True, "08:50", True)


def test_nopo_plan_without_1224_timetable_still_lists_feeders():
    """1224 시간표 파일이 없어도 환승 줄은 만들고 1224 칸만 비운다(500 금지)."""
    snap = build_busan_snapshot(NOW, 0, timetable_provider=_provider(BASE_TT))
    assert snap.nopo_plan and all(r.bus_1224_at is None for r in snap.nopo_plan)
