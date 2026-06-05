"""W2a recorder 격리 검증 (H4 회귀). 기대값은 주입한 응답·결함에서 직접 도출(E-13)."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from bushexa.crawler.recorder import GovtrackRecorder
from bushexa.crawler.state import VehicleTimeline
from tests.crawler._fakes import FakeTagoClient, FaultyState, make_response

KST = ZoneInfo("Asia/Seoul")


class _Clock:
    def now(self):
        return datetime(2026, 6, 1, 8, 0, 0, tzinfo=KST)


def test_one_vehicle_failure_no_cascade():
    """두 차량 중 첫 차량 처리에서 state가 예외를 던져도 두 번째 차량은 여전히 INSERT 후보가
    되는지 검증한다 — H4(예외 격리) 회귀. (try/except 제거 시 예외가 전파되어 실패한다.)"""
    # 두 차량 모두 추적 정류장 999000149(195000177 노선)에 있음.
    resp = make_response([
        ("999000149", "명촌", "veh-A"),  # state.record가 예외를 던질 차량
        ("999000149", "명촌", "veh-B"),  # 정상 처리되어야 할 차량
    ])
    client = FakeTagoClient(by_route={"195000177": resp})
    state = FaultyState(fail_vehicle="veh-A")
    recorder = GovtrackRecorder(
        client, state, repo=None, clock=_Clock(),
        tracked_stops_by_route={"195000177": {"999000149"}},
        stop_names={"999000149": "명촌 (기점)"},
    )

    stats, candidates = recorder.run_single_route("195000177")

    assert stats.vehicle_errors == 1               # veh-A는 격리된 실패
    assert stats.inserts == 1                       # veh-B만 후보로 남음
    assert [c.vehicle_no for c in candidates] == ["veh-B"]
    assert candidates[0].stop_id == "999000149"


def test_untracked_stop_skipped():
    """차량이 추적 대상이 아닌 nodeid에 있으면 INSERT가 발생하지 않고 timeline만 갱신되는지."""
    resp = make_response([("888888888", "비추적정류장", "veh-Y")])
    client = FakeTagoClient(by_route={"195000177": resp})
    state = VehicleTimeline()
    recorder = GovtrackRecorder(
        client, state, repo=None, clock=_Clock(),
        tracked_stops_by_route={"195000177": {"999000149"}},  # 888…은 미추적
    )

    stats, candidates = recorder.run_single_route("195000177")

    assert candidates == []
    assert stats.inserts == 0
    assert stats.skipped_unknown_stop == 1
    # timeline은 갱신되어, 다음 사이클 같은 위치는 'unchanged'로 처리된다.
    assert state.last_node("195000177", "veh-Y") == "888888888"
