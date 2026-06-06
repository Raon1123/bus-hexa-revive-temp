"""E3 recorder fetch 병렬화 검증 — 보류 사유였던 3보장(노선별 격리·폴백 직렬화·결정성)이
병렬 모드에서도 유지되는지. 기대값은 주입한 응답·결함에서 직접 도출(E-13)."""
from __future__ import annotations

import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from bushexa.api_clients.composite_location import CompositeLocationClient
from bushexa.crawler.recorder import GovtrackRecorder
from bushexa.crawler.state import VehicleTimeline
from tests.crawler._fakes import FakeTagoClient, make_response

KST = ZoneInfo("Asia/Seoul")

ROUTE_A, ROUTE_B, ROUTE_C = "195000177", "195000178", "195000215"


class _Clock:
    def now(self):
        return datetime(2026, 6, 1, 8, 0, 0, tzinfo=KST)


class _SpyRepo:
    def __init__(self):
        self.batches: list[list] = []

    def insert_batch(self, rows):
        self.batches.append(list(rows))


def _three_route_recorder(client, **kw):
    """3개 노선, 노선별 추적 정류장 1개짜리 recorder를 만든다."""
    tracked = {ROUTE_A: {"n-A"}, ROUTE_B: {"n-B"}, ROUTE_C: {"n-C"}}
    return GovtrackRecorder(
        client, VehicleTimeline(), repo=_SpyRepo(), clock=_Clock(),
        tracked_stops_by_route=tracked,
        stop_names={"n-A": "정류장A", "n-B": "정류장B", "n-C": "정류장C"},
        **kw,
    )


def _responses():
    return {
        ROUTE_A: make_response([("n-A", "정류장A", "veh-1")]),
        ROUTE_B: make_response([("n-B", "정류장B", "veh-2")]),
        ROUTE_C: make_response([("n-C", "정류장C", "veh-3")]),
    }


def test_parallel_cycle_equals_sequential():
    """동일 입력에서 병렬(workers=4)과 순차(workers=1) run_cycle의 산출물(노선별 inserts,
    batch 내용·순서)이 완전히 같은지 검증한다 — scatter-fetch/sequential-process 결정성."""
    out = {}
    for workers in (1, 4):
        rec = _three_route_recorder(FakeTagoClient(by_route=_responses()),
                                    fetch_workers=workers)
        cyc = rec.run_cycle()
        out[workers] = (
            {r: s.inserts for r, s in cyc.route_results.items()},
            [(row.route_id, row.vehicle_no, row.stop_id, row.idx)
             for row in rec.repo.batches[0]],
            cyc.total_inserts, cyc.total_errors,
        )
    assert out[1] == out[4]
    assert out[4][2] == 3                       # 3노선 각 1건
    # batch 행 순서가 route_ids 순서를 따른다(처리는 메인 스레드 순차).
    assert [r for r, *_ in out[4][1]] == [ROUTE_A, ROUTE_B, ROUTE_C]


def test_parallel_route_failure_isolated():
    """병렬 모드에서 한 노선 fetch 예외가 future에 캡처되어 다른 노선 수집·alert 상태를
    오염시키지 않는지 검증한다(H4/H6 보장 유지)."""

    class _OneBadClient(FakeTagoClient):
        def fetch_bus_locations(self, route_id, *, page=1, rows=70):
            if route_id == ROUTE_B:
                self.calls.append(route_id)
                raise RuntimeError("TAGO 무응답(모사)")
            return super().fetch_bus_locations(route_id, page=page, rows=rows)

    rec = _three_route_recorder(_OneBadClient(by_route=_responses()), fetch_workers=4)
    cyc = rec.run_cycle()

    assert cyc.route_results[ROUTE_B].api_ok is False
    assert cyc.route_results[ROUTE_A].inserts == 1
    assert cyc.route_results[ROUTE_C].inserts == 1
    assert cyc.total_inserts == 2
    # 실패 카운터는 해당 노선만 증가(메인 스레드에서만 변이).
    assert rec._consec_fail.get(ROUTE_B) == 1
    assert rec._consec_fail.get(ROUTE_A, 0) == 0


def test_killswitch_preserves_fetch_order():
    """fetch_workers=1이면 executor 없이 노선 순서대로 fetch — 기존 순차 루프와 동일
    (운영 kill-switch 보증)."""
    client = FakeTagoClient(by_route=_responses())
    rec = _three_route_recorder(client, fetch_workers=1)
    rec.run_cycle()
    assert client.calls == [ROUTE_A, ROUTE_B, ROUTE_C]


def test_fetch_workers_env(monkeypatch):
    """env BUSHEXA_GOVTRACK_FETCH_WORKERS로 운영자가 병렬을 켤 수 있는지 — env 미설정
    기본값은 1(순차, 배포 무변경 게이트)."""
    monkeypatch.delenv("BUSHEXA_GOVTRACK_FETCH_WORKERS", raising=False)
    rec_default = _three_route_recorder(FakeTagoClient(by_route=_responses()))
    assert rec_default.fetch_workers == 1
    monkeypatch.setenv("BUSHEXA_GOVTRACK_FETCH_WORKERS", "4")
    rec = _three_route_recorder(FakeTagoClient(by_route=_responses()))
    assert rec.fetch_workers == 4


def test_composite_cache_serializes_ulsan_under_stampede():
    """TAGO 동시 장애로 여러 스레드가 같은 정류장 fallback에 몰려도(stampede)
    _arrivals_cached 락이 TTL 내 울산 호출을 stop_id당 1회로 묶는지 검증한다 —
    장애 중 울산 QPS가 기존 순차 루프와 동일하게 직렬화(E3 보류 사유 해소)."""

    class _SlowUlsan:
        def __init__(self):
            self.calls: list[str] = []

        def fetch_arrivals(self, stop_id, **kw):
            self.calls.append(stop_id)
            time.sleep(0.05)  # 동시 진입 창을 벌려 락 부재 시 중복 호출이 드러나게 함
            return []

    ulsan = _SlowUlsan()
    client = CompositeLocationClient(tago=None, ulsan=ulsan, cache_ttl=8.0)

    threads = [threading.Thread(target=client._arrivals_cached, args=("stop-1",))
               for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert ulsan.calls == ["stop-1"]  # 락 + 캐시로 정확히 1회
