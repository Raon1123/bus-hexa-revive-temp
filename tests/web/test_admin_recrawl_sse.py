"""W13b 테스트: admin recrawl SSE (F04, TP-010).

E-13 준수: 기대값은 구현 독립 출처에서 온다.
- test_stream: TP-010 §2/§6 "progress 이벤트 ≥1회 후 done으로 스트림 종료".
- test_conflict: TP-010 §6 "진행 중 2번째 POST → 409 Conflict".

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
