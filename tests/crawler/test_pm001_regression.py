"""PM-001 봉인 회귀: 사용자 보고 '버스 통과 기록이 bus_timelog에 제대로 안 남는다'가 고쳐졌는지.

세 가지를 한 곳에서 증명한다:
1. 통과가 실제로 bus_timelog에 누적되고 중복은 억제된다(핵심 결함 회복).
2. 재시작 시 warm_from_repo가 직전 위치를 적재해 false-positive를 억제한다(H2).
3. (대조) warm이 없으면 재시작 첫 사이클이 통과하지도 않은 시각으로 오기록한다 — warm이
   load-bearing임을 보여 2번이 tautology가 아님을 입증한다.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from bushexa.crawler.recorder import GovtrackRecorder
from bushexa.crawler.state import VehicleTimeline
from bushexa.db.connection import create_connection
from bushexa.db.repo import BusLogRepo
from bushexa.db.schema import create_schema
from tests.crawler._fakes import FakeTagoClient, SequenceTagoClient, make_response

KST = ZoneInfo("Asia/Seoul")
ROUTE = "195000177"
TRACKED = {"999000149", "193012314", "193040420"}


class _Clock:
    def now(self):
        return datetime(2026, 6, 1, 8, 0, 0, tzinfo=KST)


def _repo():
    conn = create_connection("sqlite:///:memory:")
    create_schema(conn)
    return BusLogRepo(conn)


def _recorder(client, state, repo):
    return GovtrackRecorder(
        client, state, repo, _Clock(),
        tracked_stops_by_route={ROUTE: set(TRACKED)},
        stop_names={"999000149": "명촌", "193012314": "태화강역", "193040420": "터미널"},
    )


def test_passages_are_logged_to_bus_timelog():
    """차량이 추적 정류장 A→B→(정차)→C를 지나면 bus_timelog에 3개 통과가 기록되고,
    같은 위치 연속(정차)은 중복 INSERT되지 않는지 검증한다 — PM-001 핵심 결함 회복."""
    repo = _repo()
    state = VehicleTimeline()
    client = SequenceTagoClient([
        make_response([("999000149", "명촌", "veh-A")]),       # cycle1: A
        make_response([("193012314", "태화강역", "veh-A")]),   # cycle2: B (변경)
        make_response([("193012314", "태화강역", "veh-A")]),   # cycle3: B (정차 → 중복 억제)
        make_response([("193040420", "터미널", "veh-A")]),     # cycle4: C (변경)
    ])
    recorder = _recorder(client, state, repo)

    for _ in range(4):
        recorder.run_cycle()

    rows = repo.get_by_route(ROUTE)
    assert repo.count() == 3                                    # 통과 3건만(중복 없음)
    assert [r.stop_id for r in rows] == ["999000149", "193012314", "193040420"]
    assert [r.vehicle_no for r in rows] == ["veh-A"] * 3


def test_restart_warm_suppresses_false_positive():
    """재시작 시 DB의 직전 위치를 warm_from_repo로 적재하면, 첫 폴링에서 차량이 그 위치
    그대로일 때 INSERT가 0건이어서 통과시각 오기록이 없는지 검증한다 — H2/AC-H2 회귀."""
    repo = _repo()
    # 기존 운영 기록: 차량 A가 999000149를 통과한 적 있음.
    repo.insert_log(idx="20260601_07:59:00", stop_id="999000149", route_id=ROUTE,
                    vehicle_no="veh-A", stop_name="명촌")
    before = repo.count()

    # 새 데몬 인스턴스: 빈 timeline → warm으로 직전 위치 적재.
    state = VehicleTimeline()
    state.warm_from_repo(repo, since=datetime(2026, 6, 1, 7, 0, 0, tzinfo=KST))
    client = FakeTagoClient(by_route={ROUTE: make_response([("999000149", "명촌", "veh-A")])})
    recorder = _recorder(client, state, repo)

    cyc = recorder.run_cycle()

    assert cyc.total_inserts == 0       # 변경 아님 → 오기록 0건
    assert repo.count() == before       # DB 행 수 불변


def test_without_warm_would_false_positive():
    """(대조) warm 없이 빈 timeline으로 재시작하면 첫 폴링이 현재 위치를 '신규'로 보고 즉시
    INSERT해 false-positive가 발생함을 보여, warm이 실제로 결함을 막고 있음을 입증한다."""
    repo = _repo()
    repo.insert_log(idx="20260601_07:59:00", stop_id="999000149", route_id=ROUTE,
                    vehicle_no="veh-A", stop_name="명촌")
    before = repo.count()

    state = VehicleTimeline()  # warm_from_repo 호출하지 않음 (버그 재현)
    client = FakeTagoClient(by_route={ROUTE: make_response([("999000149", "명촌", "veh-A")])})
    recorder = _recorder(client, state, repo)

    cyc = recorder.run_cycle()

    assert cyc.total_inserts == 1       # warm 없으면 오기록 발생
    assert repo.count() == before + 1
