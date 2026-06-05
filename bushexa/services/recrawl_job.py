"""시간표 재크롤 잡 — 파일 기반 크로스 워커 구현 (#6).

기존 services/timetable_crawl.py(TimetableCrawlJob, 인메모리 큐)를 대체하는
파일 기반 구현. gunicorn sync 워커 2개가 각각 독립된 프로세스 메모리를 가지므로
인메모리 큐로는 start-POST 워커와 stream-GET 워커가 다를 때 404/409 오류가 발생한다.

이 모듈은 잡 메타와 진행 이벤트를 파일에 기록한다:
  - ``<data_dir>/timetable_crawl_job.json``:
      job_id, started_at, heartbeat, done, error
  - ``<data_dir>/timetable_crawl_progress.jsonl``:
      각 줄이 JSON 객체 (kind, payload_json, ts)

진행 프로토콜 (기존 SSE 형식 완전 호환):
  - ("progress", ProgressEvent dict) : 페이지 진행
  - ("done", None)                   : 정상 종료
  - ("error", str)                   : 실패 종료
스트림은 done/error에서 종결된다.

**SSE sync 워커 점유 경고**:
  progress() 메서드는 파일 폴링-tail(0.5s 간격)로 이벤트를 읽기 때문에
  gunicorn sync 워커 1개가 스트림 연결 시간 동안 완전히 점유된다.
  재크롤이 수 분 걸리면 그 동안 다른 요청은 나머지 워커만 처리한다.
  비동기(eventlet/gevent) 워커로 전환하거나 임시 크롤 결과가 필요한 경우에만 사용 권장.

**Linux 전제**: locked_update_json이 fcntl.flock을 사용하므로 Linux/macOS 환경 전용.
배포 환경이 Linux 컨테이너(Dockerfile)임을 가정한다.
"""
from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from bushexa import fileio

logger = logging.getLogger("bushexa.services.recrawl_job")

# heartbeat가 이 시간(초) 이상 오래되면 죽은 잡으로 간주하고 재시작 허용
_HEARTBEAT_TIMEOUT = 120
# heartbeat 갱신 주기(초)
_HEARTBEAT_INTERVAL = 10
# SSE 폴링 주기(초)
_POLL_INTERVAL = 0.5


# ConflictError를 timetable_crawl에서 re-export.
# 기존 테스트(test_admin_recrawl_sse.py)가 timetable_crawl.ConflictError를 임포트하고
# mock에서 raise하므로, admin.py의 "except ConflictError"가 같은 클래스를 잡으려면
# 여기서 동일 클래스를 사용해야 한다.
from bushexa.services.timetable_crawl import ConflictError  # noqa: F401 재-export


class RecrawlJob:
    """파일 기반 재크롤 잡 — start/progress 인터페이스는 TimetableCrawlJob과 동일.

    Parameters
    ----------
    crawl_fn:
        ``(*, vacation, on_progress) -> None`` 시그니처. admin.py _make_crawl_fn() 결과.
    data_dir:
        잡 메타·진행 JSONL이 저장될 디렉터리.
    """

    def __init__(self, crawl_fn, *, data_dir: Path) -> None:
        self._crawl_fn = crawl_fn
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)

    # ── 파일 경로 헬퍼 ────────────────────────────────────────────

    @property
    def _meta_path(self) -> Path:
        return self._data_dir / "timetable_crawl_job.json"

    @property
    def _progress_path(self) -> Path:
        return self._data_dir / "timetable_crawl_progress.jsonl"

    # ── 내부 상태 관리 ────────────────────────────────────────────

    def _load_meta(self) -> dict:
        """메타 JSON 로드. 부재·파손 시 빈 dict."""
        if not self._meta_path.exists():
            return {}
        try:
            return json.loads(self._meta_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _is_alive(self, meta: dict) -> bool:
        """잡이 실행 중이고 heartbeat가 살아있으면 True (#6 크로스 워커 가드)."""
        if not meta.get("job_id"):
            return False
        if meta.get("done") or meta.get("error"):
            return False
        heartbeat = meta.get("heartbeat") or meta.get("started_at")
        if heartbeat is None:
            return False
        age = time.time() - heartbeat
        return age < _HEARTBEAT_TIMEOUT

    def _preempt(self, job_id: str, vacation: bool) -> None:
        """locked_update_json으로 메타를 선점(이미 실행 중이면 ConflictError) (#6).

        진행 JSONL도 새로 초기화한다.
        """
        conflict_holder: list[bool] = [False]

        def _mutate(meta: dict) -> dict:
            if self._is_alive(meta):
                conflict_holder[0] = True
                return meta  # 잠금 내에서 실패 — 쓰기는 없어야 함
            # 새 잡으로 초기화
            meta.clear()
            meta.update({
                "job_id": job_id,
                "started_at": time.time(),
                "heartbeat": time.time(),
                "done": False,
                "error": None,
                "vacation": vacation,
            })
            return meta

        fileio.locked_update_json(self._meta_path, _mutate, default={})

        if conflict_holder[0]:
            raise ConflictError("이미 실행 중인 재크롤 잡이 있습니다 (크로스 워커 가드)")

        # 진행 JSONL 초기화 (새 잡 시작 시 이전 내용 제거)
        try:
            self._progress_path.write_text("", encoding="utf-8")
        except OSError as exc:
            logger.warning("진행 JSONL 초기화 실패: %s", exc)

    def _append_progress(self, kind: str, payload: Any) -> None:
        """진행 이벤트를 JSONL에 append (#6).

        각 줄: {"kind": "...", "payload": ..., "ts": <float>}
        payload가 dataclass면 dict로 직렬화.
        """
        if is_dataclass(payload) and not isinstance(payload, type):
            payload = asdict(payload)
        line = json.dumps({
            "kind": kind,
            "payload": payload,
            "ts": time.time(),
        }, ensure_ascii=False, default=str)
        try:
            with open(self._progress_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError as exc:
            logger.warning("진행 JSONL append 실패: %s", exc)

    def _update_heartbeat(self, job_id: str) -> None:
        """메타의 heartbeat 타임스탬프를 갱신 (#6)."""
        def _mutate(meta: dict) -> dict:
            if meta.get("job_id") == job_id:
                meta["heartbeat"] = time.time()
            return meta
        try:
            fileio.locked_update_json(self._meta_path, _mutate, default={})
        except Exception as exc:
            logger.warning("heartbeat 갱신 실패: %s", exc)

    def _mark_done(self, job_id: str) -> None:
        """잡 정상 종료 기록."""
        def _mutate(meta: dict) -> dict:
            if meta.get("job_id") == job_id:
                meta["done"] = True
                meta["heartbeat"] = time.time()
            return meta
        try:
            fileio.locked_update_json(self._meta_path, _mutate, default={})
        except Exception as exc:
            logger.warning("done 기록 실패: %s", exc)

    def _mark_error(self, job_id: str, error: Exception) -> None:
        """잡 실패 종료 기록."""
        def _mutate(meta: dict) -> dict:
            if meta.get("job_id") == job_id:
                meta["error"] = str(error)
                meta["heartbeat"] = time.time()
            return meta
        try:
            fileio.locked_update_json(self._meta_path, _mutate, default={})
        except Exception as exc:
            logger.warning("error 기록 실패: %s", exc)

    # ── 공개 API (TimetableCrawlJob 인터페이스 호환) ───────────────

    def start(self, *, vacation: bool = False) -> str:
        """재크롤 잡을 시작하고 job_id를 반환한다.

        이미 실행 중인 잡이 있으면 ConflictError 발생 (크로스 워커 가드 #6).
        백그라운드 스레드가 진행마다 JSONL에 append하고 heartbeat를 주기적으로 갱신.
        """
        job_id = uuid.uuid4().hex
        # locked_update_json으로 선점 (크로스 워커 409 가드)
        self._preempt(job_id, vacation)

        crawl_fn = self._crawl_fn

        def worker() -> None:
            """백그라운드 스레드: 크롤 실행, heartbeat, 진행 JSONL 기록."""
            hb_time = time.time()
            try:
                def on_progress(event):
                    nonlocal hb_time
                    self._append_progress("progress", event)
                    # _HEARTBEAT_INTERVAL마다 heartbeat 갱신
                    now = time.time()
                    if now - hb_time >= _HEARTBEAT_INTERVAL:
                        self._update_heartbeat(job_id)
                        hb_time = now

                crawl_fn(vacation=vacation, on_progress=on_progress)
                self._mark_done(job_id)
                self._append_progress("done", None)
            except Exception as exc:
                logger.error("시간표 재크롤 실패: %s", exc)
                self._mark_error(job_id, exc)
                self._append_progress("error", str(exc))

        t = threading.Thread(target=worker, name=f"recrawl-{job_id[:8]}", daemon=True)
        t.start()
        return job_id

    def progress(self, job_id: str):
        """job_id의 진행 이벤트를 done/error까지 yield한다 (#6).

        파일 폴링-tail 방식:
          - _progress_path의 새 줄을 0.5초 간격으로 읽는다.
          - 메타에서 done/error 확인 후 스트림 종결.
          - job_id가 현재 메타와 다르면 KeyError (→ 라우트가 404 반환).

        SSE 형식은 기존 TimetableCrawlJob.progress와 동일 (admin.py JS 무수정).
        """
        meta = self._load_meta()
        if meta.get("job_id") != job_id:
            raise KeyError(f"알 수 없는 job_id: {job_id}")

        offset = 0  # 파일 읽기 오프셋 (줄 단위)

        while True:
            # 새 이벤트 줄 읽기
            try:
                with open(self._progress_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
            except (OSError, FileNotFoundError):
                lines = []

            for line in lines[offset:]:
                line = line.strip()
                if not line:
                    continue
                offset += 1
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue

                kind = rec.get("kind", "")
                payload_raw = rec.get("payload")

                # dataclass 복원: progress payload는 dict로 yield (SSE 형식 호환)
                if kind == "progress":
                    yield ("progress", payload_raw)
                elif kind == "done":
                    yield ("done", None)
                    return
                elif kind == "error":
                    yield ("error", Exception(payload_raw or "unknown error"))
                    return

            # 메타 확인: done/error가 기록됐고 새 줄도 없으면 종결
            meta = self._load_meta()
            if meta.get("job_id") != job_id:
                # 잡 ID가 바뀐 경우 — 이전 잡 스트림이 교체됨
                return
            if meta.get("done") or meta.get("error"):
                # 아직 JSONL에서 done/error를 못 읽었지만 메타에 기록됨 → 잠깐 대기 후 재시도
                time.sleep(_POLL_INTERVAL)
                try:
                    with open(self._progress_path, "r", encoding="utf-8") as f:
                        lines = f.readlines()
                except (OSError, FileNotFoundError):
                    lines = []
                for line in lines[offset:]:
                    line = line.strip()
                    if not line:
                        continue
                    offset += 1
                    try:
                        rec = json.loads(line)
                    except ValueError:
                        continue
                    kind = rec.get("kind", "")
                    payload_raw = rec.get("payload")
                    if kind == "progress":
                        yield ("progress", payload_raw)
                    elif kind == "done":
                        yield ("done", None)
                        return
                    elif kind == "error":
                        yield ("error", Exception(payload_raw or "unknown error"))
                        return
                # 여전히 못 찾으면 종결 (안전 탈출)
                if meta.get("done"):
                    yield ("done", None)
                elif meta.get("error"):
                    yield ("error", Exception(meta["error"] or "unknown error"))
                return

            time.sleep(_POLL_INTERVAL)

    @property
    def is_running(self) -> bool:
        """현재 실행 중인 잡이 있으면 True."""
        return self._is_alive(self._load_meta())
