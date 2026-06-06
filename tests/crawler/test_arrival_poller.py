"""W9 arrival_poller 검증 (ADR-010). 기대값은 SERACH_STOPS·사이클 수에서 직접 도출(E-13)."""
from __future__ import annotations

import threading
from datetime import datetime
from zoneinfo import ZoneInfo

from bushexa.api_clients.ulsan_bis import Arrival
from bushexa.crawler.arrival_poller import run_arrival_poller
from bushexa.data.constants import SERACH_STOPS

KST = ZoneInfo("Asia/Seoul")


class _Clock:
    def now(self):
        return datetime(2026, 6, 1, 8, 0, 0, tzinfo=KST)


class _FakeUlsanClient:
    """정류장마다 도착 1건을 돌려주는 대역. 호출 횟수를 센다."""

    def __init__(self):
        self.calls: list[str] = []

    def fetch_arrivals(self, stop_id, **kw):
        self.calls.append(stop_id)
        return [Arrival(route_id="713", present_stop="명촌", vehicle_no="울산71자3238",
                        arrival_time=180)]


class _SpyArrivalRepo:
    def __init__(self):
        self.upserts: list[tuple] = []

    def upsert(self, stop_id, payload, fetched_at):
        self.upserts.append((stop_id, payload, fetched_at))


def test_one_cycle_upserts_all():
    """한 폴 사이클에서 SERACH_STOPS(17개) 각각에 대해 fetch→upsert가 정확히 1회씩 일어나는지
    검증한다 — 백업본 갱신 완전성. 병렬 모드(workers=4)로 돌려 E4 경로를 커버한다."""
    client = _FakeUlsanClient()
    repo = _SpyArrivalRepo()
    stop = threading.Event()

    run_arrival_poller(config=None, repo=repo, client=client, clock=_Clock(),
                       sleep=lambda _s: None, stop_event=stop, max_cycles=1,
                       fetch_workers=4)

    assert len(repo.upserts) == len(SERACH_STOPS)
    assert {u[0] for u in repo.upserts} == set(SERACH_STOPS)
    # E4: fetch는 병렬이라 호출 '순서'는 비결정적 — 각 정류장 정확히 1회만 보장.
    assert sorted(client.calls) == sorted(SERACH_STOPS)
    # upsert는 메인 스레드에서 stops 순서로 순차 — 순서 결정성은 여기서 보장된다.
    assert [u[0] for u in repo.upserts] == list(SERACH_STOPS)
    assert repo.upserts[0][1] == [{"route_id": "713", "present_stop": "명촌",
                                   "vehicle_no": "울산71자3238", "arrival_time": 180}]


def test_sequential_killswitch_preserves_call_order():
    """fetch_workers=1(kill-switch)이면 executor 없이 기존 순차 루프 — 호출 순서까지
    레거시와 동일함을 보증한다(E4 운영 비상 스위치)."""
    client = _FakeUlsanClient()
    repo = _SpyArrivalRepo()
    stop = threading.Event()

    run_arrival_poller(config=None, repo=repo, client=client, clock=_Clock(),
                       sleep=lambda _s: None, stop_event=stop, max_cycles=1,
                       fetch_workers=1)

    assert client.calls == list(SERACH_STOPS)            # 각 정류장 1회, 순서 보존
    assert [u[0] for u in repo.upserts] == list(SERACH_STOPS)


def test_fetch_workers_from_env(monkeypatch):
    """BUSHEXA_ARRIVAL_FETCH_WORKERS=1이면 env만으로 순차 모드가 선택되는지 검증한다."""
    monkeypatch.setenv("BUSHEXA_ARRIVAL_FETCH_WORKERS", "1")
    client = _FakeUlsanClient()
    stop = threading.Event()

    run_arrival_poller(config=None, repo=_SpyArrivalRepo(), client=client, clock=_Clock(),
                       sleep=lambda _s: None, stop_event=stop, max_cycles=1)

    assert client.calls == list(SERACH_STOPS)


class _FlakyUlsanClient(_FakeUlsanClient):
    """특정 정류장에서만 예외를 던지는 대역 — 정류장별 격리(ADR-013) 검증용."""

    def __init__(self, bad_stop):
        super().__init__()
        self.bad_stop = bad_stop

    def fetch_arrivals(self, stop_id, **kw):
        if stop_id == self.bad_stop:
            self.calls.append(stop_id)
            raise RuntimeError("울산 API 무응답(모사)")
        return super().fetch_arrivals(stop_id, **kw)


def test_one_stop_failure_isolated_in_parallel():
    """병렬 fetch에서도 한 정류장 실패가 future에 캡처되어 나머지 정류장 upsert가
    전부 진행되는지 검증한다(ADR-013 격리가 병렬화 후에도 유지 — E3/E4 보류 사유 해소)."""
    bad = SERACH_STOPS[3]
    client = _FlakyUlsanClient(bad)
    repo = _SpyArrivalRepo()
    stop = threading.Event()

    run_arrival_poller(config=None, repo=repo, client=client, clock=_Clock(),
                       sleep=lambda _s: None, stop_event=stop, max_cycles=1,
                       fetch_workers=4)

    assert len(repo.upserts) == len(SERACH_STOPS) - 1
    assert {u[0] for u in repo.upserts} == set(SERACH_STOPS) - {bad}


def test_poll_interval_from_env(monkeypatch):
    """BUSHEXA_ARRIVAL_POLL_SECONDS=5를 설정하면 사이클 간 sleep이 5초로 호출되는지 검증한다 —
    과호출 방지(ADR-010 시간오차 회피)를 정량 보증."""
    monkeypatch.setenv("BUSHEXA_ARRIVAL_POLL_SECONDS", "5")
    sleeps: list[float] = []
    stop = threading.Event()

    def fake_sleep(seconds):
        sleeps.append(seconds)
        stop.set()  # 첫 sleep 후 종료

    run_arrival_poller(config=None, repo=_SpyArrivalRepo(), client=_FakeUlsanClient(),
                       clock=_Clock(), sleep=fake_sleep, stop_event=stop)

    assert sleeps == [5.0]


def test_no_overcall_under_load():
    """외부 호출 횟수가 사이클 수에만 비례(= cycles × 정류장 수)하고 다른 요인과 무관한지
    검증한다 — 화면 트래픽과 분리(ADR-010)."""
    client = _FakeUlsanClient()
    stop = threading.Event()

    run_arrival_poller(config=None, repo=_SpyArrivalRepo(), client=client, clock=_Clock(),
                       sleep=lambda _s: None, stop_event=stop, max_cycles=3)

    assert len(client.calls) == 3 * len(SERACH_STOPS)
