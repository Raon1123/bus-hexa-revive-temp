"""cache-refresh 데몬 루프 단위 테스트 (clock/sleep/refresh 주입, 네트워크 없음)."""
from __future__ import annotations

import threading
from datetime import datetime
from zoneinfo import ZoneInfo

from bushexa.crawler.cache_refresh import run_cache_refresh_loop

KST = ZoneInfo("Asia/Seoul")


class _Clock:
    def __init__(self, dt):
        self._dt = dt

    def now(self):
        return self._dt


def _recorder():
    """refresh 대역: 호출된 do_timetable 인자들을 기록."""
    calls: list[bool] = []

    def refresh(do_timetable):
        calls.append(do_timetable)

    return refresh, calls


def test_run_on_start_refreshes_holidays_only():
    """부팅 시 공휴일만(do_timetable=False) 1회 갱신하고, 윈도 밖이면 추가 갱신 없음."""
    refresh, calls = _recorder()
    stop = threading.Event()
    run_cache_refresh_loop(
        config=None, refresh=refresh,
        clock=_Clock(datetime(2026, 6, 1, 12, 0, tzinfo=KST)),  # 정오: 윈도 밖
        sleep=lambda s: None, stop_event=stop,
        run_on_start=True, max_iterations=1,
    )
    assert calls == [False]


def test_no_refresh_outside_window():
    refresh, calls = _recorder()
    run_cache_refresh_loop(
        config=None, refresh=refresh,
        clock=_Clock(datetime(2026, 6, 1, 12, 0, tzinfo=KST)),
        sleep=lambda s: None, stop_event=threading.Event(),
        run_on_start=False, max_iterations=3,
    )
    assert calls == []


def test_refresh_in_window_runs_full_once_per_day():
    """윈도(02–03시) 안이면 do_timetable=True로 갱신하되, 같은 날 중복 실행하지 않는다."""
    refresh, calls = _recorder()
    run_cache_refresh_loop(
        config=None, refresh=refresh,
        clock=_Clock(datetime(2026, 6, 1, 2, 30, tzinfo=KST)),  # 윈도 안, 고정
        sleep=lambda s: None, stop_event=threading.Event(),
        run_on_start=False, max_iterations=5,
    )
    assert calls == [True]  # 5회 체크해도 같은 날엔 1회만


def test_failure_in_window_is_retried():
    """윈도 내 갱신이 실패하면 last_run_date를 기록하지 않아 다음 체크에 재시도한다."""
    calls: list[bool] = []

    def refresh(do_timetable):
        calls.append(do_timetable)
        raise RuntimeError("boom")  # 매번 실패

    run_cache_refresh_loop(
        config=None, refresh=refresh,
        clock=_Clock(datetime(2026, 6, 1, 2, 30, tzinfo=KST)),
        sleep=lambda s: None, stop_event=threading.Event(),
        run_on_start=False, max_iterations=3,
    )
    assert calls == [True, True, True]  # 실패 → 매 체크 재시도


def test_stop_event_breaks_loop():
    refresh, calls = _recorder()
    stop = threading.Event()

    def sleep(_s):
        stop.set()  # 첫 sleep 후 종료 신호

    iterations = run_cache_refresh_loop(
        config=None, refresh=refresh,
        clock=_Clock(datetime(2026, 6, 1, 12, 0, tzinfo=KST)),
        sleep=sleep, stop_event=stop, run_on_start=False,
    )
    assert iterations == 1
