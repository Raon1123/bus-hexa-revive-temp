"""런타임 폴링 주기 설정 파일 재읽기 검증 (ADR-013).

run_daemon과 run_arrival_poller가 매 사이클 crawl_settings.json을 재읽어,
두 번째 사이클부터 변경된 주기를 적용하는지 검증한다.

기대값은 주입한 설정값에서 직접 도출(E-13). 네트워크·실제 sleep·DB 미사용.
sleep·stop_event·on_cycle 주입 패턴은 test_daemon_smoke·test_arrival_poller와 동일.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from bushexa.api_clients.ulsan_bis import Arrival
from bushexa.crawler.arrival_poller import run_arrival_poller
from bushexa.crawler.daemon import run_daemon
from bushexa.crawler.recorder import CycleStats
from bushexa.crawler.state import VehicleTimeline
from bushexa.services.crawl_settings import CrawlSettingsStore, default_crawl_settings_path

KST = ZoneInfo("Asia/Seoul")

_INITIAL_GOVTRACK = 5.0   # 초기 govtrack 주기(범위 내)
_UPDATED_GOVTRACK = 30.0  # 교체 후 govtrack 주기(범위 내)
_INITIAL_ARRIVAL = 5.0    # 초기 arrival 주기(범위 내)
_UPDATED_ARRIVAL = 30.0   # 교체 후 arrival 주기(범위 내)


class _DayClock:
    """주간(08:00) — govtrack night window 밖."""

    def now(self):
        return datetime(2026, 6, 1, 8, 0, 0, tzinfo=KST)


class _FakeRecorder:
    """govtrack recorder 대역 — state.persist()도 no-op으로 안전."""
    state = VehicleTimeline()

    def run_cycle(self, **kw):
        return CycleStats(cycle_started_at=_DayClock().now())


class _FakeArrivalClient:
    """정류장마다 도착 1건을 돌려주는 대역 — 호출 수 확인 불필요."""

    def fetch_arrivals(self, stop_id, **kw):
        return [Arrival(route_id="713", present_stop="명촌", vehicle_no="울산71자3238",
                        arrival_time=180)]


class _FakeArrivalRepo:
    """upsert 호출을 기록하는 대역."""

    def upsert(self, stop_id, payload, fetched_at):
        pass


# ---------------------------------------------------------------------------
# run_daemon: settings_store가 있으면 매 사이클 govtrack 주기를 재읽는다
# ---------------------------------------------------------------------------

def test_daemon_poll_seconds_updated_on_second_cycle(tmp_path):
    """첫 번째 sleep은 초기 주기, 두 번째 sleep은 파일 교체 후 주기를 사용하는지 검증한다.

    사이클 순서: run_cycle → on_cycle → sleep(설정 파일 재읽기).
    따라서 두 번째 on_cycle 호출에서 파일을 교체하면 두 번째 sleep이 새 값을 읽는다.
    """
    settings_path = default_crawl_settings_path(tmp_path)
    store = CrawlSettingsStore(settings_path)
    store.save(govtrack_poll_seconds=_INITIAL_GOVTRACK)

    sleeps: list[float] = []
    callback_count = 0

    def fake_sleep(seconds):
        sleeps.append(seconds)

    def on_cycle(_cyc):
        nonlocal callback_count
        # 두 번째 사이클(callback_count==1)의 on_cycle에서 파일 교체
        # → 이 사이클 이후의 sleep이 새 값을 읽는다
        if callback_count == 1:
            store.save(govtrack_poll_seconds=_UPDATED_GOVTRACK)
        callback_count += 1

    run_daemon(
        config=None,
        recorder=_FakeRecorder(),
        clock=_DayClock(),
        sleep=fake_sleep,
        poll_seconds=_INITIAL_GOVTRACK,  # settings_store가 default로 사용
        settings_store=store,
        max_cycles=3,
        on_cycle=on_cycle,
    )

    # max_cycles=3이면 sleep은 사이클 0·1 이후 각 1회씩 → 2회
    assert len(sleeps) == 2, f"sleep 횟수 기대=2, 실제={len(sleeps)}"
    assert sleeps[0] == _INITIAL_GOVTRACK, f"첫 sleep 기대={_INITIAL_GOVTRACK}, 실제={sleeps[0]}"
    assert sleeps[1] == _UPDATED_GOVTRACK, f"두 번째 sleep 기대={_UPDATED_GOVTRACK}, 실제={sleeps[1]}"


def test_daemon_no_settings_store_uses_poll_seconds(tmp_path):
    """settings_store=None이면 기존 poll_seconds 그대로 모든 사이클에 적용된다."""
    sleeps: list[float] = []

    run_daemon(
        config=None,
        recorder=_FakeRecorder(),
        clock=_DayClock(),
        sleep=lambda s: sleeps.append(s),
        poll_seconds=10.0,
        settings_store=None,
        max_cycles=3,
    )

    assert len(sleeps) == 2
    assert sleeps == [10.0, 10.0]


def test_daemon_auto_creates_store_from_data_dir(tmp_path):
    """config.data_dir가 있으면 settings_store=None이어도 자동으로 스토어를 생성한다."""
    # config 대역에 data_dir 속성 부여
    class _Cfg:
        data_dir = str(tmp_path)

    # 설정 파일에 값을 미리 저장
    store = CrawlSettingsStore(default_crawl_settings_path(tmp_path))
    store.save(govtrack_poll_seconds=45.0)

    sleeps: list[float] = []

    run_daemon(
        config=_Cfg(),
        recorder=_FakeRecorder(),
        clock=_DayClock(),
        sleep=lambda s: sleeps.append(s),
        poll_seconds=10.0,   # 기본값: 스토어에 45.0이 있으므로 무시됨
        settings_store=None,  # 자동 생성
        max_cycles=2,
    )

    # max_cycles=2 → sleep 1회
    assert len(sleeps) == 1
    assert sleeps[0] == 45.0, f"파일 값 45.0을 기대, 실제={sleeps[0]}"


# ---------------------------------------------------------------------------
# run_arrival_poller: settings_store가 있으면 매 사이클 arrival 주기를 재읽는다
# ---------------------------------------------------------------------------

def test_arrival_poller_poll_seconds_updated_on_second_cycle(tmp_path):
    """첫 번째 sleep은 초기 주기, 두 번째 sleep은 파일 교체 후 주기를 사용하는지 검증한다.

    사이클 순서: 정류장 순회 → on_cycle(idx) → cycles+=1 → sleep(설정 파일 재읽기).
    on_cycle은 0-기반 인덱스를 받으므로 idx==1이 두 번째 사이클을 의미한다.
    """
    settings_path = default_crawl_settings_path(tmp_path)
    store = CrawlSettingsStore(settings_path)
    store.save(arrival_poll_seconds=_INITIAL_ARRIVAL)

    sleeps: list[float] = []

    def fake_sleep(seconds):
        sleeps.append(seconds)

    def on_cycle(idx):
        # 두 번째 사이클(idx==1)의 on_cycle에서 파일 교체
        # → 이 사이클 이후의 sleep이 새 값을 읽는다
        if idx == 1:
            store.save(arrival_poll_seconds=_UPDATED_ARRIVAL)

    run_arrival_poller(
        config=None,
        repo=_FakeArrivalRepo(),
        client=_FakeArrivalClient(),
        clock=_DayClock(),
        sleep=fake_sleep,
        poll_seconds=_INITIAL_ARRIVAL,  # _resolve_poll_seconds가 기본값으로 사용
        stops=["stop1"],               # 정류장 수를 최소화해 속도 향상
        settings_store=store,
        max_cycles=3,
        on_cycle=on_cycle,
    )

    # max_cycles=3이면 sleep은 사이클 0·1 이후 각 1회씩 → 2회
    assert len(sleeps) == 2, f"sleep 횟수 기대=2, 실제={len(sleeps)}"
    assert sleeps[0] == _INITIAL_ARRIVAL, f"첫 sleep 기대={_INITIAL_ARRIVAL}, 실제={sleeps[0]}"
    assert sleeps[1] == _UPDATED_ARRIVAL, f"두 번째 sleep 기대={_UPDATED_ARRIVAL}, 실제={sleeps[1]}"


def test_arrival_poller_no_settings_store_uses_poll_seconds():
    """settings_store=None이면 기존 poll_seconds 그대로 모든 사이클에 적용된다."""
    sleeps: list[float] = []

    run_arrival_poller(
        config=None,
        repo=_FakeArrivalRepo(),
        client=_FakeArrivalClient(),
        clock=_DayClock(),
        sleep=lambda s: sleeps.append(s),
        poll_seconds=7.0,
        stops=["stop1"],
        settings_store=None,
        max_cycles=3,
    )

    assert len(sleeps) == 2
    assert sleeps == [7.0, 7.0]


def test_arrival_poller_auto_creates_store_from_data_dir(tmp_path):
    """config.data_dir가 있으면 settings_store=None이어도 자동으로 스토어를 생성한다."""
    class _Cfg:
        data_dir = str(tmp_path)

    store = CrawlSettingsStore(default_crawl_settings_path(tmp_path))
    store.save(arrival_poll_seconds=20.0)

    sleeps: list[float] = []

    run_arrival_poller(
        config=_Cfg(),
        repo=_FakeArrivalRepo(),
        client=_FakeArrivalClient(),
        clock=_DayClock(),
        sleep=lambda s: sleeps.append(s),
        poll_seconds=7.0,   # 파일에 20.0이 있으므로 무시됨
        stops=["stop1"],
        settings_store=None,  # 자동 생성
        max_cycles=2,
    )

    # max_cycles=2 → sleep 1회
    assert len(sleeps) == 1
    assert sleeps[0] == 20.0, f"파일 값 20.0을 기대, 실제={sleeps[0]}"
