"""W3 night window (H7 회귀). 새벽 구간에서 sleep이 night_sleep_seconds로 단축되는지."""
from __future__ import annotations

import threading
from datetime import datetime
from zoneinfo import ZoneInfo

from bushexa.crawler.daemon import run_daemon

KST = ZoneInfo("Asia/Seoul")


class _NightClock:
    """새벽 2시 — night window(01:00~05:00) 안."""

    def now(self):
        return datetime(2026, 6, 1, 2, 0, 0, tzinfo=KST)


class _NoCallRecorder:
    """run_cycle이 불리면 즉시 실패(새벽엔 폴링하지 않아야 함)."""

    def run_cycle(self, **kw):
        raise AssertionError("night window에서는 run_cycle이 호출되면 안 된다")


def test_short_sleep_in_night_window():
    """clock을 새벽 2시로 고정하면 sleep 인자가 night_sleep_seconds(60)로 호출되는지 검증한다 — H7 회귀.

    (legacy는 600초를 sleep해 막차/첫차 데이터 공백을 키웠다. 60초로 위험 구간을 좁힌다.)
    """
    stop = threading.Event()
    sleeps: list[float] = []

    def fake_sleep(seconds):
        sleeps.append(seconds)
        stop.set()  # 첫 sleep 후 루프 종료

    run_daemon(config=None, recorder=_NoCallRecorder(), clock=_NightClock(),
               sleep=fake_sleep, stop_event=stop,
               poll_seconds=10, night_sleep_seconds=60)

    assert sleeps == [60]  # poll_seconds(10)가 아니라 night_sleep_seconds(60)
