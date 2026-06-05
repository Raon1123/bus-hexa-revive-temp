"""W5 시간표 재크롤 Job 어댑터 검증. 기대값은 주입한 crawl_fn 동작에서 직접 도출(E-13)."""
from __future__ import annotations

import threading

import pytest

from bushexa.crawler.timetable_crawl import ProgressEvent
from bushexa.services.timetable_crawl import ConflictError, TimetableCrawlJob


def test_start_and_progress():
    """mock 크롤 함수로 start 후 progress를 소비하면 progress 이벤트들 뒤에 done 이벤트가 와서
    스트림이 종료되는지 검증한다 — F04 AC-R3."""
    def fake_crawl(*, vacation, on_progress):
        on_progress(ProgressEvent("713", 0, 1))
        on_progress(ProgressEvent("713", 0, 2))

    job = TimetableCrawlJob(fake_crawl)
    jid = job.start(vacation=False)
    events = list(job.progress(jid))

    kinds = [k for k, _ in events]
    assert kinds == ["progress", "progress", "done"]
    assert events[0][1].page == 1
    assert events[1][1].page == 2


def test_conflict():
    """한 job이 실행 중일 때 두 번째 start 호출이 ConflictError를 던지는지 검증한다 — F04 AC-R5."""
    release = threading.Event()

    def blocking_crawl(*, vacation, on_progress):
        release.wait(timeout=2.0)  # 테스트가 풀어줄 때까지 실행 중 상태 유지

    job = TimetableCrawlJob(blocking_crawl)
    job.start(vacation=False)
    try:
        with pytest.raises(ConflictError):
            job.start(vacation=False)
    finally:
        release.set()  # 첫 job 워커 정리


def test_error_event_on_failure():
    """크롤 함수가 예외를 던지면 progress가 error 이벤트로 종결되는지 검증한다 — F04 AC-R4."""
    def failing_crawl(*, vacation, on_progress):
        on_progress(ProgressEvent("713", 0, 1))
        raise RuntimeError("boom")

    job = TimetableCrawlJob(failing_crawl)
    jid = job.start(vacation=False)
    events = list(job.progress(jid))

    assert events[0][0] == "progress"
    assert events[-1][0] == "error"
    assert isinstance(events[-1][1], RuntimeError)
