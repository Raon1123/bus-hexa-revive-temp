"""Feature 3/4/5 관리자 웹 라우트 테스트.

Feature 3: /admin/backup (export/import)
Feature 4: /admin/worker-status (govtrack + arrival 상태 대시보드, stale 탐지)
Feature 5: /admin/audit (감사 로그 뷰 + 뮤테이션 훅)
"""
from __future__ import annotations

import base64
import io
import json
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from bushexa.config import AppConfig
from bushexa.crawler.recorder import CycleStats, RouteStats
from bushexa.services.arrival_status import ArrivalStatusWriter
from bushexa.services.audit_log import AuditLog, default_audit_path
from bushexa.services.backup import _MANIFEST
from bushexa.services.govtrack_status import GovtrackStatusWriter
from bushexa.web.app import create_app

_KST = ZoneInfo("Asia/Seoul")
_CSRF = "test-csrf-f3f4f5"
_BASE = datetime(2026, 6, 1, 8, 0, 0, tzinfo=_KST)
_OLD = datetime(2020, 1, 1, 0, 0, 0, tzinfo=_KST)   # stale용 — 아주 오래된 시각


# ── 공통 픽스처 ──────────────────────────────────────────────────────────────

@pytest.fixture
def app(tmp_path, monkeypatch):
    """기본 앱 픽스처 (timetable dir 격리)."""
    tdir = tmp_path / "timetable"
    tdir.mkdir()
    monkeypatch.setenv("BUSHEXA_TIMETABLE_DIR", str(tdir))

    data_dir = tmp_path / "data"
    data_dir.mkdir()

    config = AppConfig(
        api_key="test-key",
        database_url="sqlite:///:memory:",
        session_secret="test-secret",
        manager_password_path=tmp_path / "pw.txt",
        data_dir=data_dir,
        tz=_KST,
        log_level="DEBUG",
        log_dir=tmp_path / "logs",
    )
    return create_app(config)


@pytest.fixture
def authed_client(app):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["admin_authed"] = True
        sess["csrf_token"] = _CSRF
    return client, app


def _seed_govtrack(data_dir: Path, started=_BASE, *, fail: bool = False) -> None:
    path = data_dir / "govtrack_status.json"
    routes = {"195000177": RouteStats(route_id="195000177", inserts=0 if fail else 2)}
    cyc = CycleStats(
        cycle_started_at=started,
        route_results=routes,
        total_inserts=0 if fail else 2,
        total_errors=10 if fail else 0,
        committed=not fail,
    )
    GovtrackStatusWriter(path).write(cyc)


def _seed_arrival(data_dir: Path, started=_BASE, *, partial: bool = False) -> None:
    path = data_dir / "arrival_status.json"
    ArrivalStatusWriter(path).write(
        cycle_started_at=started,
        stops_ok=10 if partial else 17,
        stops_total=17,
        last_error_msg="timeout" if partial else None,
    )


# ── Feature 4: 워커 상태 대시보드 ────────────────────────────────────────────

class TestWorkerStatus:

    def test_requires_login(self, app):
        resp = app.test_client().get("/admin/worker-status")
        assert resp.status_code in (302, 401)

    def test_page_renders_without_data(self, authed_client):
        client, _ = authed_client
        resp = client.get("/admin/worker-status")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert "워커 상태" in html
        # 데이터 없음 안내
        assert "데이터 없음" in html

    def test_shows_govtrack_data(self, authed_client):
        client, app = authed_client
        config = app.config["BUSHEXA_CONFIG"]
        _seed_govtrack(Path(config.data_dir))

        resp = client.get("/admin/worker-status")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert "Govtrack" in html
        assert str(_BASE.isoformat()) in html or "2026" in html

    def test_shows_arrival_data(self, authed_client):
        client, app = authed_client
        config = app.config["BUSHEXA_CONFIG"]
        _seed_arrival(Path(config.data_dir))

        resp = client.get("/admin/worker-status")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert "Arrival" in html or "도착" in html

    def test_stale_warning_shown_for_old_cycle(self, authed_client):
        """아주 오래된 타임스탬프 → stale 경고가 표시된다."""
        client, app = authed_client
        config = app.config["BUSHEXA_CONFIG"]
        _seed_govtrack(Path(config.data_dir), started=_OLD)

        resp = client.get("/admin/worker-status")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert "경고" in html or "stale" in html.lower() or "오래" in html

    def test_no_stale_warning_for_recent_cycle(self, authed_client):
        """직전 사이클이 최근(60초 이내)이면 stale 경고가 표시되지 않는다."""
        client, app = authed_client
        config = app.config["BUSHEXA_CONFIG"]

        # 현재 wall-clock 기반으로 아주 최근 타임스탬프를 시드 (route는 KSTClock().now() 사용)
        from datetime import datetime as _dt
        recent = _dt.now(_KST)
        _seed_govtrack(Path(config.data_dir), started=recent)
        _seed_arrival(Path(config.data_dir), started=recent)

        resp = client.get("/admin/worker-status")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        # stale 경고가 없어야 한다
        assert "경고: 마지막 사이클이" not in html

    def test_both_workers_rendered(self, authed_client):
        """govtrack + arrival 둘 다 시드되면 양쪽 카드가 보인다."""
        client, app = authed_client
        config = app.config["BUSHEXA_CONFIG"]
        _seed_govtrack(Path(config.data_dir))
        _seed_arrival(Path(config.data_dir))

        resp = client.get("/admin/worker-status")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert "Govtrack" in html
        assert "Arrival" in html or "도착" in html


# ── Feature 3: 백업 내보내기/가져오기 ────────────────────────────────────────

class TestBackup:

    def test_backup_page_requires_login(self, app):
        resp = app.test_client().get("/admin/backup")
        assert resp.status_code in (302, 401)

    def test_backup_page_renders(self, authed_client):
        client, _ = authed_client
        resp = client.get("/admin/backup")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert "백업" in html or "export" in html.lower()

    def test_export_returns_zip(self, authed_client):
        """GET /admin/backup/export → application/zip 파일."""
        client, app = authed_client
        config = app.config["BUSHEXA_CONFIG"]
        # 파일 시드
        (Path(config.data_dir) / "holidays.json").write_text('["20260101"]', encoding="utf-8")

        resp = client.get("/admin/backup/export")
        assert resp.status_code == 200
        assert resp.content_type == "application/zip"
        assert "attachment" in resp.headers.get("Content-Disposition", "")

        # ZIP 파싱 가능 확인
        zb = resp.data
        with zipfile.ZipFile(io.BytesIO(zb)) as zf:
            names = zf.namelist()
        assert _MANIFEST in names
        assert "holidays.json" in names

    def test_import_preview_valid_zip(self, authed_client):
        """POST /admin/backup/import/preview → 미리보기 페이지 200."""
        client, _ = authed_client

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr(_MANIFEST, json.dumps({"version": 1, "exported_at": "x"}))
            zf.writestr("holidays.json", '["20260601"]')
        zb = buf.getvalue()

        resp = client.post(
            "/admin/backup/import/preview",
            data={"csrf_token": _CSRF, "bundle": (io.BytesIO(zb), "backup.zip")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert "holidays.json" in html

    def test_import_confirm_restores_files(self, authed_client):
        """POST /admin/backup/import/confirm → 파일이 복구된다."""
        client, app = authed_client
        config = app.config["BUSHEXA_CONFIG"]

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr(_MANIFEST, json.dumps({"version": 1, "exported_at": "x"}))
            zf.writestr("holidays.json", '["20261225"]')
        zb = buf.getvalue()
        encoded = base64.b64encode(zb).decode("ascii")

        resp = client.post("/admin/backup/import/confirm", data={
            "csrf_token": _CSRF,
            "encoded_bundle": encoded,
        })
        assert resp.status_code in (302, 303)

        dest = Path(config.data_dir) / "holidays.json"
        assert dest.exists()
        assert json.loads(dest.read_text()) == ["20261225"]

    def test_import_path_traversal_rejected(self, authed_client):
        """경로 탐색이 포함된 ZIP → 오류 flash, 파일 미생성."""
        client, app = authed_client
        config = app.config["BUSHEXA_CONFIG"]

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("../evil.json", '{}')
        zb = buf.getvalue()

        resp = client.post(
            "/admin/backup/import/preview",
            data={"csrf_token": _CSRF, "bundle": (io.BytesIO(zb), "evil.zip")},
            content_type="multipart/form-data",
        )
        # 에러 flash 후 redirect
        assert resp.status_code in (302, 303)
        # 파일이 생성되지 않아야 함
        assert not (Path(config.data_dir).parent / "evil.json").exists()

    def test_import_invalid_json_rejected(self, authed_client):
        """유효하지 않은 JSON → 오류 flash."""
        client, app = authed_client
        config = app.config["BUSHEXA_CONFIG"]

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr(_MANIFEST, json.dumps({"version": 1, "exported_at": "x"}))
            zf.writestr("holidays.json", "NOT VALID JSON {{{{")
        zb = buf.getvalue()
        encoded = base64.b64encode(zb).decode("ascii")

        resp = client.post("/admin/backup/import/confirm", data={
            "csrf_token": _CSRF,
            "encoded_bundle": encoded,
        }, follow_redirects=True)
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert "실패" in html or "오류" in html or "error" in html.lower()

    def test_import_not_a_zip(self, authed_client):
        """ZIP이 아닌 파일 업로드 → 오류 flash."""
        client, _ = authed_client
        resp = client.post(
            "/admin/backup/import/preview",
            data={"csrf_token": _CSRF, "bundle": (io.BytesIO(b"not a zip"), "bad.zip")},
            content_type="multipart/form-data",
        )
        assert resp.status_code in (302, 303)


# ── Feature 5: 감사 로그 ──────────────────────────────────────────────────────

class TestAuditLog:

    def test_audit_page_requires_login(self, app):
        resp = app.test_client().get("/admin/audit")
        assert resp.status_code in (302, 401)

    def test_audit_page_renders_empty(self, authed_client):
        """감사 로그가 없어도 200 반환."""
        client, _ = authed_client
        resp = client.get("/admin/audit")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert "감사" in html or "audit" in html.lower()

    def test_audit_page_shows_entries_newest_first(self, authed_client):
        """시드된 감사 항목이 최신순으로 표시된다."""
        client, app = authed_client
        config = app.config["BUSHEXA_CONFIG"]

        # 감사 항목 직접 시드
        audit = AuditLog(default_audit_path(config.data_dir))
        audit.record("holiday.add", actor_ip="1.2.3.4", date="20260101")
        audit.record("via.save", actor_ip="1.2.3.4", override_count=2)

        resp = client.get("/admin/audit")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert "holiday.add" in html
        assert "via.save" in html

        # via.save가 나중에 추가됐으므로 html에서 먼저(위에) 나와야 함
        pos_via = html.find("via.save")
        pos_holiday = html.find("holiday.add")
        assert pos_via < pos_holiday, "최신순 정렬: via.save가 holiday.add 앞에 있어야 함"

    def test_mutation_writes_audit_entry(self, authed_client):
        """공휴일 추가 뮤테이션 → 감사 로그에 holiday.add 항목이 기록된다."""
        client, app = authed_client
        config = app.config["BUSHEXA_CONFIG"]

        resp = client.post("/admin/holidays/add", data={
            "csrf_token": _CSRF,
            "date": "20261225",
        })
        assert resp.status_code in (302, 303)

        audit = AuditLog(default_audit_path(config.data_dir))
        entries = audit.load()
        actions = [e["action"] for e in entries]
        assert "holidays.add" in actions

    def test_mutation_includes_actor_ip(self, authed_client):
        """감사 항목에 actor_ip가 포함된다 (None 또는 실제 IP)."""
        client, app = authed_client
        config = app.config["BUSHEXA_CONFIG"]

        client.post("/admin/holidays/add", data={
            "csrf_token": _CSRF,
            "date": "20261231",
        })

        audit = AuditLog(default_audit_path(config.data_dir))
        entries = audit.load()
        holiday_entries = [e for e in entries if e["action"] == "holidays.add"]
        assert len(holiday_entries) >= 1
        # actor_ip 필드가 존재해야 한다
        assert "actor_ip" in holiday_entries[0]

    def test_audit_size_cap(self, authed_client):
        """max_entries가 적용된다."""
        client, app = authed_client
        config = app.config["BUSHEXA_CONFIG"]

        # max_entries=5 인 AuditLog로 10건 기록
        audit = AuditLog(default_audit_path(config.data_dir), max_entries=5)
        for i in range(10):
            audit.record(f"test.action.{i}", actor_ip=None)

        entries = audit.load(limit=100)
        assert len(entries) == 5
