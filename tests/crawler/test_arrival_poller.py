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
    검증한다 — 백업본 갱신 완전성."""
    client = _FakeUlsanClient()
    repo = _SpyArrivalRepo()
    stop = threading.Event()

    run_arrival_poller(config=None, repo=repo, client=client, clock=_Clock(),
                       sleep=lambda _s: None, stop_event=stop, max_cycles=1)

    assert len(repo.upserts) == len(SERACH_STOPS)
    assert {u[0] for u in repo.upserts} == set(SERACH_STOPS)
    assert client.calls == list(SERACH_STOPS)            # 각 정류장 1회
    assert repo.upserts[0][1] == [{"route_id": "713", "present_stop": "명촌",
                                   "vehicle_no": "울산71자3238", "arrival_time": 180}]


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
