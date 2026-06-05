"""W3 daemon smoke: dry-run INSERT 0건(EC-3) + SIGTERM graceful 종료(EC-4/AC-3).

기대값은 주입한 응답·stop_event 타이밍에서 직접 도출(E-13). 실제 네트워크/시계/sleep 미사용.
"""
from __future__ import annotations

import threading
from datetime import datetime
from zoneinfo import ZoneInfo

from bushexa.crawler.daemon import crawl_once, run_daemon
from bushexa.crawler.recorder import CycleStats, GovtrackRecorder
from bushexa.crawler.state import VehicleTimeline
from tests.crawler._fakes import FakeTagoClient, make_response

KST = ZoneInfo("Asia/Seoul")


class _DayClock:
    """주간(08:00) — night window 밖."""

    def now(self):
        return datetime(2026, 6, 1, 8, 0, 0, tzinfo=KST)


class _SpyRepo:
    def __init__(self):
        self.batch_calls = 0

    def insert_batch(self, rows):
        self.batch_calls += 1
        return len(list(rows))


def test_crawl_once_dry_run():
    """--dry-run에서 mock client 응답을 처리하되 repo.insert_batch가 호출되지 않는지(0건) 검증한다."""
    resp = make_response([("999000149", "명촌", "veh-A")])
    client = FakeTagoClient(by_route={"195000177": resp})
    repo = _SpyRepo()
    recorder = GovtrackRecorder(
        client, VehicleTimeline(), repo, _DayClock(),
        tracked_stops_by_route={"195000177": {"999000149"}},
        stop_names={"999000149": "명촌"},
    )

    stats = crawl_once(recorder, "195000177", dry_run=True)

    assert stats.inserts == 1        # 기록 '후보'는 1건(요약 출력용)
    assert repo.batch_calls == 0     # 실제 INSERT 0건 (EC-3)


def test_sigterm_graceful():
    """데몬을 스레드로 띄우고 중단 플래그(SIGTERM 대용)를 세우면 현재 사이클을 끝낸 뒤
    1사이클 내에 종료하는지 검증한다 — EC-4."""
    stop = threading.Event()
    cycles_run = []

    class _Recorder:
        state = VehicleTimeline()

        def run_cycle(self, **kw):
            cycles_run.append(1)
            return CycleStats(cycle_started_at=_DayClock().now())

    def fake_sleep(_seconds):
        # 첫 사이클 직후 inter-cycle sleep에서 'SIGTERM 도착'을 시뮬레이션.
        stop.set()

    t = threading.Thread(target=run_daemon, kwargs=dict(
        config=None, recorder=_Recorder(), clock=_DayClock(),
        sleep=fake_sleep, stop_event=stop, poll_seconds=10))
    t.start()
    t.join(timeout=2.0)

    assert not t.is_alive()           # 종료됨(무한 루프에 갇히지 않음)
    assert len(cycles_run) == 1       # 진행 중 사이클을 끝낸 뒤 종료
