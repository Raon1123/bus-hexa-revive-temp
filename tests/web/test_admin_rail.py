"""/admin/rail 검증 — 상태 화면, 재수집·재계산 잡 시작(모의 잡), 환승 기본값 저장, 프로필 적용·버리기·되돌리기."""
from __future__ import annotations

import json

import pytest

from bushexa.config import AppConfig
from bushexa.services.leg_profile import (
    candidate_profile_path,
    default_profile_path,
    previous_profile_path,
    save_profile,
)
from bushexa.services.recrawl_job import ConflictError
from bushexa.time_utils import KST, KSTClock
from bushexa.web.app import create_app

_CSRF = "test-csrf-rail"


def _profile(n, p50, period=("2026-01-01", "2026-06-01")):
    stats = {"n": n, "p10": p50 - 2, "p50": p50, "p90": p50 + 2}
    return {"version": 1, "period": list(period), "generated_at": "2026-09-30T00:00:00+09:00",
            "legs": {"deokha_unist": {"by_day": {"0": {"all": stats, "hours": {}}}}}}


class _MockJob:
    """start 인자 기록, 두 번째부터 ConflictError. snapshot 은 고정값."""

    def __init__(self):
        self.calls = []

    def start(self, **params):
        self.calls.append(params)
        if len(self.calls) > 1:
            raise ConflictError("busy")
        return "job1"

    def snapshot(self, limit=30):
        return {"job_id": "job1", "running": False, "done": True, "error": None,
                "events": [{"kind": "progress", "payload": {"label": "울산→부산 2026-09-30", "ok": True}}]}


@pytest.fixture
def client(tmp_path):
    config = AppConfig(api_key="k", database_url="sqlite:///:memory:", session_secret="s",
                       manager_password_path=tmp_path / "pw.txt", data_dir=tmp_path / "data",
                       tz=KST, log_level="INFO", log_dir=tmp_path / "logs")
    app = create_app(config)
    app.config["TESTING"] = True
    app.config["_RAIL_CRAWL_JOB"] = _MockJob()
    app.config["_KTX_PROFILE_JOB"] = _MockJob()
    c = app.test_client()
    with c.session_transaction() as sess:
        sess["admin_authed"] = True
        sess["csrf_token"] = _CSRF
    return c, app, tmp_path / "data"


def test_rail_page_requires_login(tmp_path):
    """로그인 없이 /admin/rail 은 로그인 화면으로 보낸다."""
    config = AppConfig(api_key="k", database_url="sqlite:///:memory:", session_secret="s",
                       manager_password_path=tmp_path / "pw.txt", data_dir=tmp_path / "data",
                       tz=KST, log_level="INFO", log_dir=tmp_path / "logs")
    resp = create_app(config).test_client().get("/admin/rail")
    assert resp.status_code == 302 and "/admin/login" in resp.headers["Location"]


def test_rail_page_renders_status_warnings_and_nav(client):
    """철도 캐시가 없으면 구간마다 '재수집 필요' 경고, 프로필 없음 안내, 사이드바 항목이 보인다."""
    c, _, _ = client
    html = c.get("/admin/rail").data.decode()
    assert "철도·KTX 연계 운영" in html and "저장된 날짜 없음" in html
    assert "프로필 없음" in html and 'href="/admin/rail"' in html
    assert "울산→부산 2026-09-30" in html                    # 잡 진행 로그


def test_rail_page_shows_stored_pairs(client):
    """rail_timetable.json 에 오늘 열차가 있으면 오늘 편수와 정차역 확인 날짜를 보인다."""
    c, _, data_dir = client
    today = KSTClock().now().date().isoformat()
    store = {"version": 1, "metro": {}, "trains": {"last_success_date": today, "pairs": {
        "NATH13717-NAT010000": {"dates": {today: {"trains": [
            {"dep": f"{today}T07:00:00+09:00", "arr": f"{today}T09:30:00+09:00", "stops": [{"name": "대전", "arr": "08:30"}]},
            {"dep": f"{today}T08:00:00+09:00", "arr": f"{today}T10:30:00+09:00", "stops": None}]}}}}}}
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "rail_timetable.json").write_text(json.dumps(store), encoding="utf-8")
    html = c.get("/admin/rail").data.decode()
    assert "1일 확인 · 오늘 모름 1편" in html and "성공" in html


def test_recrawl_starts_job_with_clamped_days_and_reports_conflict(client):
    """재수집 POST 는 일수를 1~14 로 자르고 잡을 시작한다. 진행 중이면 안내 후 되돌아온다."""
    c, app, _ = client
    resp = c.post("/admin/rail/recrawl", data={"days": "99", "csrf_token": _CSRF})
    assert resp.status_code == 302
    assert app.config["_RAIL_CRAWL_JOB"].calls == [{"days": 14}]
    resp = c.post("/admin/rail/recrawl", data={"days": "3", "csrf_token": _CSRF}, follow_redirects=True)
    assert "이미 진행 중" in resp.data.decode()


def test_job_status_json(client):
    """잡 상태 JSON: 알려진 종류만, 모르는 종류는 404."""
    c, _, _ = client
    assert c.get("/admin/rail/job/rail").get_json()["done"] is True
    assert c.get("/admin/rail/job/nope").status_code == 404


def test_transfer_settings_save_applies_to_ktx_page(client):
    """환승 기본값을 저장하면 /ktx 폼 기본값이 바뀌고, 범위 밖 값은 거부한다."""
    c, _, data_dir = client
    c.post("/admin/rail/settings", data={"transfer_station_min": "8", "transfer_jinmok_min": "",
                                         "csrf_token": _CSRF})
    saved = json.loads((data_dir / "ktx_settings.json").read_text(encoding="utf-8"))
    assert saved == {"transfer_station_min": 8}
    html = c.get("/ktx").data.decode()
    assert 'name="ts" min="0" max="30" value="8"' in html and 'name="tj" min="0" max="30" value="5"' in html
    assert 'value="3"' in c.get("/ktx?ts=3").data.decode()          # 쿼리가 우선
    resp = c.post("/admin/rail/settings", data={"transfer_station_min": "99", "csrf_token": _CSRF},
                  follow_redirects=True)
    assert "입력값 오류" in resp.data.decode()


def test_profile_rebuild_apply_merge_discard_and_rollback(client):
    """후보 계산 잡 시작 → (후보 있음) 병합 적용 시 표본 많은 쪽만 → 이전 값 되돌리기 → 후보 버리기."""
    c, app, data_dir = client
    c.post("/admin/rail/profile/rebuild", data={"use_tsv": "on", "csrf_token": _CSRF})
    assert app.config["_KTX_PROFILE_JOB"].calls == [{"use_tsv": True}]

    save_profile(default_profile_path(data_dir), _profile(700, 61.0))
    save_profile(candidate_profile_path(data_dir), _profile(40, 58.0, ("2026-09-01", "2026-09-30")))
    html = c.get("/admin/rail").data.decode()
    assert "후보와 비교" in html and "58.0분" in html

    c.post("/admin/rail/profile/apply", data={"mode": "merge", "csrf_token": _CSRF})
    cur = json.loads(default_profile_path(data_dir).read_text(encoding="utf-8"))
    assert cur["legs"]["deokha_unist"]["by_day"]["0"]["all"]["n"] == 700      # 표본 많은 현재 값 유지
    assert cur["period"] == ["2026-01-01", "2026-09-30"] and cur["merged"]
    assert not candidate_profile_path(data_dir).exists() and previous_profile_path(data_dir).exists()

    c.post("/admin/rail/profile/rollback", data={"csrf_token": _CSRF})
    cur = json.loads(default_profile_path(data_dir).read_text(encoding="utf-8"))
    assert "merged" not in cur

    save_profile(candidate_profile_path(data_dir), _profile(40, 58.0))
    c.post("/admin/rail/profile/apply", data={"mode": "replace", "csrf_token": _CSRF})
    cur = json.loads(default_profile_path(data_dir).read_text(encoding="utf-8"))
    assert cur["legs"]["deokha_unist"]["by_day"]["0"]["all"]["n"] == 40       # 교체

    save_profile(candidate_profile_path(data_dir), _profile(1, 1.0))
    c.post("/admin/rail/profile/discard", data={"csrf_token": _CSRF})
    assert not candidate_profile_path(data_dir).exists()


def test_actions_are_audited(client):
    """관리자 작업은 감사 로그에 남는다."""
    c, _, data_dir = client
    c.post("/admin/rail/recrawl", data={"days": "2", "csrf_token": _CSRF})
    c.post("/admin/rail/settings", data={"transfer_station_min": "6", "csrf_token": _CSRF})
    audit = (data_dir / "audit_log.json").read_text(encoding="utf-8")
    assert "rail.recrawl" in audit and "ktx_settings.save" in audit


def test_post_without_csrf_is_rejected(client):
    """CSRF 토큰 없는 POST 는 거부된다(app.before_request)."""
    c, app, _ = client
    assert c.post("/admin/rail/recrawl", data={"days": "2"}).status_code in (400, 403)
    assert app.config["_RAIL_CRAWL_JOB"].calls == []
