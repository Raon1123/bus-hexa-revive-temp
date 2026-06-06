"""울산 BIS 도착정보 poller (W9, ADR-010).

화면이 울산 API를 직접·빈번히 호출하면 시간 오차가 발생한다(사용자 보고). 그래서 도착정보는
**사용자 트래픽과 무관한 고정 주기 데몬**이 5~10초 간격으로 폴링해 ``bus_arrival_cache``에
백업하고, 화면은 그 백업본만 읽는다. 호출 빈도는 화면 요청 수가 아니라 사이클 수에만 비례한다.

graceful 종료·sleep 주입 패턴은 govtrack daemon과 동일(테스트 결정성). 정류장별 호출 실패는
로그만 남기고 다음 정류장으로 계속한다(ADR-013).

병렬화(E4, scatter-fetch/sequential-process): 워커 스레드는 ``fetch_arrivals`` 호출만 수행하고
결과/예외만 반환한다 — upsert·ok/last_error 집계는 메인 스레드에서 ``stops`` 순서로 순차 처리해
출력 결정성과 정류장별 격리(ADR-013)를 유지한다. 기본 ``fetch_workers=1``은 executor 없이
기존 순차 루프 그대로(배포 무변경 — 라이브 게이트 통과 전 운영자가 env로 켠다). DB 쓰기를
메인 스레드에 묶는 건 sqlite3 기본 ``check_same_thread=True`` 제약이기도 하다.
"""
from __future__ import annotations

import logging
import os
import threading
import time as _time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict

from bushexa.data.constants import SERACH_STOPS
from bushexa.services.crawl_settings import CrawlSettingsStore, default_crawl_settings_path
from bushexa.time_utils import KSTClock

logger = logging.getLogger("bushexa.crawler.arrival_poller")

_DEFAULT_POLL = 7.0  # 권장 5~10초 (ADR-010)
# E4: fetch 동시성 기본값. 1=기존 순차 루프와 동일(배포 무변경 — 게이트 방식).
# 라이브 smoke 게이트 통과 전에는 운영자가 env로 켠다(BUSHEXA_ARRIVAL_FETCH_WORKERS=4).
_DEFAULT_FETCH_WORKERS = 1


def _resolve_poll_seconds(explicit=None) -> float:
    if explicit is not None:
        return float(explicit)
    return float(os.environ.get("BUSHEXA_ARRIVAL_POLL_SECONDS", _DEFAULT_POLL))


def _resolve_fetch_workers(explicit=None) -> int:
    if explicit is not None:
        return max(1, int(explicit))
    return max(1, int(os.environ.get("BUSHEXA_ARRIVAL_FETCH_WORKERS", _DEFAULT_FETCH_WORKERS)))


def _scatter_fetch(client, stops, workers):
    """``stops`` 순서로 ``(stop_id, arrivals|None, exc|None)``를 yield한다(E4).

    워커는 fetch만 수행하고 공유 상태를 건드리지 않는다 — 예외는 future에 캡처되어
    호출자에게 값으로 전달된다(정류장별 격리, ADR-013). workers<=1이면 executor 없이
    기존 순차 호출 그대로다.
    """
    if workers <= 1 or len(stops) <= 1:
        for stop_id in stops:
            try:
                yield stop_id, client.fetch_arrivals(stop_id), None
            except Exception as exc:
                yield stop_id, None, exc
        return
    with ThreadPoolExecutor(max_workers=min(workers, len(stops))) as ex:
        futures = [(stop_id, ex.submit(client.fetch_arrivals, stop_id)) for stop_id in stops]
        for stop_id, fut in futures:
            try:
                yield stop_id, fut.result(), None
            except Exception as exc:
                yield stop_id, None, exc


def run_arrival_poller(config, *, repo=None, client=None, clock=None, sleep=None,
                       stop_event=None, poll_seconds=None, stops=None,
                       max_cycles=None, on_cycle=None, status_writer=None,
                       settings_store=None, fetch_workers=None) -> int:
    """도착정보 poller 루프. 반환: 수행한 사이클 수. ``stop_event.set()`` 시 현재 사이클 후 종료.

    설정 파일(``crawl_settings.json``)을 매 사이클 재읽으므로 arrival 폴링 주기 변경은
    다음 사이클부터(최대 현재 주기만큼 지연) 적용된다(ADR-013).

    Parameters
    ----------
    status_writer : optional
        ArrivalStatusWriter 인스턴스. 각 사이클 결과를 기록한다.
        None이면 기록하지 않는다(기존 동작 유지 — 기존 테스트 무영향).
    fetch_workers : optional
        fetch 동시성(E4). 기본 env ``BUSHEXA_ARRIVAL_FETCH_WORKERS``(=1, 순차 —
        라이브 게이트 통과 전 배포 무변경). >1이면 fetch만 병렬, 처리는 순차.
    """
    clock = clock or KSTClock()
    sleep = sleep or _time.sleep
    stop_event = stop_event or threading.Event()
    stops = list(stops) if stops is not None else list(SERACH_STOPS)
    poll_seconds = _resolve_poll_seconds(poll_seconds)
    fetch_workers = _resolve_fetch_workers(fetch_workers)
    if settings_store is None:
        data_dir = getattr(config, "data_dir", None)
        if data_dir is not None:
            settings_store = CrawlSettingsStore(default_crawl_settings_path(data_dir))

    if repo is None or client is None:
        from bushexa.api_clients.ulsan_bis import UlsanBisClient
        from bushexa.db.connection import create_connection
        from bushexa.db.repo_arrival import BusArrivalRepo
        from bushexa.db.schema import create_schema
        if repo is None:
            conn = create_connection(config.database_url)
            create_schema(conn)
            repo = BusArrivalRepo(conn)
        if client is None:
            client = UlsanBisClient(config.api_key)

    cycles = 0
    while not stop_event.is_set():
        cycle_started = clock.now()
        fetched_at = cycle_started.isoformat()
        ok = 0
        last_error: str | None = None
        # E4: fetch는 분산, upsert·집계는 메인 스레드에서 stops 순서로 순차(결정성 유지).
        for stop_id, arrivals, fetch_exc in _scatter_fetch(client, stops, fetch_workers):
            try:
                if fetch_exc is not None:
                    raise fetch_exc
                payload = [asdict(a) for a in arrivals]
                repo.upsert(stop_id, payload, fetched_at)
                ok += 1
            except Exception as exc:
                # ADR-013: 한 정류장 실패가 루프를 죽이지 않게 — 로그 후 다음 정류장.
                last_error = str(exc)
                logger.error("arrival poll 실패 stop=%s (계속): %s", stop_id, exc)
        logger.info("arrival cycle: %d/%d 정류장 백업 갱신", ok, len(stops))
        # 상태 기록 (주입된 writer가 있을 때만 — 기존 테스트 무영향)
        if status_writer is not None:
            try:
                status_writer.write(
                    cycle_started_at=cycle_started,
                    stops_ok=ok,
                    stops_total=len(stops),
                    last_error_msg=last_error,
                )
            except Exception as exc:
                logger.warning("arrival status 기록 실패: %s", exc)
        if on_cycle is not None:
            on_cycle(cycles)
        cycles += 1
        if max_cycles is not None and cycles >= max_cycles:
            break
        sleep(settings_store.arrival_poll_seconds(poll_seconds) if settings_store else poll_seconds)
    logger.info("arrival poller 종료(사이클 %d회 수행)", cycles)
    return cycles
