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


def test_run_on_start_failure_does_not_kill_loop():
    """부팅 시 공휴일 갱신이 예외를 던져도 루프가 시작되어 체크를 계속하는지 검증한다(ADR-013)."""
    calls: list[bool] = []

    def refresh(do_timetable):
        calls.append(do_timetable)
        if not do_timetable:
            raise RuntimeError("holiday api down")

    iterations = run_cache_refresh_loop(
        config=None, refresh=refresh,
        clock=_Clock(datetime(2026, 6, 1, 2, 30, tzinfo=KST)),  # 윈도 안
        sleep=lambda s: None, stop_event=threading.Event(),
        run_on_start=True, max_iterations=2,
    )
    assert iterations == 2
    assert calls == [False, True]  # 부팅 실패 후에도 윈도 갱신은 수행


def test_window_refresh_runs_again_next_day():
    """윈도 갱신이 날짜 단위로 1회씩 — 다음 날 윈도에서는 다시 수행되는지 검증한다."""
    refresh, calls = _recorder()
    days = iter([
        datetime(2026, 6, 1, 2, 10, tzinfo=KST),
        datetime(2026, 6, 1, 2, 20, tzinfo=KST),
        datetime(2026, 6, 2, 2, 10, tzinfo=KST),
    ])

    class _SeqClock:
        def now(self):
            return next(days)

    run_cache_refresh_loop(
        config=None, refresh=refresh, clock=_SeqClock(),
        sleep=lambda s: None, stop_event=threading.Event(),
        run_on_start=False, max_iterations=3,
    )
    assert calls == [True, True]  # 6/1 1회 + 6/2 1회


def test_window_end_is_exclusive():
    """윈도 종료 시각(03:00)은 윈도 밖 — 갱신하지 않는지 검증한다(start <= t < end)."""
    refresh, calls = _recorder()
    run_cache_refresh_loop(
        config=None, refresh=refresh,
        clock=_Clock(datetime(2026, 6, 1, 3, 0, tzinfo=KST)),
        sleep=lambda s: None, stop_event=threading.Event(),
        run_on_start=False, max_iterations=1,
    )
    assert calls == []


def test_refresh_all_isolates_holiday_failure(monkeypatch):
    """refresh_all에서 공휴일 갱신이 실패해도 시간표 재크롤은 수행되는지 검증한다(한쪽 실패 격리)."""
    from bushexa.crawler import cache_refresh

    order: list[str] = []

    def bad_holidays(config, clock=None):
        order.append("holiday")
        raise RuntimeError("boom")

    monkeypatch.setattr(cache_refresh, "refresh_holidays", bad_holidays)
    monkeypatch.setattr(cache_refresh, "refresh_timetables",
                        lambda config: order.append("timetable") or {})

    cache_refresh.refresh_all(None, do_timetable=True)
    assert order == ["holiday", "timetable"]


def test_refresh_all_isolates_timetable_failure_and_skips_when_disabled(monkeypatch):
    """시간표 재크롤 예외는 삼켜지고, do_timetable=False면 시간표는 호출되지 않는지 검증한다."""
    from bushexa.crawler import cache_refresh

    order: list[str] = []
    monkeypatch.setattr(cache_refresh, "refresh_holidays",
                        lambda config, clock=None: order.append("holiday") or set())

    def bad_tt(config):
        order.append("timetable")
        raise RuntimeError("ulsan down")

    monkeypatch.setattr(cache_refresh, "refresh_timetables", bad_tt)

    cache_refresh.refresh_all(None, do_timetable=True)   # 예외 전파 없음
    cache_refresh.refresh_all(None, do_timetable=False)
    assert order == ["holiday", "timetable", "holiday"]


def test_refresh_holidays_writes_cache_for_current_and_next_month(app_config_test):
    """refresh_holidays가 clock 기준 이번 달+다음 달을 조회해 holiday_cache.json에 적재하는지 검증한다."""
    from datetime import date

    from bushexa.crawler.cache_refresh import refresh_holidays
    from bushexa.services.holiday_service import HolidayCache, default_holiday_cache_path

    class _Client:
        def __init__(self):
            self.asked = []

        def fetch(self, year, month):
            self.asked.append((year, month))
            return [date(2026, 6, 6)] if month == 6 else []

    client = _Client()
    app_config_test.data_dir.mkdir(parents=True, exist_ok=True)
    result = refresh_holidays(app_config_test, client=client,
                              clock=_Clock(datetime(2026, 6, 15, 12, 0, tzinfo=KST)))

    assert client.asked == [(2026, 6), (2026, 7)]
    assert result == {"20260606"}
    cache = HolidayCache(default_holiday_cache_path(app_config_test.data_dir))
    assert cache.load() == {"20260606"}


def test_refresh_all_runs_rail_stale_only_on_boot_and_isolates_failure(monkeypatch):
    """refresh_all 은 철도 갱신을 부팅(do_timetable=False)에는 only_if_stale 로, 새벽에는 강제로 부르고,
    철도 실패가 버스 시간표 재크롤을 막지 않는다."""
    from bushexa.crawler import cache_refresh

    rail_calls, tt_calls = [], []
    monkeypatch.setattr(cache_refresh, "refresh_holidays", lambda *a, **k: set())

    def bad_rail(config, *, clock=None, only_if_stale=False):
        rail_calls.append(only_if_stale)
        raise RuntimeError("rail down")

    monkeypatch.setattr(cache_refresh, "refresh_rail", bad_rail)
    monkeypatch.setattr(cache_refresh, "refresh_timetables",
                        lambda *a, **k: tt_calls.append(1) or [])
    cache_refresh.refresh_all(None, do_timetable=False)
    cache_refresh.refresh_all(None, do_timetable=True)
    assert rail_calls == [True, False]
    assert tt_calls == [1]


def test_refresh_rail_isolates_train_failure_and_skips_fresh_sections(tmp_path):
    """열차 조회 전체 실패가 동해선 갱신을 막지 않고, only_if_stale 면 오늘 성공한 절은 건너뛴다."""
    from types import SimpleNamespace

    from bushexa.crawler.cache_refresh import refresh_rail
    from bushexa.services.rail_timetable import default_rail_path, refreshed_today

    class _Trains:
        calls = 0

        def fetch_trains(self, *a):
            _Trains.calls += 1
            raise RuntimeError("down")

    class _Metro:
        calls = 0

        def fetch_station_schedule(self, *a):
            _Metro.calls += 1
            return []

    cfg = SimpleNamespace(data_dir=tmp_path, api_key="k")
    clock = _Clock(datetime(2026, 9, 29, 2, 30, tzinfo=KST))
    refresh_rail(cfg, clock=clock, train_client=_Trains(), subway_client=_Metro())
    path = default_rail_path(tmp_path)
    assert not refreshed_today(path, "trains", clock.now().date())
    assert refreshed_today(path, "metro", clock.now().date())
    metro_calls = _Metro.calls
    refresh_rail(cfg, clock=clock, only_if_stale=True, train_client=_Trains(), subway_client=_Metro())
    assert _Metro.calls == metro_calls          # 오늘 성공 → 건너뜀
    assert _Trains.calls > 0
