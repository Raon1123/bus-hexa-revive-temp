"""기한형 공지 — 공개 화면 렌더링과 /admin/notices 관리 라우트 테스트.

공개 화면은 _base.html 이 endpoint→surface 매핑으로 공지를 그린다.
data_dir 에 notices.json 이 없거나 깨지면 이미지 seed(bushexa/data/notices.seed.json, 743 공지)를 쓴다.
네트워크 없음(실시간 화면은 DB 캐시가 비어도 200 을 반환한다).
"""
from __future__ import annotations

import json
import pytest
from freezegun import freeze_time
from zoneinfo import ZoneInfo

from bushexa.config import AppConfig
from bushexa.services import notices as N
from bushexa.web.app import create_app

_KST = ZoneInfo("Asia/Seoul")
_CSRF = "notice-csrf-token"


@pytest.fixture(autouse=True)
def _fresh_cache():
    N._clear_cache()
    yield
    N._clear_cache()


@pytest.fixture
def app(tmp_path):
    config = AppConfig(
        api_key="k", database_url="sqlite:///:memory:", session_secret="s",
        manager_password_path=tmp_path / "pw.txt", data_dir=tmp_path / "data",
        tz=_KST, log_level="INFO", log_dir=tmp_path / "logs",
    )
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    return create_app(config)


@pytest.fixture
def authed(app):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["admin_authed"] = True
        sess["csrf_token"] = _CSRF
    return client


def _live_path(app):
    return N.default_notices_path(app.config["BUSHEXA_CONFIG"].data_dir)


def _write_live(app, entries):
    _live_path(app).write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")


def _html(client, url):
    resp = client.get(url)
    assert resp.status_code == 200
    return resp.data.decode("utf-8")


# ── seed(743) 공지: 시행 전·후·만료 ────────────────────────────────────────

@freeze_time("2026-10-02T12:00:00+09:00")
def test_seed_743_notice_before_effective_on_timetable(app):
    html = _html(app.test_client(), "/timetable?day=0")
    assert 'class="notice notice-route_change"' in html
    assert "10월 3일부터 743번은 구영리에서 범서중학교를 경유합니다" in html
    assert 'href="/info"' in html


@freeze_time("2026-10-05T12:00:00+09:00")
def test_seed_743_notice_after_effective_wording(app):
    html = _html(app.test_client(), "/timetable?day=0")
    assert "743번은 이제 구영리에서 범서중학교를 경유합니다 (10월 3일 변경" in html
    assert "10월 3일부터" not in html


@freeze_time("2026-11-01T00:00:00+09:00")
def test_seed_743_notice_expires_after_show_until(app):
    html = _html(app.test_client(), "/timetable?day=0")
    assert "notice-list" not in html
    assert "범서중학교" not in html


@freeze_time("2026-10-02T12:00:00+09:00")
def test_notice_english(app):
    html = _html(app.test_client(), "/timetable?day=0&lang=en")
    assert "From Oct 3, bus 743 passes Beomseo Middle School" in html
    assert "Route change" in html


# ── 화면·노선 필터 ─────────────────────────────────────────────────────────

@freeze_time("2026-10-02T12:00:00+09:00")
def test_busno_shows_only_selected_route_notices(app):
    client = app.test_client()
    assert "범서중학교" in _html(client, "/busno?bus=743")
    assert "범서중학교" not in _html(client, "/busno?bus=713")


@freeze_time("2026-10-02T12:00:00+09:00")
@pytest.mark.parametrize("url", ["/busno", "/busno?bus=zzz"])
def test_busno_filter_follows_the_bus_actually_shown(app, url):
    """bus 미지정·오류면 페이지는 기본 노선(513)을 보여 주므로, 743 공지도 숨는다."""
    html = _html(app.test_client(), url)
    assert "범서중학교" not in html
    assert "범서중학교" in _html(app.test_client(), "/busno?bus=743")   # 대조군


@freeze_time("2026-10-02T12:00:00+09:00")
def test_info_surface_not_in_seed_targets(app):
    """seed 공지는 info 화면을 대상으로 하지 않는다(info 본문에 같은 안내가 이미 있음)."""
    html = _html(app.test_client(), "/info")
    assert "notice-list" not in html


@freeze_time("2026-10-02T12:00:00+09:00")
def test_live_file_overrides_seed_and_escapes_text(app):
    _write_live(app, [{
        "id": "x", "kind": "suspension", "surfaces": ["all"],
        "text": {"ko": "<script>alert(1)</script> 운행 중단"},
    }])
    html = _html(app.test_client(), "/timetable?day=0")
    assert "범서중학교" not in html                    # live 가 있으면 seed 무시
    assert "notice-suspension" in html
    assert "&lt;script&gt;" in html and "<script>alert(1)</script>" not in html


@freeze_time("2026-10-02T12:00:00+09:00")
def test_corrupt_live_file_falls_back_to_seed(app):
    _live_path(app).write_text("{ broken", encoding="utf-8")
    html = _html(app.test_client(), "/timetable?day=0")
    assert "10월 3일부터 743번은" in html


def test_seed_is_not_publicly_served(app):
    assert app.test_client().get("/static/data/notices.json").status_code == 404


@freeze_time("2026-10-02T12:00:00+09:00")
@pytest.mark.parametrize("url", ["/board", "/unist", "/stops"])
def test_realtime_pages_render_notice_once(app, url):
    """실시간 화면(외부 API 실패 시에도 200)에 공지가 한 번만 그려진다."""
    html = _html(app.test_client(), url)
    assert html.count('class="notice notice-route_change"') == 1


@freeze_time("2026-10-02T12:00:00+09:00")
def test_lite_renders_notice_as_plain_text(app):
    html = _html(app.test_client(), "/lite")
    assert "[노선 변경] 10월 3일부터 743번은" in html
    assert 'href="/info"' in html
    assert "<style" not in html and "<script" not in html   # zero-CSS/JS 원칙 유지


@freeze_time("2026-10-02T12:00:00+09:00")
@pytest.mark.parametrize("url, surface", [("/board", "board"), ("/unist", "unist"), ("/stops", "stops")])
def test_htmx_pages_poll_notice_region(app, url, surface):
    """표만 부분 갱신하는 화면은 공지 영역을 따로 60초마다 다시 불러온다."""
    html = _html(app.test_client(), url)
    assert f'hx-get="/partial/notices?surface={surface}&amp;lang=ko"' in html
    assert 'hx-trigger="every 60s"' in html


@freeze_time("2026-10-02T12:00:00+09:00")
def test_poll_url_keeps_language(app):
    """쿠키가 막혀 있어도 60초 뒤 갱신된 공지가 같은 언어로 나온다."""
    client = app.test_client(use_cookies=False)
    html = _html(client, "/board?lang=en")
    assert 'surface=board&amp;lang=en"' in html
    assert "From Oct 3, bus 743" in _html(client, "/partial/notices?surface=board&lang=en")


@freeze_time("2026-10-02T12:00:00+09:00")
def test_static_pages_do_not_poll(app):
    assert "/partial/notices" not in _html(app.test_client(), "/timetable?day=0")


def test_notice_partial_reflects_phase_change_and_expiry(app):
    client = app.test_client()
    with freeze_time("2026-10-02T23:59:00+09:00"):
        before = _html(client, "/partial/notices?surface=board")
    with freeze_time("2026-10-03T00:00:00+09:00"):
        after = _html(client, "/partial/notices?surface=board")
    with freeze_time("2026-11-01T00:00:00+09:00"):
        expired = _html(client, "/partial/notices?surface=board")
    assert "10월 3일부터 743번은" in before
    assert "743번은 이제" in after and "10월 3일부터" not in after
    assert 'id="notice-region"' in expired and "notice-list" not in expired   # 자리는 유지
    assert "<html" not in before


@pytest.mark.parametrize("surface", ["", "timetable", "admin", "<x>"])
def test_notice_partial_rejects_non_poll_surface(app, surface):
    html = _html(app.test_client(), f"/partial/notices?surface={surface}")
    assert html.strip() == ""


@freeze_time("2026-10-02T12:00:00+09:00")
@pytest.mark.parametrize("url", ["/partial/board", "/partial/unist", "/partial/stops"])
def test_partials_do_not_render_notices(app, url):
    """HTMX 부분 갱신 응답에는 공지가 없어야 한다(중복 표시 방지)."""
    resp = app.test_client().get(url)
    assert "notice-list" not in resp.data.decode("utf-8")


# ── /admin/notices ────────────────────────────────────────────────────────

def test_admin_notices_requires_login(app):
    assert app.test_client().get("/admin/notices").status_code in (302, 401)


def test_admin_notices_lists_seed_with_preview_at(authed):
    html = _html(authed, "/admin/notices?at=2026-10-05T09:00")
    assert "743-beomseo-2026" in html
    assert "시행 후" in html and "743번은 이제" in html


def test_admin_notices_save_toggle_remove_roundtrip(authed, app):
    form = {
        "csrf_token": _CSRF, "id": "holiday-1225", "kind": "info",
        "routes": ["513", "713"], "surfaces": ["board", "timetable"],
        "show_from": "2026-12-20", "show_until": "2026-12-25",
        "effective_from": "", "text_ko": "{date} 성탄절은 일/공휴일 시간표로 운행합니다.",
        "text_en": "", "text_after_ko": "", "text_after_en": "",
        "link": "", "priority": "3", "enabled": "1",
    }
    resp = authed.post("/admin/notices/save", data=form)
    assert resp.status_code == 302
    saved = N.NoticeStore(_live_path(app)).get("holiday-1225")
    assert saved["routes"] == ["513", "713"] and saved["surfaces"] == ["board", "timetable"]
    assert saved["priority"] == 3 and saved["enabled"] is True
    # seed 항목도 함께 이관됐다
    assert N.NoticeStore(_live_path(app)).get("743-beomseo-2026") is not None

    authed.post("/admin/notices/toggle", data={"csrf_token": _CSRF, "id": "holiday-1225", "enabled": "0"})
    assert N.NoticeStore(_live_path(app)).get("holiday-1225")["enabled"] is False

    authed.post("/admin/notices/remove", data={"csrf_token": _CSRF, "id": "holiday-1225"})
    assert N.NoticeStore(_live_path(app)).get("holiday-1225") is None


def test_admin_notices_save_invalid_flashes_and_keeps_file(authed, app):
    resp = authed.post("/admin/notices/save", data={
        "csrf_token": _CSRF, "id": "bad id", "text_ko": "x",
    }, follow_redirects=True)
    assert "저장하지 못했습니다" in resp.data.decode("utf-8")
    assert not _live_path(app).exists()


def test_admin_rename_does_not_duplicate(authed, app):
    base = {"csrf_token": _CSRF, "kind": "info", "text_ko": "안내", "enabled": "1"}
    authed.post("/admin/notices/save", data={**base, "id": "a1"})
    authed.post("/admin/notices/save", data={**base, "id": "a2", "original_id": "a1"})
    ids = [e["id"] for e in N.NoticeStore(_live_path(app)).load_entries()]
    assert "a2" in ids and "a1" not in ids


def test_admin_corrupt_file_warns_and_blocks_save(authed, app):
    _live_path(app).write_text("[{bad", encoding="utf-8")
    html = _html(authed, "/admin/notices")
    assert "읽지 못했습니다" in html
    resp = authed.post("/admin/notices/save", data={
        "csrf_token": _CSRF, "id": "n", "kind": "info", "text_ko": "x", "enabled": "1",
    }, follow_redirects=True)
    assert "깨져" in resp.data.decode("utf-8")
    assert _live_path(app).read_text(encoding="utf-8") == "[{bad"


def test_admin_seed_drift_import(authed, app):
    _write_live(app, [{"id": "mine", "text": {"ko": "내 공지"}}])
    html = _html(authed, "/admin/notices")
    assert "743-beomseo-2026" in html and "편집본에 없음" in html
    authed.post("/admin/notices/import-seed", data={"csrf_token": _CSRF, "id": "743-beomseo-2026"})
    assert N.NoticeStore(_live_path(app)).get("743-beomseo-2026") is not None


def test_backup_restore_rejects_invalid_notices(tmp_path):
    import io
    import zipfile
    from bushexa.services.backup import RestoreError, validate_and_restore
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("MANIFEST.json", json.dumps({"version": 1}))
        zf.writestr("notices.json", json.dumps({"id": "x"}))
    with pytest.raises(RestoreError, match="notices.json"):
        validate_and_restore(buf.getvalue(), tmp_path, tmp_path / "timetable")
    assert not (tmp_path / "notices.json").exists()


def test_admin_notices_post_requires_csrf(authed):
    resp = authed.post("/admin/notices/save", data={"id": "x", "text_ko": "x"})
    assert resp.status_code == 400
