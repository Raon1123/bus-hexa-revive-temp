"""govtrack 데몬 루프 방어 경로(ADR-013) + build_recorder/TSV sink 조립 검증.

기존 smoke/night-window 테스트가 다루지 않는 분기 — 사이클 예외 격리, on_cycle 콜백,
state.persist 실패 무시, 야간 창 진입 시 persist, warm_from_repo 실패 무시, TSV 헤더 1회 —
를 대역 주입으로 결정적으로 검증한다. 실제 네트워크/시계/sleep 미사용.
"""
from __future__ import annotations

import threading
from datetime import datetime
from zoneinfo import ZoneInfo

from bushexa.crawler.daemon import build_recorder, make_tsv_sink, run_daemon
from bushexa.crawler.recorder import CycleStats
from bushexa.crawler.state import VehicleTimeline
from bushexa.db.repo import LogRow

KST = ZoneInfo("Asia/Seoul")
_DAY = datetime(2026, 6, 1, 8, 0, 0, tzinfo=KST)
_NIGHT = datetime(2026, 6, 1, 2, 0, 0, tzinfo=KST)


class _Clock:
    def __init__(self, dt):
        self._dt = dt

    def now(self):
        return self._dt


class _State:
    """persist 호출 횟수를 세고, 옵션으로 매번 실패하는 state 대역."""

    def __init__(self, fail=False):
        self.fail = fail
        self.persists = 0

    def persist(self):
        self.persists += 1
        if self.fail:
            raise OSError("disk full")


class _Recorder:
    """run_cycle 결과를 시퀀스대로 돌려주는(예외면 raise) recorder 대역."""

    def __init__(self, seq, state=None):
        self._seq = list(seq)
        self.state = state or _State()
        self.calls = 0

    def run_cycle(self, **kw):
        item = self._seq[min(self.calls, len(self._seq) - 1)]
        self.calls += 1
        if isinstance(item, Exception):
            raise item
        return item


def _stats():
    return CycleStats(cycle_started_at=_DAY)


def test_cycle_exception_does_not_kill_daemon():
    """run_cycle이 예외를 던져도 데몬이 로그 후 다음 사이클을 계속 수행하는지 검증한다(ADR-013).
    예외 사이클도 사이클 수에 포함되고, 성공 사이클만 on_cycle로 전달된다."""
    ok = _stats()
    rec = _Recorder([RuntimeError("api down"), ok, ok])
    seen = []

    cycles = run_daemon(config=None, recorder=rec, clock=_Clock(_DAY), sleep=lambda s: None,
                        stop_event=threading.Event(), max_cycles=3, on_cycle=seen.append)

    assert cycles == 3
    assert rec.calls == 3
    assert seen == [ok, ok]


def test_persist_failure_is_ignored():
    """사이클 후 state.persist가 실패해도 on_cycle은 호출되고 데몬이 계속 도는지 검증한다."""
    state = _State(fail=True)
    rec = _Recorder([_stats()], state=state)
    seen = []

    cycles = run_daemon(config=None, recorder=rec, clock=_Clock(_DAY), sleep=lambda s: None,
                        stop_event=threading.Event(), max_cycles=2, on_cycle=seen.append)

    assert cycles == 2
    assert state.persists == 2
    assert len(seen) == 2


def test_night_window_persists_state_before_sleep():
    """야간 창 진입 시 run_cycle 없이 state.persist를 먼저 호출하고, persist 실패도 무시하는지 검증한다(감사 2-8)."""
    state = _State(fail=True)
    rec = _Recorder([AssertionError("야간엔 run_cycle 금지")], state=state)
    stop = threading.Event()
    sleeps = []

    def fake_sleep(s):
        sleeps.append(s)
        if len(sleeps) == 2:
            stop.set()

    run_daemon(config=None, recorder=rec, clock=_Clock(_NIGHT), sleep=fake_sleep,
               stop_event=stop, night_sleep_seconds=45)

    assert rec.calls == 0
    assert state.persists == 2
    assert sleeps == [45, 45]


def test_stop_event_preset_runs_zero_cycles():
    """시작 전에 stop_event가 이미 set이면 사이클을 한 번도 돌지 않고 0을 반환하는지 검증한다."""
    stop = threading.Event()
    stop.set()
    rec = _Recorder([_stats()])

    assert run_daemon(config=None, recorder=rec, clock=_Clock(_DAY),
                      sleep=lambda s: None, stop_event=stop) == 0
    assert rec.calls == 0


# ── build_recorder ───────────────────────────────────────────────


class _WarmFailState(VehicleTimeline):
    def warm_from_repo(self, repo, since):
        raise RuntimeError("db unreachable")


def test_build_recorder_survives_warm_failure(app_config_test):
    """warm_from_repo가 실패해도 build_recorder가 예외 없이 recorder를 조립하는지 검증한다(H2 워밍 실패가 기동을 막지 않음)."""
    sink_rows = []
    rec = build_recorder(app_config_test, repo=object(), client=object(),
                         state=_WarmFailState(), clock=_Clock(_DAY),
                         passage_sink=sink_rows.append)
    assert rec.state.__class__ is _WarmFailState


def test_build_recorder_warms_with_since_window(app_config_test):
    """warm_from_repo가 clock.now() - warm_hours 시점을 since로 받는지 검증한다."""
    seen = {}

    class _SpyState(VehicleTimeline):
        def warm_from_repo(self, repo, since):
            seen["since"] = since
            return 0

    build_recorder(app_config_test, repo=object(), client=object(), state=_SpyState(),
                   clock=_Clock(_DAY), passage_sink=lambda r: None, warm_hours=2)
    assert seen["since"] == datetime(2026, 6, 1, 6, 0, 0, tzinfo=KST)


# ── TSV sink ─────────────────────────────────────────────────────


def _row(vehicle):
    return LogRow(idx="2026-06-01 08:00:00", stop_id="S1", route_id="R1",
                  route_nm="713", vehicle_no=vehicle, stop_name=None)


def test_tsv_sink_writes_header_once_and_rows(tmp_path):
    """새 파일이면 헤더를 1회 쓰고, 같은 경로로 sink를 다시 만들어도 헤더/핸들러가 중복되지 않는지 검증한다.
    stop_name이 None이면 빈 칸으로 기록된다."""
    path = tmp_path / "sub" / "logs.tsv"
    sink = make_tsv_sink(path)
    sink(_row("v1"))
    sink2 = make_tsv_sink(path)  # 같은 프로세스 재호출(재조립)
    sink2(_row("v2"))

    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "time\tstop_id\troute_id\tvehicle_number\tstop_name"
    assert lines[1:] == [
        "2026-06-01 08:00:00\tS1\tR1\tv1\t",
        "2026-06-01 08:00:00\tS1\tR1\tv2\t",
    ]
