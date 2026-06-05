"""감사 보고서 기반 recorder 정확성 테스트 (T1, T2, T5, T6, T7).

기대값은 주입한 입력에서 직접 도출한다(E-13). 네트워크 사용 없음.

- T1: GPS 지터/방향 역전 → 허위 통과 기록 (감사 2-1)
- T2: node_ord 역전 게이트 + skipped_reversed 카운터 (감사 2-1/2-6)
- T5: route_nm이 LogRow에 채워지고 DB에 기록됨 (감사 2-3)
- T6: dry_run=True 이후 정규 사이클에서 통과 누락 없음 (감사 2-7)
- T7: 야간 창 진입 시 state.persist() 호출 (감사 2-8)
"""
from __future__ import annotations

import threading
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from bushexa.crawler.daemon import run_daemon
from bushexa.crawler.recorder import JITTER_WINDOW, GovtrackRecorder, RouteStats
from bushexa.crawler.state import VehicleTimeline
from bushexa.db.connection import create_connection
from bushexa.db.repo import BusLogRepo, LogRow
from bushexa.db.schema import create_schema
from tests.crawler._fakes import FakeTagoClient, SequenceTagoClient, make_response

KST = ZoneInfo("Asia/Seoul")
ROUTE = "195000177"
TRACKED = {"999000149", "193012314", "193040420"}


class _Clock:
    def now(self):
        return datetime(2026, 6, 1, 8, 0, 0, tzinfo=KST)


class _NightClock:
    """새벽 2시 — night window 안."""

    def now(self):
        return datetime(2026, 6, 1, 2, 0, 0, tzinfo=KST)


def _fresh_repo() -> BusLogRepo:
    conn = create_connection("sqlite:///:memory:")
    create_schema(conn)
    return BusLogRepo(conn)


def _recorder(client, state, repo, *, route_names=None):
    return GovtrackRecorder(
        client, state, repo, _Clock(),
        tracked_stops_by_route={ROUTE: set(TRACKED)},
        stop_names={"999000149": "명촌", "193012314": "태화강역", "193040420": "터미널"},
        route_names=route_names or {},
    )


# ---------------------------------------------------------------------------
# T1: GPS 지터 → node_ord 역전이 JITTER_WINDOW 이하면 기록 skip
# ---------------------------------------------------------------------------

def test_T1_jitter_skip_no_insert():
    """T1: GPS 지터(소역전)이면 INSERT 후보가 없고 skipped_reversed가 증가하는지.

    차량 A: ord=5(정류소 A) → ord=6(정류소 B 이동) → ord=5(GPS 지터, 역전) 순서.
    세 번째 응답이 ord=5로 역전이지만 JITTER_WINDOW 이하이므로 skip.
    기대: 정류소 A 1건, 정류소 B 1건, 세 번째는 skip(skipped_reversed=1).
    """
    # 999000149(ord=5), 193012314(ord=6), 999000149(ord=5) — 세 번째가 지터
    client = SequenceTagoClient([
        make_response([("999000149", "명촌", "veh-A", 5)]),        # 정류소 A, ord=5
        make_response([("193012314", "태화강역", "veh-A", 6)]),    # 정류소 B, ord=6 (정상 이동)
        make_response([("999000149", "명촌", "veh-A", 5)]),        # 역전(5<6), JITTER_WINDOW 이하
    ])
    repo = _fresh_repo()
    state = VehicleTimeline()
    recorder = _recorder(client, state, repo)

    stats1, _ = recorder.run_single_route(ROUTE)
    stats2, _ = recorder.run_single_route(ROUTE)
    stats3, cands3 = recorder.run_single_route(ROUTE)

    # 첫 번째: 새 차량이므로 changed=True → INSERT 후보
    assert stats1.inserts == 1
    # 두 번째: ord 6으로 정방향 이동 → INSERT 후보
    assert stats2.inserts == 1
    # 세 번째: ord 5로 역전(JITTER_WINDOW=3 이하) → skip
    assert stats3.skipped_reversed == 1
    assert cands3 == []


def test_T1_large_reversal_is_not_jitter():
    """T1: 역전 폭이 JITTER_WINDOW 초과이면 종점 회차로 보고 정상 기록해야 한다.

    ord가 6에서 1로 역전(역전폭=5 > JITTER_WINDOW=3) → 종점 회차로 정상 기록.
    """
    client = SequenceTagoClient([
        make_response([("193012314", "태화강역", "veh-A", 6)]),  # ord=6 (이전 상태)
        make_response([("999000149", "명촌", "veh-A", 1)]),      # ord=1 (역전폭=5 > JITTER_WINDOW)
    ])
    state = VehicleTimeline()
    repo = _fresh_repo()
    recorder = _recorder(client, state, repo)

    recorder.run_single_route(ROUTE)  # ord=6 상태 기록
    stats2, cands2 = recorder.run_single_route(ROUTE)

    # 역전폭이 JITTER_WINDOW 초과 → 종점 회차로 보고 정상 기록
    assert stats2.skipped_reversed == 0
    assert stats2.inserts == 1
    assert cands2[0].stop_id == "999000149"


def test_T1_none_node_ord_passes_gate():
    """T1: node_ord가 None이면 게이트 통과 — 기존 동작 유지(울산 BIS fallback 경로).

    이전 ord가 있어도 새 ord가 None이면 게이트를 통과해 state.record가 호출된다.
    """
    client = SequenceTagoClient([
        make_response([("193012314", "태화강역", "veh-A", 6)]),  # ord=6 상태 기록
        make_response([("999000149", "명촌", "veh-A")]),          # node_ord=None(3-튜플)
    ])
    state = VehicleTimeline()
    repo = _fresh_repo()
    recorder = _recorder(client, state, repo)

    recorder.run_single_route(ROUTE)  # ord=6 상태 기록
    stats2, cands2 = recorder.run_single_route(ROUTE)

    # node_ord=None → 게이트 통과 → 정상 기록
    assert stats2.skipped_reversed == 0
    assert stats2.inserts == 1


# ---------------------------------------------------------------------------
# T2: RouteStats.skipped_reversed 카운터 축적 검증
# ---------------------------------------------------------------------------

def test_T2_skipped_reversed_counter_accumulates():
    """T2: 같은 차량이 JITTER_WINDOW 이하 역전을 연속으로 해도 skipped_reversed가 매번 증가하는지.

    시퀀스 추적(E-13 기대값 도출):
      step1: prev=None, new=5  → 게이트 통과 → state(ord=5). inserts=1
      step2: prev=5,    new=4  → diff=1 ≤ 3 → skip reversed=1
      step3: prev=5,    new=6  → 정방향   → state(ord=6). inserts=1
      step4: prev=6,    new=4  → diff=2 ≤ 3 → skip reversed=1
      step5: prev=6,    new=5  → diff=1 ≤ 3 → skip reversed=1
    총 skipped_reversed = 3
    """
    client = SequenceTagoClient([
        make_response([("999000149", "명촌", "veh-A", 5)]),     # step1: 첫 기록, ord=5
        make_response([("999000149", "명촌", "veh-A", 4)]),     # step2: 역전폭=1 → skip
        make_response([("193012314", "태화강역", "veh-A", 6)]), # step3: 정방향 이동
        make_response([("999000149", "명촌", "veh-A", 4)]),     # step4: 역전폭=2 → skip
        make_response([("193012314", "태화강역", "veh-A", 5)]), # step5: 역전폭=1 → skip
    ])
    state = VehicleTimeline()
    recorder = _recorder(client, state, None)

    all_reversed = 0
    for _ in range(5):
        s, _ = recorder.run_single_route(ROUTE)
        all_reversed += s.skipped_reversed

    assert all_reversed == 3  # 역전 3회 감지(E-13에서 도출)


# ---------------------------------------------------------------------------
# T5: route_nm이 LogRow에 채워지고 DB에 기록됨
# ---------------------------------------------------------------------------

def test_T5_route_nm_in_logrow():
    """T5: route_names 주입 시 LogRow.route_nm이 버스 번호로 채워지는지(감사 2-3).

    ROUTEID['195000177'][0] = "713" — run_single_route가 반환하는 LogRow.route_nm이 "713"이어야.
    """
    resp = make_response([("999000149", "명촌", "veh-A")])
    client = FakeTagoClient(by_route={ROUTE: resp})
    state = VehicleTimeline()
    recorder = GovtrackRecorder(
        client, state, repo=None, clock=_Clock(),
        tracked_stops_by_route={ROUTE: {"999000149"}},
        stop_names={"999000149": "명촌"},
        route_names={ROUTE: "713"},  # 버스 번호 주입
    )

    _, candidates = recorder.run_single_route(ROUTE)

    assert len(candidates) == 1
    assert candidates[0].route_nm == "713"


def test_T5_route_nm_persisted_to_db():
    """T5: insert_batch 후 DB에 route_nm이 NULL이 아닌 값으로 저장되는지(감사 2-3).

    기대: get_by_route 결과의 route_nm == "713".
    """
    resp = make_response([("999000149", "명촌", "veh-A")])
    client = FakeTagoClient(by_route={ROUTE: resp})
    state = VehicleTimeline()
    repo = _fresh_repo()
    recorder = GovtrackRecorder(
        client, state, repo, _Clock(),
        tracked_stops_by_route={ROUTE: {"999000149"}},
        stop_names={"999000149": "명촌"},
        route_names={ROUTE: "713"},
    )

    recorder.run_cycle()

    rows = repo.get_by_route(ROUTE)
    assert len(rows) == 1
    assert rows[0].route_nm == "713"


def test_T5_route_nm_none_when_not_injected():
    """T5: route_names 없이 생성하면 route_nm이 None으로 남는지(기존 동작 보존).

    route_names를 주입하지 않으면 route_nm=None이어야 한다(하위호환).
    """
    resp = make_response([("999000149", "명촌", "veh-A")])
    client = FakeTagoClient(by_route={ROUTE: resp})
    state = VehicleTimeline()
    recorder = GovtrackRecorder(
        client, state, repo=None, clock=_Clock(),
        tracked_stops_by_route={ROUTE: {"999000149"}},
        stop_names={"999000149": "명촌"},
        # route_names 주입 없음
    )

    _, candidates = recorder.run_single_route(ROUTE)

    assert len(candidates) == 1
    assert candidates[0].route_nm is None


# ---------------------------------------------------------------------------
# T6: dry_run=True 이후 정규 사이클에서 통과 누락 없음
# ---------------------------------------------------------------------------

def test_T6_dry_run_does_not_advance_state():
    """T6: dry_run=True가 state를 전진시키지 않아 실제 run 사이클이 같은 통과를 누락하지 않는지.

    시나리오: 차량이 정류소 A(999000149)에 있을 때 dry_run 실행 후 정규 run 실행.
    dry_run이 state를 전진시키지 않으면 정규 run에서 changed=True → INSERT 1건.
    dry_run이 state를 전진시키면 정규 run에서 changed=False → INSERT 0건(버그, 감사 2-7).

    주의: run_single_route는 dry_run=True여도 candidates 목록을 반환한다(RouteStats.inserts=1).
    실제 INSERT는 run_cycle이 dry_run 분기에서 막는다. 여기서는 state 전진 억제만 검증한다.
    """
    resp_A = make_response([("999000149", "명촌", "veh-A")])
    client = FakeTagoClient(by_route={ROUTE: resp_A})
    state = VehicleTimeline()
    repo = _fresh_repo()
    recorder = _recorder(client, state, repo)

    # dry_run 사이클: 후보는 반환되지만(stats.inserts=1) state는 전진되지 않아야 함.
    dry_stats, dry_cands = recorder.run_single_route(ROUTE, dry_run=True)
    assert dry_stats.inserts == 1   # 후보는 감지됨(RouteStats 표시용)
    assert len(dry_cands) == 1      # run_single_route는 candidates 반환(run_cycle이 INSERT 막음)
    # state가 전진되지 않았으면 last_node가 None이어야(핵심 검증, 감사 2-7)
    assert state.last_node(ROUTE, "veh-A") is None, "dry_run이 state를 전진시켰음 (감사 2-7 버그)"

    # 정규 사이클: dry_run 후에도 동일 위치가 changed=True로 기록되어야
    real_stats, real_cands = recorder.run_single_route(ROUTE, dry_run=False)
    assert real_stats.inserts == 1, "dry_run이 state를 전진시켜 정규 사이클 통과 누락"
    assert len(real_cands) == 1
    assert real_cands[0].stop_id == "999000149"


def test_T6_dry_run_repeated_does_not_affect_state():
    """T6: dry_run을 여러 번 반복해도 state가 변하지 않고 이후 정규 run이 정상 동작하는지."""
    resp = make_response([("999000149", "명촌", "veh-A")])
    client = FakeTagoClient(by_route={ROUTE: resp})
    state = VehicleTimeline()
    recorder = _recorder(client, state, None)

    for _ in range(5):
        recorder.run_single_route(ROUTE, dry_run=True)

    # 5회 dry_run 후에도 state에 차량 없음
    assert state.last_node(ROUTE, "veh-A") is None


# ---------------------------------------------------------------------------
# T7: 야간 창 진입 시 state.persist() 호출
# ---------------------------------------------------------------------------

def test_T7_night_window_calls_persist():
    """T7: 야간 창(01:00~05:00) 진입 시 sleep 전에 state.persist()가 호출되는지(감사 2-8).

    PersistSpy를 state에 달아 persist 호출 횟수를 셈.
    """
    persist_calls: list[int] = []
    stop = threading.Event()

    class _PersistSpyTimeline:
        def persist(self):
            persist_calls.append(1)

        def run_cycle(self, **kw):
            pass

    class _SpyRecorder:
        state = _PersistSpyTimeline()

        def run_cycle(self, **kw):
            from bushexa.crawler.recorder import CycleStats
            return CycleStats(cycle_started_at=_NightClock().now())

    def fake_sleep(_seconds):
        stop.set()  # 첫 sleep 후 루프 종료

    run_daemon(
        config=None,
        recorder=_SpyRecorder(),
        clock=_NightClock(),
        sleep=fake_sleep,
        stop_event=stop,
        poll_seconds=10,
        night_sleep_seconds=60,
    )

    assert len(persist_calls) >= 1, "야간 창 진입 시 state.persist()가 호출되지 않음 (감사 2-8)"
