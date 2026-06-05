"""W2a 미등록 정류장 안전 처리 (H3 회귀). 기대값은 주입한 응답에서 직접 도출(E-13)."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from bushexa.crawler.recorder import GovtrackRecorder
from bushexa.crawler.state import VehicleTimeline
from tests.crawler._fakes import FakeTagoClient, make_response

KST = ZoneInfo("Asia/Seoul")


class _Clock:
    def now(self):
        return datetime(2026, 6, 1, 8, 0, 0, tzinfo=KST)


def test_unknown_stop_inserts_null_name():
    """tracked_stops에는 있으나 STOP_IDS에 없는 nodeid를 차량이 통과할 때 KeyError 없이
    stop_name=None으로 INSERT 후보가 되는지 검증한다 — H3 회귀."""
    unknown_node = "195030615"  # tracked로 둘 것이나 stop_names에는 일부러 누락
    resp = make_response([(unknown_node, "신규정류장", "veh-Z")])
    client = FakeTagoClient(by_route={"194000107": resp})
    recorder = GovtrackRecorder(
        client, VehicleTimeline(), repo=None, clock=_Clock(),
        tracked_stops_by_route={"194000107": {unknown_node}},
        stop_names={},  # 비어 있음 → .get(unknown) == None (KeyError 아님)
    )

    stats, candidates = recorder.run_single_route("194000107")

    assert stats.inserts == 1
    assert len(candidates) == 1
    assert candidates[0].stop_id == unknown_node
    assert candidates[0].stop_name is None  # 미등록이어도 None으로 안전 기록
