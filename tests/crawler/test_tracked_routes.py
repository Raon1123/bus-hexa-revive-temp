"""수집 전용 노선(EXTRA_TRACKED_ROUTES, 1224) — govtrack 은 따라가고 UNIST 화면에는 섞이지 않는다."""
from __future__ import annotations

from bushexa.data.constants import (
    BUSAN_1224_ROUTE_ID,
    BUSAN_NOPO_TRANSFER_STOP_ID,
    EXTRA_TRACKED_ROUTES,
    ROUTEID,
    STOP_IDS,
    TRACKED_ROUTES,
)
from bushexa.crawler.daemon import tracked_stops_by_route


def test_govtrack_tracks_1224_both_directions():
    """govtrack 추적 목록에 1224 양방향이 들어가고, 노포 방면은 좋은삼정병원앞 통과를 기록한다."""
    tracked = tracked_stops_by_route()
    assert {"195000247", "195000248"} <= set(tracked)
    assert BUSAN_NOPO_TRANSFER_STOP_ID in tracked[BUSAN_1224_ROUTE_ID]
    assert set(ROUTEID) <= set(tracked)


def test_extra_routes_stay_out_of_unist_routeid():
    """1224 는 ROUTEID(게시판·시간표·/stops 기준)에 들어가지 않는다 — UNIST 경유 노선이 아니다."""
    assert not set(EXTRA_TRACKED_ROUTES) & set(ROUTEID)
    assert all(meta[0] != "1224" for meta in ROUTEID.values())
    assert TRACKED_ROUTES == {**ROUTEID, **EXTRA_TRACKED_ROUTES}


def test_extra_route_stops_have_names():
    """추적 정류장마다 STOP_IDS 명칭이 있어 /running 과 울산 폴백 이름 역매핑이 동작한다."""
    missing = [sid for meta in EXTRA_TRACKED_ROUTES.values() for sid in meta[3] if not STOP_IDS.get(sid)]
    assert missing == []


def test_running_reconstructs_1224_runs():
    """운행 재구성(parse_runs)은 1224 기록을 모르는 노선으로 버리지 않고 차량별 회차로 묶는다."""
    from bushexa.db.repo import LogRow
    from bushexa.domain.running import explain_runs

    rows = [LogRow(idx="20260930_15:22:23", stop_id="193030929", route_id="195000247",
                   route_nm="1224", vehicle_no="울산71자2006", stop_name="좋은삼정병원앞"),
            LogRow(idx="20260930_15:24:10", stop_id="193030707", route_id="195000247",
                   route_nm="1224", vehicle_no="울산71자2006", stop_name="울산대학교 (시내)")]
    ex = explain_runs(rows, "195000247")
    assert not ex.unknown_route
    assert [r.stops for r in ex.runs] == [{"193030929": "15:22", "193030707": "15:24"}]
