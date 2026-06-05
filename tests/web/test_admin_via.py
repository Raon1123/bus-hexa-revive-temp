"""경유지(주요 정류소) 편집 — ViaEditor 저장소 + 도메인 override 우선 + admin 라우트.

기대값은 이 파일이 정의한 알려진 입력에서 정해짐(E-13). 네트워크 0건.
"""
from __future__ import annotations

import json

import pytest
import pytz

from bushexa.config import AppConfig
from bushexa.data.constants import VIA_STOPS
from bushexa.domain.board import _via_for
from bushexa.services.via_editor import ViaEditor, default_via_path
from bushexa.web.app import create_app

_KST = pytz.timezone("Asia/Seoul")
_CSRF = "via-csrf-token"


# ── ViaEditor 저장소 ───────────────────────────────────────────────────────

def test_via_editor_roundtrip(tmp_path):
    """저장→로드 왕복. 빈/공백 항목은 저장 시 제거된다."""
    ed = ViaEditor(tmp_path / "via_overrides.json")
    assert ed.load() == {}, "파일 부재 시 빈 dict"

    ed.save({"713": {"명촌": "수정된 경유 - 명촌"}, "743": {"명촌": "   "}})
    loaded = ed.load()
    assert loaded == {"713": {"명촌": "수정된 경유 - 명촌"}}, "공백-only 항목은 저장 제외"


def test_via_editor_corrupt_file_returns_empty(tmp_path):
    """파손 JSON은 빈 override로 처리(상수 fallback 유지)."""
    p = tmp_path / "via_overrides.json"
    p.write_text("{not json", encoding="utf-8")
    assert ViaEditor(p).load() == {}


# ── 도메인 우선순위: override > VIA_STOPS > 노선 fallback ────────────────────

def test_via_for_override_beats_constant():
    """override가 있으면 상수 VIA_STOPS보다 우선한다."""
    overrides = {"713": {"명촌": "OVERRIDE-VIA"}}
    # 713/명촌 방면: terminal "명촌 (시내) 방면" → via_key "명촌"
    out = _via_for("195000178", "713", "명촌 (시내) 방면", overrides)
    assert out == "OVERRIDE-VIA"


def test_via_for_falls_back_to_constant_without_override():
    """override가 없으면 상수 VIA_STOPS 값을 쓴다(E-13: 상수 원문)."""
    out = _via_for("195000178", "713", "명촌 (시내) 방면", {})
    assert out == VIA_STOPS["713"]["명촌"]


# ── admin 라우트 ──────────────────────────────────────────────────────────

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


def test_via_index_requires_login(app):
    """비로그인 GET /admin/via → 로그인으로 리다이렉트(302)."""
    resp = app.test_client().get("/admin/via")
    assert resp.status_code in (302, 401)


def test_via_index_lists_entries(authed):
    """GET /admin/via → 200, VIA_STOPS의 노선·목적지가 표시된다."""
    client, _ = authed
    resp = client.get("/admin/via")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    assert "713" in html and "명촌" in html
    assert 'name="713|명촌"' in html, "편집 필드명이 노출돼야 함"


def test_via_index_includes_unist_bound_directions(authed):
    """advisor 회귀: VIA_STOPS에 없는 'UNIST 방면'도 편집 대상에 포함돼야 한다.

    독립 출처: ROUTEID에 713 'UNIST 방면'(195000177)이 존재 → 필드 '713|UNIST'가 노출되어야 함.
    """
    client, _ = authed
    html = client.get("/admin/via").data.decode("utf-8")
    assert 'name="713|UNIST"' in html, "UNIST 방면 경유지도 admin에서 편집 가능해야 함"


def test_via_save_persists_override(authed):
    """POST /admin/via → override 파일에 저장되고 board가 읽을 수 있다."""
    client, app = authed
    resp = client.post("/admin/via", data={
        "csrf_token": _CSRF,
        "713|명촌": "관리자가 바꾼 경유 - 명촌",
    })
    assert resp.status_code in (302, 303)

    config = app.config["BUSHEXA_CONFIG"]
    saved = ViaEditor(default_via_path(config.data_dir)).load()
    assert saved.get("713", {}).get("명촌") == "관리자가 바꾼 경유 - 명촌"


def test_via_save_default_value_not_stored(authed):
    """기본값과 동일하게 제출하면 override로 저장하지 않는다(상수 fallback 유지)."""
    client, app = authed
    client.post("/admin/via", data={
        "csrf_token": _CSRF,
        "713|명촌": VIA_STOPS["713"]["명촌"],  # 기본값 그대로
    })
    config = app.config["BUSHEXA_CONFIG"]
    saved = ViaEditor(default_via_path(config.data_dir)).load()
    assert "713" not in saved, "기본값과 같으면 override 불필요"
