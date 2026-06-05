"""W2c API 연속 실패 alert (H6 회귀). 기대값은 주입한 사이클 시퀀스에서 직접 도출(E-13)."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from bushexa.api_clients.errors import TagoError
from bushexa.crawler.recorder import GovtrackRecorder
from bushexa.crawler.state import VehicleTimeline
from tests.crawler._fakes import FakeTagoClient, SequenceTagoClient, make_response

KST = ZoneInfo("Asia/Seoul")


class _Clock:
    def now(self):
        return datetime(2026, 6, 1, 8, 0, 0, tzinfo=KST)


def _recorder(client, alerts, threshold=5):
    return GovtrackRecorder(
        client, VehicleTimeline(), repo=None, clock=_Clock(),
        tracked_stops_by_route={"195000177": {"999000149"}},
        stop_names={"999000149": "명촌"},
        alert_hook=lambda rid, n: alerts.append((rid, n)),
        alert_threshold=threshold,
    )


def test_five_consecutive_failures_trigger_alert():
    """mock client가 5사이클 연속 result_code='99'(TagoError)를 반환할 때 alert_hook이
    정확히 1회만 호출되는지 검증한다 — H6(침묵 실패 방지) 회귀."""
    alerts: list[tuple[str, int]] = []
    client = FakeTagoClient(raise_exc=TagoError("99"))
    recorder = _recorder(client, alerts)

    for _ in range(7):  # 7사이클 연속 실패
        recorder.run_cycle()

    assert alerts == [("195000177", 5)]  # 5사이클째 1회만, 이후 중복 없음


def test_success_resets_counter():
    """4회 실패 후 1회 성공하면 연속 카운터가 0으로 리셋되어, 이어진 4회 실패로도 alert가
    호출되지 않는지 검증한다 — H6 리셋. (리셋 제거 시 두 번째 그룹에서 5연속 도달→발화)"""
    alerts: list[tuple[str, int]] = []
    success = make_response([("888888888", "비추적", "veh-A")])  # 성공이지만 미추적 → INSERT 없음(repo 불필요)
    seq = [TagoError("99")] * 4 + [success] + [TagoError("99")] * 4
    recorder = _recorder(SequenceTagoClient(seq), alerts)

    for _ in range(len(seq)):  # 4 실패 + 1 성공 + 4 실패 = 9사이클
        recorder.run_cycle()

    assert alerts == []  # 연속 실패가 5에 도달한 적 없음
