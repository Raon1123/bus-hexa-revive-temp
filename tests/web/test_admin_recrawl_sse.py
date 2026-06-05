"""W13b 테스트: admin recrawl SSE (F04, TP-010).

E-13 준수: 기대값은 구현 독립 출처에서 온다.
- test_stream: TP-010 §2/§6 "progress 이벤트 ≥1회 후 done으로 스트림 종료".
- test_conflict: TP-010 §6 "진행 중 2번째 POST → 409 Conflict".
- test_cross_worker_sse_via_http: #6 spec "새 app 인스턴스(다른 워커)에서 SSE GET 가능".

mock TimetableCrawlJob을 app.config["_TIMETABLE_CRAWL_JOB"]에 주입한다
(admin.py _get_crawl_job이 setdefault로 읽으므로 mock이 우선).
CSRF: 세션 토큰 + 폼 필드.
"""
from __future__ import annotations

from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from bushexa.config import AppConfig
from bushexa.services.timetable_crawl import ConflictError
from bushexa.web.app import create_app

_KST = ZoneInfo("Asia/Seoul")
_CSRF = "test-csrf-token"


@pytest.fixture
def app(tmp_path):
    config = AppConfig(
        api_key="test-api-key",
        database_url="sqlite:///:memory:",
        session_secret="test-secret",
        manager_password_path=tmp_path / "manager_password.txt",
        data_dir=tmp_path / "data",
        tz=_KST,
        log_level="DEBUG",
        log_dir=tmp_path / "logs",
    )
    return create_app(config)


def _authed(client):
    with client.session_transaction() as sess:
        sess["admin_authed"] = True
        sess["csrf_token"] = _CSRF


# ──────────────────────────────────────────────────
# mock job: progress ≥1회 후 done
# ──────────────────────────────────────────────────

class _MockStreamJob:
    """start → 고정 job_id; progress → progress 1건 후 done yield."""

    def __init__(self) -> None:
        self.started_with = None

    def start(self, *, vacation: bool = False) -> str:
        self.started_with = vacation
        return "job-abc"

    def progress(self, job_id: str):
        if job_id != "job-abc":
            raise KeyError(job_id)
        # progress(route/day/page) ≥1회 후 done — TP-010 §2.
        yield ("progress", {"route": "713", "day": 0, "page": 1})
        yield ("done", None)


class _MockConflictJob:
    """start → 항상 ConflictError(이미 진행 중 시뮬레이션)."""

    def start(self, *, vacation: bool = False) -> str:
        raise ConflictError("이미 실행 중")

    def progress(self, job_id: str):
        raise KeyError(job_id)


# ──────────────────────────────────────────────────
# AC-1: SSE progress ≥1 후 done 종결
# ──────────────────────────────────────────────────

def test_stream(app):
    """recrawl 시작 → SSE 소비 시 progress ≥1 후 done으로 종료 (TP-010 AC-1)."""
    app.config["_TIMETABLE_CRAWL_JOB"] = _MockStreamJob()
    client = app.test_client()
    _authed(client)

    # 1) 재크롤 시작 → job_id JSON.
    start = client.post(
        "/admin/timetable/recrawl",
        data={"csrf_token": _CSRF, "vacation": "off"},
    )
    assert start.status_code == 200, f"recrawl start expected 200, got {start.status_code}"
    job_id = start.get_json()["job_id"]
    assert job_id == "job-abc"

    # 2) SSE 소비.
    stream = client.get(f"/admin/timetable/recrawl/{job_id}/stream")
    assert stream.status_code == 200
    assert stream.mimetype == "text/event-stream", (
        f"SSE Content-Type expected text/event-stream, got {stream.mimetype}"
    )
    body = stream.get_data(as_text=True)

    # progress 이벤트 ≥1 후 done (독립 출처: TP-010 §2/§6).
    assert "event: progress" in body, "progress 이벤트가 1건 이상이어야 함"
    assert "event: done" in body, "done 이벤트로 종결되어야 함"
    # 순서: 첫 progress가 done보다 앞.
    assert body.index("event: progress") < body.index("event: done"), (
        "progress가 done보다 먼저 와야 함"
    )
    # SSE 형식: `event: <type>\ndata: <...>\n\n`.
    assert "data:" in body


# ──────────────────────────────────────────────────
# AC-2: 진행 중 2번째 recrawl POST → 409
# ──────────────────────────────────────────────────

def test_conflict(app):
    """진행 중 job이 있을 때 두 번째 recrawl POST → 409 (TP-010 §6, AC-2)."""
    app.config["_TIMETABLE_CRAWL_JOB"] = _MockConflictJob()
    client = app.test_client()
    _authed(client)

    resp = client.post(
        "/admin/timetable/recrawl",
        data={"csrf_token": _CSRF, "vacation": "off"},
    )
    assert resp.status_code == 409, f"concurrent recrawl should be 409, got {resp.status_code}"


# ──────────────────────────────────────────────────
# AC-3: 두 Flask app 인스턴스(= 두 워커)가 같은 data_dir 공유 → SSE GET (#6)
# ──────────────────────────────────────────────────

def _make_real_app(tmp_path: Path, data_dir: Path):
    """공유 data_dir를 사용하는 Flask app 인스턴스 생성.

    실제 RecrawlJob(파일 기반)을 사용하도록 _TIMETABLE_CRAWL_JOB은 주입하지 않는다.
    """
    pw_path = tmp_path / "manager_password.txt"
    if not pw_path.exists():
        pw_path.write_text("testpassword")
    config = AppConfig(
        api_key="test-api-key",
        database_url="sqlite:///:memory:",
        session_secret="test-secret",
        manager_password_path=pw_path,
        data_dir=data_dir,
        tz=_KST,
        log_level="DEBUG",
        log_dir=tmp_path / "logs",
    )
    return create_app(config)


def test_cross_worker_sse_via_http(tmp_path):
    """app_a(워커 A)가 시작한 잡을 app_b(워커 B)의 SSE GET으로 읽을 수 있다 (#6).

    독립 출처: #6 spec "새 app 인스턴스(다른 워커)에서 SSE GET 가능".

    검증 방법:
      - 두 Flask app이 같은 data_dir를 공유 (= 두 gunicorn 워커 시뮬레이션)
      - fast_crawl_fn을 직접 주입해 실제 네트워크 없이 진행 이벤트 생성
      - app_a: POST /admin/timetable/recrawl → job_id
      - app_b: GET /admin/timetable/recrawl/<job_id>/stream → SSE 소비
      - 응답에 "event: progress" + "event: done" 포함 확인

    E-13: 기대값 = SSE 응답 본문에 progress·done 이벤트, tautology 없음.
    """
    import threading
    import time
    from bushexa.services.recrawl_job import RecrawlJob

    shared_data = tmp_path / "shared_data"
    shared_data.mkdir()

    # 빠른 crawl_fn — 실제 API 미호출, progress 2건 후 반환
    crawl_done = threading.Event()

    def fast_crawl(*, vacation, on_progress):
        on_progress({"route": "713", "day": 0, "page": 1})
        on_progress({"route": "713", "day": 0, "page": 2})
        crawl_done.set()

    # app_a, app_b: 같은 data_dir를 보는 두 개의 Flask app 인스턴스
    app_a = _make_real_app(tmp_path, shared_data)
    app_b = _make_real_app(tmp_path, shared_data)

    # app_a에는 fast_crawl을 사용하는 RecrawlJob 주입 (실제 네트워크 없이 이벤트 생성)
    real_job_a = RecrawlJob(fast_crawl, data_dir=shared_data)
    app_a.config["_TIMETABLE_CRAWL_JOB"] = real_job_a

    # app_b에는 같은 data_dir를 보는 RecrawlJob 주입 (crawl_fn은 실행되지 않음)
    def _unused_crawl(*, vacation, on_progress):
        pass

    real_job_b = RecrawlJob(_unused_crawl, data_dir=shared_data)
    app_b.config["_TIMETABLE_CRAWL_JOB"] = real_job_b

    client_a = app_a.test_client()
    client_b = app_b.test_client()

    # 인증 주입 (두 클라이언트 각각)
    with client_a.session_transaction() as sess:
        sess["admin_authed"] = True
        sess["csrf_token"] = _CSRF
    with client_b.session_transaction() as sess:
        sess["admin_authed"] = True
        sess["csrf_token"] = _CSRF

    # 워커 A (app_a): POST로 잡 시작 → job_id 취득
    start_resp = client_a.post(
        "/admin/timetable/recrawl",
        data={"csrf_token": _CSRF, "vacation": "off"},
    )
    assert start_resp.status_code == 200, (
        f"app_a recrawl start expected 200, got {start_resp.status_code}"
    )
    job_id = start_resp.get_json()["job_id"]

    # 크롤이 완료될 때까지 최대 5초 대기 (JSONL flush 보장)
    crawl_done.wait(timeout=5.0)
    time.sleep(0.3)  # JSONL flush 여유

    # 워커 B (app_b): GET SSE 스트림 — 다른 앱 인스턴스에서 파일 폴링으로 읽기
    stream_resp = client_b.get(f"/admin/timetable/recrawl/{job_id}/stream")
    assert stream_resp.status_code == 200, (
        f"app_b SSE stream expected 200, got {stream_resp.status_code}"
    )
    assert stream_resp.mimetype == "text/event-stream", (
        f"SSE Content-Type 기대 text/event-stream, got {stream_resp.mimetype}"
    )
    body = stream_resp.get_data(as_text=True)

    # app_b가 app_a의 파일 기반 이벤트를 읽어 SSE로 응답해야 한다 (크로스 워커 핵심 검증)
    assert "event: progress" in body, (
        f"app_b SSE에 progress 이벤트가 없음 (크로스 워커 파일 공유 실패). body={body!r}"
    )
    assert "event: done" in body, (
        f"app_b SSE에 done 이벤트가 없음. body={body!r}"
    )
    assert body.index("event: progress") < body.index("event: done"), (
        "progress가 done보다 먼저 와야 함"
    )
