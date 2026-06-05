"""W14 테스트: admin govtrack status + SSE (F04, TP-011).

E-13 준수: 기대값은 구현 독립 출처에서 온다.
- test_status_json: W14 AC-1, TP-011 §9 "status JSON에 last_success_at·consecutive_failures 포함".
  GovtrackStatusWriter로 임시 status 파일을 시드하고, JSON 응답에서 두 필드를 직접 검증.
  기대값은 시드 시점에 직접 투입한 CycleStats에서 도출 — 구현 출력 베끼기 아님.
- test_status_sse: W14 AC-2, TP-011 §9 "SSE text/event-stream + 첫 이벤트에 status 데이터".
  첫 청크만 읽고 응답을 닫는다 (무한 루프 방지).
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from bushexa.config import AppConfig
from bushexa.crawler.recorder import CycleStats, RouteStats
from bushexa.services.govtrack_status import GovtrackStatusWriter
from bushexa.web.app import create_app

_KST = ZoneInfo("Asia/Seoul")
_BASE_DT = datetime(2026, 6, 1, 8, 0, 0, tzinfo=_KST)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

def _cycle(started, *, route_inserts, total_errors=0, committed=True) -> CycleStats:
    """알려진 CycleStats 생성 헬퍼 (test_govtrack_status.py와 동일 패턴)."""
    routes = {rid: RouteStats(route_id=rid, inserts=n) for rid, n in route_inserts.items()}
    return CycleStats(
        cycle_started_at=started,
        route_results=routes,
        total_inserts=sum(route_inserts.values()),
        total_errors=total_errors,
        committed=committed,
    )


@pytest.fixture
def status_app(tmp_path):
    """govtrack_status.json을 시드하고 Flask app을 반환한다.

    status 파일 경로: config.data_dir / govtrack_status.json
    (W14 매뉴얼 "status 파일 경로 = Path(config.data_dir)/'govtrack_status.json'")
    """
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    # 알려진 사이클 1회 시드 (성공 사이클 — consecutive_failures=0, last_success_at 설정)
    status_path = data_dir / "govtrack_status.json"
    writer = GovtrackStatusWriter(status_path)
    writer.write(_cycle(_BASE_DT, route_inserts={"195000177": 3, "196000421": 2}))

    config = AppConfig(
        api_key="test-api-key",
        database_url="sqlite:///:memory:",
        session_secret="test-secret",
        manager_password_path=tmp_path / "manager_password.txt",
        data_dir=data_dir,
        tz=_KST,
        log_level="DEBUG",
        log_dir=tmp_path / "logs",
    )
    app = create_app(config)
    return app


@pytest.fixture
def authed_client(status_app):
    """로그인 세션이 주입된 test_client."""
    client = status_app.test_client()
    with client.session_transaction() as sess:
        sess["admin_authed"] = True
        sess["csrf_token"] = "test-csrf-token"
    return client


# ─────────────────────────────────────────────────────────────────────────────
# test_status_json
# ─────────────────────────────────────────────────────────────────────────────

def test_status_json(authed_client):
    """GovtrackStatusWriter가 기록한 사이클을 reader가 읽어 JSON 응답에
    last_success_at·consecutive_failures가 포함되는지 검증한다 (W14 AC-1).

    E-13: 기대값은 시드 시점에 투입한 CycleStats에서 도출.
    - 성공 사이클이므로 consecutive_failures == 0
    - last_success_at == _BASE_DT.isoformat()
    """
    resp = authed_client.get("/admin/govtrack/status")
    assert resp.status_code == 200

    data = json.loads(resp.data)

    # AC-1: 두 필드 존재 여부
    assert "last_success_at" in data
    assert "consecutive_failures" in data

    # 기대값: 시드한 알려진 값 (구현 출력 베끼기 아님)
    assert data["consecutive_failures"] == 0
    assert data["last_success_at"] == _BASE_DT.isoformat()


# ─────────────────────────────────────────────────────────────────────────────
# test_status_sse
# ─────────────────────────────────────────────────────────────────────────────

def test_status_sse(authed_client):
    """SSE 스트림이 text/event-stream Content-Type이고 첫 이벤트에 status 데이터가 있다
    (W14 AC-2, TP-011 AC-2).

    첫 청크만 읽어 무한 루프를 방지하고 응답을 닫는다.
    """
    with authed_client.get("/admin/govtrack/status/stream", buffered=False) as resp:
        assert resp.status_code == 200
        assert "text/event-stream" in resp.content_type

        # 첫 청크를 읽어 status 이벤트 확인
        chunk = next(resp.iter_encoded())
        text = chunk.decode("utf-8")

        assert "event: status" in text
        assert "data:" in text

        # data 부분을 파싱해 status 필드 존재 확인
        for line in text.splitlines():
            if line.startswith("data:"):
                payload = json.loads(line[len("data:"):].strip())
                assert "consecutive_failures" in payload
                assert "last_success_at" in payload
                break
        else:
            pytest.fail("SSE 응답에 data: 라인이 없습니다")
