"""Feature 1/2/6 테스트.

Feature 1: /admin/special/preview — 그날 미리보기 (특별편/공휴일/요일 라벨)
Feature 2: /admin/holidays/sync + /admin/holidays/sync/confirm — 공휴일 API 일괄 동기화
Feature 6: /admin/login 공개 관리자 네비 미노출 확인

모두 네트워크 없음. HolidayClient는 app.config['_HOLIDAY_CLIENT']로 주입.
파일 조작은 tmp_path·BUSHEXA_TIMETABLE_DIR override로 격리.
"""
from __future__ import annotations

import datetime
import json
from pathlib import Path
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest

from bushexa.config import AppConfig
from bushexa.services.holiday_editor import HolidayEditor, default_holidays_path
from bushexa.services.special_timetable import SpecialTimetableService, default_special_path
from bushexa.web.app import create_app

_KST = ZoneInfo("Asia/Seoul")
_CSRF = "test-csrf-token-new"

# ── 공통 픽스처 ──────────────────────────────────────────────────────────────

@pytest.fixture
def app(tmp_path, monkeypatch):
    """시간표 디렉터리를 tmp에 격리하고, 알려진 노선 JSON 시드."""
    tdir = tmp_path / "timetable"
    tdir.mkdir()
    for busno in ["513", "713", "743", "753", "1115"]:
        (tdir / f"{busno}.json").write_text(
            json.dumps({
                "0": {"UNIST": ["07:30", "08:00"]},
                "1": {"UNIST": ["09:00"]},
                "2": {"UNIST": ["10:00"]},
            }, indent=2),
            encoding="utf-8",
        )
    monkeypatch.setenv("BUSHEXA_TIMETABLE_DIR", str(tdir))

    config = AppConfig(
        api_key="k",
        database_url="sqlite:///:memory:",
        session_secret="s",
        manager_password_path=tmp_path / "pw.txt",
        data_dir=tmp_path / "data",
        tz=_KST,
        log_level="INFO",
        log_dir=tmp_path / "logs",
    )
    flask_app = create_app(config)
    return flask_app


@pytest.fixture
def authed(app):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["admin_authed"] = True
        sess["csrf_token"] = _CSRF
    return client, app


def _inject_mock_holiday_client(app, dates_by_month: dict[tuple[int, int], list[datetime.date]]):
    """app.config['_HOLIDAY_CLIENT']에 mock을 주입해 네트워크를 차단한다."""
    mock_client = MagicMock()

    def _fake_fetch(year, month):
        return dates_by_month.get((year, month), [])

    mock_client.fetch.side_effect = _fake_fetch
    app.config["_HOLIDAY_CLIENT"] = mock_client
    return mock_client


# ── Feature 1: /admin/special/preview ────────────────────────────────────────

class TestSpecialPreview:

    def test_preview_requires_login(self, app):
        """비로그인 → 302 로그인 페이지."""
        resp = app.test_client().get("/admin/special/preview")
        assert resp.status_code in (302, 401)

    def test_preview_default_date_returns_200(self, authed, app):
        """GET /admin/special/preview (날짜 미지정) → 200."""
        # 공휴일 API mock (빈 응답)
        _inject_mock_holiday_client(app, {})
        client, _ = authed
        resp = client.get("/admin/special/preview")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert "미리보기" in html

    def test_preview_weekday_label(self, authed, app, tmp_path):
        """평일에는 '평일' 라벨이 표시된다."""
        _inject_mock_holiday_client(app, {})
        client, _ = authed
        # 2026-06-01 = 월요일 (평일)
        resp = client.get("/admin/special/preview?date=20260601")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert "평일" in html

    def test_preview_holiday_label(self, authed, app, tmp_path):
        """공휴일 날짜는 '공휴일' 라벨이 표시된다."""
        # 20260101을 공휴일로 등록
        config = app.config["BUSHEXA_CONFIG"]
        editor = HolidayEditor(default_holidays_path(config.data_dir))
        editor.add("20260101")

        _inject_mock_holiday_client(app, {})
        client, _ = authed
        resp = client.get("/admin/special/preview?date=20260101")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert "공휴일" in html

    def test_preview_special_edition_label(self, authed, app, tmp_path, monkeypatch):
        """특별편이 배정된 날짜는 '특별편' 라벨과 에디션 ID가 표시된다."""
        config = app.config["BUSHEXA_CONFIG"]
        import os
        tdir_str = os.environ.get("BUSHEXA_TIMETABLE_DIR", "data/timetable")
        tdir = Path(tdir_str)

        # 에디션 디렉터리 생성 + 시간표 파일 생성
        ed_dir = tdir / "special" / "exam-test"
        ed_dir.mkdir(parents=True)
        for busno in ["513", "713", "743", "753", "1115"]:
            (ed_dir / f"{busno}.json").write_text(
                json.dumps({"0": {"UNIST": ["06:00", "06:30"]}}),
                encoding="utf-8",
            )

        # 날짜 배정
        svc = SpecialTimetableService(
            map_path=default_special_path(config.data_dir),
            timetable_dir=tdir,
        )
        svc.assign("20260610", "exam-test")

        _inject_mock_holiday_client(app, {})
        client, _ = authed
        resp = client.get("/admin/special/preview?date=20260610")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert "특별편" in html
        assert "exam-test" in html

    def test_preview_shows_times_for_weekday(self, authed, app):
        """평일 날짜 → 평일 시간표(07:30, 08:00)가 표시된다."""
        _inject_mock_holiday_client(app, {})
        client, _ = authed
        # 2026-06-01 = 월요일 평일
        resp = client.get("/admin/special/preview?date=20260601")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert "07:30" in html or "08:00" in html


# ── Feature 2: /admin/holidays/sync ──────────────────────────────────────────

class TestHolidaysSync:

    def test_sync_requires_login(self, app):
        """비로그인 → 302."""
        resp = app.test_client().post("/admin/holidays/sync", data={"year": "2026", "csrf_token": _CSRF})
        assert resp.status_code in (302, 400, 401)

    def test_sync_fetch_shows_preview(self, authed, app):
        """fetch 단계: 유효 API mock → 미리보기 페이지 200 반환."""
        _inject_mock_holiday_client(app, {
            (2026, 1): [datetime.date(2026, 1, 1), datetime.date(2026, 1, 27)],
            (2026, 3): [datetime.date(2026, 3, 1)],
        })
        client, _ = authed
        resp = client.post("/admin/holidays/sync", data={
            "csrf_token": _CSRF,
            "year": "2026",
        })
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert "동기화" in html or "미리보기" in html
        assert "20260101" in html or "2026-01-01" in html

    def test_sync_merges_into_store(self, authed, app):
        """confirm 단계: new_dates가 HolidayEditor에 저장된다."""
        client, _ = authed
        resp = client.post("/admin/holidays/sync/confirm", data={
            "csrf_token": _CSRF,
            "year": "2026",
            "new_dates": "20260101 20260301",
        })
        assert resp.status_code in (302, 303)

        config = app.config["BUSHEXA_CONFIG"]
        saved = HolidayEditor(default_holidays_path(config.data_dir)).load()
        assert "20260101" in saved
        assert "20260301" in saved

    def test_sync_no_duplicates(self, authed, app):
        """이미 등록된 날짜는 중복 추가되지 않는다."""
        config = app.config["BUSHEXA_CONFIG"]
        # 미리 등록
        HolidayEditor(default_holidays_path(config.data_dir)).add("20260101")

        _inject_mock_holiday_client(app, {
            (2026, 1): [datetime.date(2026, 1, 1)],  # 이미 등록됨
        })
        client, _ = authed

        # fetch 단계: 중복 분류 확인
        resp = client.post("/admin/holidays/sync", data={
            "csrf_token": _CSRF,
            "year": "2026",
        })
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        # new_dates가 비어야 함
        assert "새로 추가될 날짜가 없습니다" in html or "0건" in html or (
            "2026-01-01" not in html.split("새로 추가될")[1] if "새로 추가될" in html else True
        )

        # confirm 후에도 한 번만 있어야 함
        client.post("/admin/holidays/sync/confirm", data={
            "csrf_token": _CSRF,
            "year": "2026",
            "new_dates": "",  # 새 날짜 없음
        })
        saved = HolidayEditor(default_holidays_path(config.data_dir)).load()
        # 20260101이 정확히 1개여야 함 (set이므로 중복 불가)
        count = sum(1 for d in saved if d == "20260101")
        assert count == 1

    def test_sync_api_failure_shows_error_no_write(self, authed, app):
        """API 호출에서 예외 발생 → 오류 메시지, 파일 미변경."""
        mock_client = MagicMock()
        mock_client.fetch.side_effect = ConnectionError("API 연결 오류")
        app.config["_HOLIDAY_CLIENT"] = mock_client

        config = app.config["BUSHEXA_CONFIG"]
        client, _ = authed

        resp = client.post("/admin/holidays/sync", data={
            "csrf_token": _CSRF,
            "year": "2026",
        }, follow_redirects=True)
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert "오류" in html or "실패" in html or "error" in html.lower()

        # 파일 미변경
        saved = HolidayEditor(default_holidays_path(config.data_dir)).load()
        assert len(saved) == 0

    def test_sync_invalid_year_shows_error(self, authed, app):
        """유효하지 않은 연도 → 오류 flash, 파일 미변경."""
        client, _ = authed
        resp = client.post("/admin/holidays/sync", data={
            "csrf_token": _CSRF,
            "year": "not-a-year",
        }, follow_redirects=True)
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert "오류" in html or "유효" in html or "error" in html.lower()


# ── Feature 6: login 페이지 네비 확인 ────────────────────────────────────────

class TestLoginPageNav:

    def test_login_page_has_no_admin_nav(self, app):
        """GET /admin/login → 관리자 네비(대시보드, 공휴일 등) 링크가 없다."""
        client = app.test_client()
        resp = client.get("/admin/login")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        # 관리자 전용 nav 링크가 없어야 함
        assert "/admin/holidays" not in html
        assert "/admin/timetable" not in html
        assert "/admin/special" not in html

    def test_login_page_shows_form(self, app):
        """GET /admin/login → 비밀번호 입력 폼이 있다 (로그인 or 초기 설정 모드)."""
        client = app.test_client()
        resp = client.get("/admin/login")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert 'type="password"' in html
        # 로그인 또는 초기 설정 중 하나가 표시된다
        assert "로그인" in html or "초기 설정" in html

    def test_login_page_no_logout_btn(self, app):
        """GET /admin/login → 로그아웃 버튼이 없다."""
        client = app.test_client()
        resp = client.get("/admin/login")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert "/admin/logout" not in html

    def test_login_post_still_works(self, app, tmp_path):
        """로그인 POST 흐름이 여전히 동작한다 (기존 테스트 회귀 방지)."""
        pw_path = app.config["BUSHEXA_CONFIG"].manager_password_path
        pw_path.parent.mkdir(parents=True, exist_ok=True)
        pw_path.write_text("testpassword99")

        client = app.test_client()
        with client.session_transaction() as sess:
            sess["csrf_token"] = _CSRF

        resp = client.post("/admin/login", data={
            "password": "testpassword99",
            "csrf_token": _CSRF,
        })
        assert resp.status_code in (200, 302)
