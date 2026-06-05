"""크롤 설정 페이지 + 로그 소스 선택 테스트.

- /admin/crawl-settings GET/POST
- /admin/logs?src= 소스 선택
"""
from __future__ import annotations

import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from bushexa.config import AppConfig
from bushexa.services.crawl_settings import CrawlSettingsStore, default_crawl_settings_path
from bushexa.web.app import create_app

_KST = ZoneInfo("Asia/Seoul")
_CSRF = "test-csrf-crawl-settings"


# ── 공통 픽스처 ──────────────────────────────────────────────────────────────

@pytest.fixture
def app(tmp_path, monkeypatch):
    """시간표 디렉터리를 tmp에 격리."""
    import json as _json
    tdir = tmp_path / "timetable"
    tdir.mkdir()
    for busno in ["513", "713", "743", "753", "1115"]:
        (tdir / f"{busno}.json").write_text(
            _json.dumps({"0": {"UNIST": ["07:30"]}, "1": {"UNIST": ["09:00"]}, "2": {"UNIST": ["10:00"]}}),
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
    """로그인 세션이 주입된 (client, app) 튜플."""
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["admin_authed"] = True
        sess["csrf_token"] = _CSRF
    return client, app


# ── /admin/crawl-settings ────────────────────────────────────────────────────

class TestCrawlSettingsPage:

    def test_requires_login(self, app):
        """비로그인 GET /admin/crawl-settings → 로그인 리다이렉트."""
        resp = app.test_client().get("/admin/crawl-settings")
        assert resp.status_code == 302
        assert "/admin/login" in resp.headers["Location"]

    def test_get_returns_200(self, authed):
        """로그인 후 GET → 200, 폼 요소 포함."""
        client, _ = authed
        resp = client.get("/admin/crawl-settings")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert "govtrack_poll_seconds" in html
        assert "arrival_poll_seconds" in html

    def test_post_valid_saves_correct_values(self, authed, app):
        """POST 정상값(15/9) → crawl_settings.json에 {"govtrack_poll_seconds": 15.0, "arrival_poll_seconds": 9.0}.

        E-13: 기대값은 입력 15/9에서 직접 도출. 구현과 독립된 출처.
        """
        client, _ = authed
        resp = client.post("/admin/crawl-settings", data={
            "csrf_token": _CSRF,
            "govtrack_poll_seconds": "15",
            "arrival_poll_seconds": "9",
        }, follow_redirects=False)
        # POST 성공 → redirect
        assert resp.status_code in (302, 303)

        config = app.config["BUSHEXA_CONFIG"]
        settings_path = default_crawl_settings_path(config.data_dir)
        saved = json.loads(settings_path.read_text(encoding="utf-8"))
        assert saved == {"govtrack_poll_seconds": 15.0, "arrival_poll_seconds": 9.0}, (
            f"기대 {{'govtrack_poll_seconds': 15.0, 'arrival_poll_seconds': 9.0}}, 실제 {saved}"
        )

    def test_post_out_of_range_shows_error_and_preserves_file(self, authed, app):
        """POST 범위 밖(1초) → error flash, 파일은 이전 상태 유지.

        E-13: 사전 유효 값 15/9를 저장한 후 범위 밖(1)을 POST → 파일은 15/9 유지.
        """
        client, _ = authed
        config = app.config["BUSHEXA_CONFIG"]

        # 사전 조건: 유효 값 저장
        client.post("/admin/crawl-settings", data={
            "csrf_token": _CSRF,
            "govtrack_poll_seconds": "15",
            "arrival_poll_seconds": "9",
        })

        settings_path = default_crawl_settings_path(config.data_dir)
        before = json.loads(settings_path.read_text(encoding="utf-8"))

        # 범위 밖 값 POST
        resp = client.post("/admin/crawl-settings", data={
            "csrf_token": _CSRF,
            "govtrack_poll_seconds": "1",  # MIN_POLL_SECONDS=3 미만 → ValueError
            "arrival_poll_seconds": "9",
        }, follow_redirects=True)

        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        # error 카테고리 flash 또는 "오류" 텍스트가 있어야 함
        assert "오류" in html or "error" in html.lower() or "입력값" in html

        # 파일은 이전 상태 유지
        after = json.loads(settings_path.read_text(encoding="utf-8"))
        assert after == before, f"파일이 변경되면 안 됨: before={before}, after={after}"

    def test_post_empty_values_saves_empty_dict(self, authed, app):
        """POST 빈 값 → {} 저장 (기본값 복귀).

        E-13: 빈 입력 → None → store.save 제외 → 빈 dict 기록.
        """
        client, _ = authed
        config = app.config["BUSHEXA_CONFIG"]

        # 먼저 값 저장
        client.post("/admin/crawl-settings", data={
            "csrf_token": _CSRF,
            "govtrack_poll_seconds": "15",
            "arrival_poll_seconds": "9",
        })

        # 빈 값으로 POST
        resp = client.post("/admin/crawl-settings", data={
            "csrf_token": _CSRF,
            "govtrack_poll_seconds": "",
            "arrival_poll_seconds": "",
        }, follow_redirects=False)
        assert resp.status_code in (302, 303)

        settings_path = default_crawl_settings_path(config.data_dir)
        saved = json.loads(settings_path.read_text(encoding="utf-8"))
        assert saved == {}, f"빈 입력 → {{}} 기대, 실제: {saved}"


# ── /admin/logs?src= 소스 선택 ──────────────────────────────────────────────

class TestLogsSourceSelection:

    def test_src_crawl_uses_crawl_log(self, authed, app):
        """GET /admin/logs?src=crawl → 크롤 로그 파일의 내용이 표시되고 웹 로그 내용은 없어야 함.

        E-13: bushexa-crawl.log에만 고유 sentinel을 쓰고, bushexa.log에는 다른 sentinel을 쓴다.
        응답에 crawl sentinel이 있고 web sentinel이 없으면 올바른 파일을 읽은 것.
        LOG_SOURCES["crawl"] == "bushexa-crawl.log" — 계약 파일에서 직접 확인.
        """
        client, _ = authed
        config = app.config["BUSHEXA_CONFIG"]
        log_dir = Path(config.log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)

        crawl_sentinel = "CRAWL_UNIQUE_SENTINEL_XJ7K"
        web_sentinel = "WEB_UNIQUE_SENTINEL_TQ3M"

        (log_dir / "bushexa-crawl.log").write_text(
            f"2026-06-05T10:00:00+09:00 [bushexa.crawler] INFO: {crawl_sentinel}\n",
            encoding="utf-8",
        )
        (log_dir / "bushexa.log").write_text(
            f"2026-06-05T10:00:00+09:00 [bushexa.web] INFO: {web_sentinel}\n",
            encoding="utf-8",
        )

        resp = client.get("/admin/logs?src=crawl")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert crawl_sentinel in html, (
            f"?src=crawl 요청에 크롤 로그 sentinel({crawl_sentinel!r})이 없음 — "
            "잘못된 파일을 읽고 있을 가능성"
        )
        assert web_sentinel not in html, (
            f"?src=crawl 요청에 웹 로그 sentinel({web_sentinel!r})이 있음 — "
            "웹 로그 파일을 잘못 읽고 있음"
        )

    def test_src_invalid_falls_back_to_web(self, authed, app):
        """?src=../etc 같은 화이트리스트 외 값 → "web" 폴백(bushexa.log 내용 표시).

        E-13: bushexa.log에 고유 sentinel을 쓰고, bushexa-crawl.log에는 다른 sentinel.
        폴백 시 web sentinel이 있고 crawl sentinel이 없어야 함. 전체 경로(log_dir 포함)
        에서 bushexa.log가 보여야 함(드롭다운 label과 구분).
        S3 path traversal 차단 유지.
        """
        client, _ = authed
        config = app.config["BUSHEXA_CONFIG"]
        log_dir = Path(config.log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)

        web_sentinel = "WEB_FALLBACK_SENTINEL_PL9N"
        crawl_sentinel = "CRAWL_SENTINEL_FOR_FALLBACK_QM2X"

        (log_dir / "bushexa.log").write_text(
            f"2026-06-05T10:00:00+09:00 [bushexa.web] INFO: {web_sentinel}\n",
            encoding="utf-8",
        )
        (log_dir / "bushexa-crawl.log").write_text(
            f"2026-06-05T10:00:00+09:00 [bushexa.crawler] INFO: {crawl_sentinel}\n",
            encoding="utf-8",
        )

        resp = client.get("/admin/logs?src=../etc")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")

        # 폴백 → bushexa.log 내용이 표시되어야 함
        assert web_sentinel in html, (
            f"폴백 시 웹 로그 sentinel({web_sentinel!r})이 없음"
        )
        # 크롤 로그 내용은 없어야 함 (다른 파일)
        assert crawl_sentinel not in html, (
            f"폴백 시 크롤 로그 sentinel({crawl_sentinel!r})이 있음 — 폴백 미동작"
        )
        # 렌더된 파일 경로(log_meta)에 log_dir 기준 전체 경로 포함 (traversal 차단 확인)
        assert "../etc" not in html
        assert str(log_dir / "bushexa.log") in html, (
            "폴백 시 log_file_path에 bushexa.log 전체 경로가 없음"
        )

    def test_src_level_lines_preserved_on_src_change(self, authed, app):
        """?src=crawl&level=ERROR&lines=50 → 해당 옵션이 selected 상태로 렌더된다.

        E-13: 한 폼에서 모두 관리하므로 submit 시 전달된 값이 그대로 selected 상태여야 함.
        드롭다운 label에 항상 "ERROR"·"50"이 있으므로, selected 속성 또는 value="50"으로 검증.
        """
        client, _ = authed
        config = app.config["BUSHEXA_CONFIG"]
        log_dir = Path(config.log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)

        resp = client.get("/admin/logs?src=crawl&level=ERROR&lines=50")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")

        # src=crawl → crawl 옵션이 selected 상태
        assert 'value="crawl"' in html and "selected" in html, (
            "src=crawl 요청 시 crawl 옵션에 selected가 없음"
        )
        # level=ERROR → ERROR 옵션 selected (template: value="ERROR" {% if ... %}selected{% endif %})
        assert 'value="ERROR"' in html, "level ERROR 옵션이 없음"
        # lines=50 → input value가 50
        assert 'value="50"' in html, "lines 50이 input value에 없음"
