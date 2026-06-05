"""울산 BIS 도착정보 poller (W9, ADR-010).

화면이 울산 API를 직접·빈번히 호출하면 시간 오차가 발생한다(사용자 보고). 그래서 도착정보는
**사용자 트래픽과 무관한 고정 주기 데몬**이 5~10초 간격으로 폴링해 ``bus_arrival_cache``에
백업하고, 화면은 그 백업본만 읽는다. 호출 빈도는 화면 요청 수가 아니라 사이클 수에만 비례한다.

graceful 종료·sleep 주입 패턴은 govtrack daemon과 동일(테스트 결정성). 정류장별 호출 실패는
로그만 남기고 다음 정류장으로 계속한다(ADR-013).
"""
from __future__ import annotations

import logging
import os
import threading
import time as _time
from dataclasses import asdict

from bushexa.data.constants import SERACH_STOPS
from bushexa.time_utils import KSTClock

logger = logging.getLogger("bushexa.crawler.arrival_poller")

_DEFAULT_POLL = 7.0  # 권장 5~10초 (ADR-010)


def _resolve_poll_seconds(explicit=None) -> float:
    if explicit is not None:
        return float(explicit)
    return float(os.environ.get("BUSHEXA_ARRIVAL_POLL_SECONDS", _DEFAULT_POLL))


def run_arrival_poller(config, *, repo=None, client=None, clock=None, sleep=None,
                       stop_event=None, poll_seconds=None, stops=None,
                       max_cycles=None, on_cycle=None, status_writer=None) -> int:
    """도착정보 poller 루프. 반환: 수행한 사이클 수. ``stop_event.set()`` 시 현재 사이클 후 종료.

    Parameters
    ----------
    status_writer : optional
        ArrivalStatusWriter 인스턴스. 각 사이클 결과를 기록한다.
        None이면 기록하지 않는다(기존 동작 유지 — 기존 테스트 무영향).
    """
    clock = clock or KSTClock()
    sleep = sleep or _time.sleep
    stop_event = stop_event or threading.Event()
    stops = list(stops) if stops is not None else list(SERACH_STOPS)
    poll_seconds = _resolve_poll_seconds(poll_seconds)

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
        for stop_id in stops:
            try:
                arrivals = client.fetch_arrivals(stop_id)
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
        sleep(poll_seconds)
    logger.info("arrival poller 종료(사이클 %d회 수행)", cycles)
    return cycles
