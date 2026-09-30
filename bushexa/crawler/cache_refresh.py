"""cache-refresh 데몬 — 저빈도 데이터(공휴일·시간표)를 유휴시간에 백엔드에서만 갱신.

배경: 공휴일/버스 시간표는 하루에도 자주 변하지 않는다. 화면 요청 경로에서 외부 API를
동기 호출하면(과거 board의 공휴일 호출) cold 지연이 발생한다. 이 워커가 새벽 유휴시간
(기본 02–03시)에 하루 1회 data.go.kr 공휴일 API·울산 시간표·TAGO 철도(열차·동해선) 시간표를
호출해 영속 캐시(``holiday_cache.json`` / ``data/timetable/*.json`` / ``rail_timetable.json``)에
적재하고, 화면은 그 캐시만 읽는다.

govtrack/arrival 데몬과 동일한 graceful 종료·sleep/clock 주입 패턴을 따른다(테스트 결정성).
부팅 직후엔 공휴일만 즉시 1회 갱신해(가벼움) 읽기 경로가 빈 캐시로 시작하지 않게 하고,
철도 시간표는 그날 아직 성공한 적이 없을 때만 부팅 시 받는다(호출 40회 안팎, 재시작마다 반복 방지).
무거운 시간표 재크롤은 새벽 윈도에서만 수행한다(매 재시작마다 전 노선 재크롤 방지).
"""
from __future__ import annotations

import logging
import threading
import time as _time
from datetime import time

from bushexa.services.holiday_service import (
    HolidayCache,
    default_holiday_cache_path,
    upcoming_months,
)
from bushexa.time_utils import KSTClock

logger = logging.getLogger("bushexa.crawler.cache_refresh")

# 새벽 유휴시간 갱신 윈도(KST). govtrack 데몬의 night window(01–05)와 겹치되 더 좁게 둔다.
_WINDOW = (time(2, 0), time(3, 0))


def refresh_holidays(config, *, client=None, clock=None) -> set[str]:
    """공휴일 캐시를 이번 달+다음 달로 갱신. 갱신 후 전체 공휴일 set 반환."""
    clock = clock or KSTClock()
    if client is None:
        from bushexa.api_clients.holiday import HolidayClient
        client = HolidayClient(config.api_key)
    cache = HolidayCache(default_holiday_cache_path(config.data_dir))
    return cache.refresh(client, upcoming_months(clock.now().date(), 2))


def refresh_timetables(config, *, client=None, on_progress=None) -> dict:
    """전 노선 울산 시간표를 재크롤해 ``data/timetable/*.json``에 적재."""
    from bushexa.api_clients.ulsan_bis import UlsanBisClient
    from bushexa.crawler.timetable_crawl import crawl_all_timetables
    if client is None:
        client = UlsanBisClient(config.api_key)
    return crawl_all_timetables(client, on_progress=on_progress)


def refresh_rail(config, *, clock=None, only_if_stale=False,
                 train_client=None, subway_client=None) -> None:
    """TAGO 열차·동해선 시간표를 ``rail_timetable.json`` 에 갱신. 두 절은 서로 격리.

    ``only_if_stale`` 면 오늘 이미 실패 없이 갱신된 절은 건너뛴다(부팅 경로).
    """
    from bushexa.services.rail_timetable import (
        default_rail_path,
        refresh_metro,
        refresh_trains,
        refreshed_today,
    )
    clock = clock or KSTClock()
    path = default_rail_path(config.data_dir)
    today = clock.now().date()
    if not (only_if_stale and refreshed_today(path, "trains", today)):
        try:
            if train_client is None:
                from bushexa.api_clients.tago_rail import TrainInfoClient
                train_client = TrainInfoClient(config.api_key)
            from bushexa.services.holiday_service import read_effective_holidays
            holidays = read_effective_holidays(config.data_dir)
            logger.info("열차 시간표 갱신: %s", refresh_trains(train_client, path, clock=clock,
                                                         holiday_set=holidays))
        except Exception as exc:
            logger.error("열차 시간표 갱신 실패(계속): %s", exc, exc_info=True)
    if not (only_if_stale and refreshed_today(path, "metro", today)):
        try:
            if subway_client is None:
                from bushexa.api_clients.tago_rail import SubwayInfoClient
                subway_client = SubwayInfoClient(config.api_key)
            logger.info("동해선 시간표 갱신: %s", refresh_metro(subway_client, path, clock=clock))
        except Exception as exc:
            logger.error("동해선 시간표 갱신 실패(계속): %s", exc, exc_info=True)


def refresh_all(config, *, do_timetable=True, clock=None) -> None:
    """공휴일·철도(+선택적으로 버스 시간표)를 갱신. 한쪽 실패가 다른 쪽을 막지 않는다.

    철도는 ``do_timetable`` 이 거짓(부팅 경로)이면 오늘 갱신이 안 된 경우에만 받는다.
    """
    try:
        holidays = refresh_holidays(config, clock=clock)
        logger.info("공휴일 캐시 갱신 완료: 총 %d건", len(holidays))
    except Exception as exc:  # 방어: 갱신 실패가 데몬을 죽이지 않게(ADR-013)
        logger.error("공휴일 캐시 갱신 실패(계속): %s", exc, exc_info=True)
    try:
        refresh_rail(config, clock=clock, only_if_stale=not do_timetable)
    except Exception as exc:
        logger.error("철도 시간표 갱신 실패(계속): %s", exc, exc_info=True)
    if do_timetable:
        try:
            written = refresh_timetables(config)
            logger.info("시간표 재크롤 완료: %d개 노선", len(written))
        except Exception as exc:
            logger.error("시간표 재크롤 실패(계속): %s", exc, exc_info=True)


def _in_window(now_t, window) -> bool:
    start, end = window
    return start <= now_t < end


def run_cache_refresh_loop(
    config,
    *,
    refresh=None,
    clock=None,
    sleep=None,
    stop_event=None,
    window=_WINDOW,
    check_seconds=600,
    run_on_start=True,
    max_iterations=None,
) -> int:
    """유휴시간 캐시 갱신 루프. 반환: 수행한 체크 반복 횟수.

    하루 1회 ``window`` 안에서 ``refresh(do_timetable=True)`` 를 호출하고, 같은 날 중복
    실행을 막기 위해 마지막 성공 날짜를 추적한다. ``run_on_start`` 면 부팅 시 공휴일만
    1회 갱신(시간표 제외)해 읽기 경로가 즉시 캐시를 갖게 한다.

    Parameters
    ----------
    refresh : Callable[[bool], None] | None
        ``refresh(do_timetable)`` 형태. 기본은 :func:`refresh_all`. 테스트는 대역 주입.
    check_seconds : float
        윈도 진입을 확인하는 폴링 간격(기본 600초).
    max_iterations : int | None
        테스트용 — 지정 시 해당 횟수만큼 체크 후 종료.
    """
    clock = clock or KSTClock()
    sleep = sleep or _time.sleep
    stop_event = stop_event or threading.Event()
    if refresh is None:
        def refresh(do_timetable, _config=config):
            refresh_all(_config, do_timetable=do_timetable)

    if run_on_start:
        try:
            refresh(False)  # 부팅: 공휴일만(가벼움). 무거운 시간표는 새벽 윈도에서만.
        except Exception as exc:
            logger.error("부팅 시 공휴일 갱신 실패(계속): %s", exc, exc_info=True)

    last_run_date = None
    iterations = 0
    while not stop_event.is_set():
        now = clock.now()
        if _in_window(now.time(), window) and last_run_date != now.date():
            try:
                refresh(True)
                last_run_date = now.date()  # 성공 시에만 기록 → 실패는 윈도 내 재시도
            except Exception as exc:
                logger.error("유휴시간 캐시 갱신 실패(다음 체크에 재시도): %s", exc, exc_info=True)
        iterations += 1
        if max_iterations is not None and iterations >= max_iterations:
            break
        sleep(check_seconds)
    logger.info("cache-refresh 데몬 종료(체크 %d회 수행)", iterations)
    return iterations
