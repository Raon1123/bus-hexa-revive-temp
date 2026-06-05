"""관리자 특별 시간표 라우트 테스트.

/admin/special GET — 에디션 목록
/admin/special/create POST — 에디션 생성
/admin/special/<edition_id> GET — 편집 화면
/admin/special/<edition_id>/assign POST — 날짜 배정
/admin/special/<edition_id>/unassign POST — 날짜 배정 해제

네트워크 없음. 파일 조작은 tmp_path 격리.
"""
from __future__ import annotations

import json

import pytest
from zoneinfo import ZoneInfo

from bushexa.config import AppConfig
from bushexa.data.timetable import timetable_dir
from bushexa.services.special_timetable import SpecialTimetableService, default_special_path
from bushexa.web.app import create_app

_KST = ZoneInfo("Asia/Seoul")
_CSRF = "special-csrf-token"


@pytest.fixture
def app(tmp_path, monkeypatch):
    """시간표 dir을 tmp에 격리한 Flask app."""
    tdir = tmp_path / "timetable"
    tdir.mkdir()
    # 알려진 노선 JSON 시드 (BUSHEXA_TIMETABLE_DIR override)
    import json as _json
    for busno in ["513", "713", "743", "753", "1115"]:
        (tdir / f"{busno}.json").write_text(
            _json.dumps({"0": {}, "1": {}, "2": {}}, indent=2),
            encoding="utf-8",
        )
    monkeypatch.setenv("BUSHEXA_TIMETABLE_DIR", str(tdir))

    config = AppConfig(
        api_key="k", database_url="sqlite:///:memory:", session_secret="s",
        manager_password_path=tmp_path / "pw.txt", data_dir=tmp_path / "data",
        tz=_KST, log_level="INFO", log_dir=tmp_path / "logs",
    )
    return create_app(config)


@pytest.fixture
def authed(app):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["admin_authed"] = True
        sess["csrf_token"] = _CSRF
    return client, app


def test_special_index_requires_login(app):
    resp = app.test_client().get("/admin/special")
    assert resp.status_code in (302, 401)


def test_special_index_returns_200(authed):
    client, _ = authed
    resp = client.get("/admin/special")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    assert "에디션" in html or "special" in html.lower()


def test_special_create_and_edit_access(authed):
    """에디션 생성 후 편집 화면에 접근할 수 있다."""
    client, _ = authed
    resp = client.post("/admin/special/create", data={
        "csrf_token": _CSRF,
        "edition_id": "exam-2026",
    })
    assert resp.status_code in (302, 303)

    # 편집 화면
    resp2 = client.get("/admin/special/exam-2026")
    assert resp2.status_code == 200
    assert "exam-2026" in resp2.data.decode("utf-8")


def test_special_create_invalid_id_returns_404(authed):
    """잘못된 에디션 ID(경로 구분자 포함) → 404."""
    client, _ = authed
    resp = client.post("/admin/special/create", data={
        "csrf_token": _CSRF,
        "edition_id": "../malicious",
    })
    assert resp.status_code == 404


def test_special_assign_and_list(authed, tmp_path, monkeypatch):
    """날짜 배정 후 편집 화면에 배정일이 표시된다."""
    client, app = authed
    # 에디션 생성
    client.post("/admin/special/create", data={"csrf_token": _CSRF, "edition_id": "exam"})

    # 날짜 배정
    resp = client.post("/admin/special/exam/assign", data={
        "csrf_token": _CSRF,
        "date": "20260610",
    })
    assert resp.status_code in (302, 303)

    # 배정 확인: 서비스 직접 조회
    config = app.config["BUSHEXA_CONFIG"]
    svc = SpecialTimetableService(
        map_path=default_special_path(config.data_dir),
        timetable_dir=timetable_dir(),
    )
    assert svc.get_edition_for_date("20260610") == "exam"

    # 편집 화면에 날짜 표시
    resp2 = client.get("/admin/special/exam")
    html = resp2.data.decode("utf-8")
    assert "2026-06-10" in html or "20260610" in html


def test_special_unassign(authed, app):
    """날짜 배정 해제 후 매핑에서 사라진다."""
    client, app = authed
    client.post("/admin/special/create", data={"csrf_token": _CSRF, "edition_id": "exam"})
    client.post("/admin/special/exam/assign", data={"csrf_token": _CSRF, "date": "20260610"})

    resp = client.post("/admin/special/exam/unassign", data={
        "csrf_token": _CSRF,
        "date": "20260610",
    })
    assert resp.status_code in (302, 303)

    config = app.config["BUSHEXA_CONFIG"]
    svc = SpecialTimetableService(
        map_path=default_special_path(config.data_dir),
        timetable_dir=timetable_dir(),
    )
    assert svc.get_edition_for_date("20260610") is None


def test_special_assign_invalid_date_flashes_error(authed):
    """잘못된 날짜 배정 → flash error."""
    client, _ = authed
    client.post("/admin/special/create", data={"csrf_token": _CSRF, "edition_id": "exam"})

    resp = client.post("/admin/special/exam/assign", data={
        "csrf_token": _CSRF,
        "date": "not-a-date",
    }, follow_redirects=True)
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    assert "형식" in html or "error" in html or "오류" in html
