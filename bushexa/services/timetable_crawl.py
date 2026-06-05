"""시간표 재크롤 Job 어댑터 (W5).

W4의 ``crawl_all_timetables``를 백그라운드 스레드로 실행하고 진행상황을 queue로 스트리밍한다
(관리자 F04의 SSE가 소비). 이미 실행 중인 job이 있으면 두 번째 start는 ``ConflictError``
(중복 재크롤로 인한 API 과호출·파일 경합 방지, F04 AC-R5).

진행 프로토콜: ``progress()``는 ``(kind, payload)`` 튜플을 yield한다.
- ``("progress", ProgressEvent)`` : 페이지 진행
- ``("done", None)``              : 정상 종료
- ``("error", Exception)``        : 실패 종료
스트림은 done/error에서 종결된다(F04 AC-R3/R4).
"""
from __future__ import annotations

import logging
import queue
import threading
import uuid

logger = logging.getLogger("bushexa.services.timetable_crawl")


class ConflictError(RuntimeError):
    """이미 실행 중인 재크롤 job이 있을 때 두 번째 start에서 발생."""


class TimetableCrawlJob:
    def __init__(self, crawl_fn):
        """``crawl_fn``: ``(*, vacation, on_progress) -> None`` 시그니처의 재크롤 함수.
        실제 배선은 W4 ``crawl_all_timetables``에 config/client를 바인딩한 closure를 넘긴다."""
        self._crawl_fn = crawl_fn
        self._lock = threading.Lock()
        self._running = False
        self._job_id: str | None = None
        self._queue: queue.Queue | None = None
        self._thread: threading.Thread | None = None

    def start(self, *, vacation: bool = False) -> str:
        with self._lock:
            if self._running:
                raise ConflictError("이미 실행 중인 재크롤 job이 있습니다")
            self._running = True
            self._job_id = uuid.uuid4().hex
            self._queue = queue.Queue()
            q, jid = self._queue, self._job_id

        def worker() -> None:
            try:
                self._crawl_fn(vacation=vacation,
                               on_progress=lambda e: q.put(("progress", e)))
                q.put(("done", None))
            except Exception as exc:  # 실패도 스트림으로 알린다(침묵 금지)
                logger.error("시간표 재크롤 실패: %s", exc)
                q.put(("error", exc))
            finally:
                with self._lock:
                    self._running = False

        self._thread = threading.Thread(target=worker, name=f"timetable-crawl-{jid}",
                                        daemon=True)
        self._thread.start()
        return jid

    def progress(self, job_id: str):
        """job_id의 진행 이벤트를 done/error까지 yield한다."""
        if job_id != self._job_id or self._queue is None:
            raise KeyError(f"알 수 없는 job_id: {job_id}")
        q = self._queue
        while True:
            kind, payload = q.get()
            yield kind, payload
            if kind in ("done", "error"):
                return

    @property
    def is_running(self) -> bool:
        return self._running
