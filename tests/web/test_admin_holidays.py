"""관리자 공휴일 관리 라우트 테스트.

/admin/holidays GET — 목록 표시
/admin/holidays/add POST — 날짜 추가
/admin/holidays/remove POST — 날짜 제거

네트워크 없음. 파일 조작은 tmp_path 격리.
"""
from __future__ import annotations

import pytest
from zoneinfo import ZoneInfo

from bushexa.config import AppConfig
from bushexa.services.holiday_editor import HolidayEditor, default_holidays_path
from bushexa.web.app import create_app

_KST = ZoneInfo("Asia/Seoul")
_CSRF = "holiday-csrf-token"


@pytest.fixture
def app(tmp_path):
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


def test_holidays_index_requires_login(app):
    """비로그인 → 로그인 페이지 리다이렉트."""
    resp = app.test_client().get("/admin/holidays")
    assert resp.status_code in (302, 401)


def test_holidays_index_returns_200(authed):
    """GET /admin/holidays → 200."""
    client, _ = authed
    resp = client.get("/admin/holidays")
    assert resp.status_code == 200
    assert "공휴일" in resp.data.decode("utf-8")


def test_holidays_add_saves_date(authed):
    """POST /admin/holidays/add → 날짜가 파일에 저장된다."""
    client, app = authed
    resp = client.post("/admin/holidays/add", data={
        "csrf_token": _CSRF,
        "date": "20261001",
    })
    assert resp.status_code in (302, 303)

    config = app.config["BUSHEXA_CONFIG"]
    saved = HolidayEditor(default_holidays_path(config.data_dir)).load()
    assert "20261001" in saved


def test_holidays_add_invalid_date_flashes_error(authed):
    """잘못된 날짜 형식 → flash error, 파일 미변경."""
    client, app = authed
    resp = client.post("/admin/holidays/add", data={
        "csrf_token": _CSRF,
        "date": "not-a-date",
    }, follow_redirects=True)
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    assert "형식" in html or "error" in html or "오류" in html

    config = app.config["BUSHEXA_CONFIG"]
    saved = HolidayEditor(default_holidays_path(config.data_dir)).load()
    assert len(saved) == 0


def test_holidays_remove_deletes_date(authed):
    """POST /admin/holidays/remove → 날짜가 파일에서 제거된다."""
    client, app = authed
    # 먼저 추가
    client.post("/admin/holidays/add", data={"csrf_token": _CSRF, "date": "20261001"})
    # 제거
    resp = client.post("/admin/holidays/remove", data={
        "csrf_token": _CSRF,
        "date": "20261001",
    })
    assert resp.status_code in (302, 303)

    config = app.config["BUSHEXA_CONFIG"]
    saved = HolidayEditor(default_holidays_path(config.data_dir)).load()
    assert "20261001" not in saved


def test_holidays_index_shows_registered_dates(authed):
    """GET /admin/holidays → 등록된 날짜가 HTML에 표시된다."""
    client, app = authed
    client.post("/admin/holidays/add", data={"csrf_token": _CSRF, "date": "20261001"})

    resp = client.get("/admin/holidays")
    html = resp.data.decode("utf-8")
    assert "2026-10-01" in html or "20261001" in html
