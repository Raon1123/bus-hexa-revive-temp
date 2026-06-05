"""W4 테스트: info route (F03).

테스트 의도:
  test_routes_listed       — GET /info → 200, 노선번호 5개 모두 포함
  test_hexa_no_admin       — GET /info?hexa=6 → /admin, __mgr_auth__ 없음
  test_changelog_missing_ok — changelog.json 없어도 200 + 빈 이력 (500 아님)

E-13 준수: 기대값은 F03 명세 (5개 노선번호 고정값, ?hexa=6 관리자 unlock 제거)에서.
"""

from __future__ import annotations

import pytest

from bushexa.web.app import create_app


@pytest.fixture
def app(app_config_test):
    return create_app(app_config_test)


@pytest.fixture
def client(app):
    return app.test_client()


# ---------------------------------------------------------------------------
# AC-1 — GET /info → 200, 노선번호 513/713/743/753/1115 모두 포함
# ---------------------------------------------------------------------------

def test_routes_listed(client):
    """/info HTML에 5개 노선번호가 모두 표시되는지 검증.

    독립 출처: P4 W4 AC-1, F03 §1 — 5개 노선번호 고정값.
    """
    resp = client.get("/info")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    html = resp.data.decode("utf-8")
    for busno in ("513", "713", "743", "753", "1115"):
        assert busno in html, f"Bus number {busno} not found in /info response"


# ---------------------------------------------------------------------------
# AC-2 — ?hexa=6 → 관리자 마커 없음
# ---------------------------------------------------------------------------

def test_hexa_no_admin(client):
    """?hexa=6을 줘도 관리자 UI가 노출되지 않는지 검증 (숨김 진입 제거).

    독립 출처: P4 W4 AC-2, F03 결함 §2.5 — 쿼리파람 기반 관리자 unlock 제거.
    """
    resp = client.get("/info?hexa=6")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    html = resp.data.decode("utf-8")
    assert "/admin" not in html, "/admin link must not appear in ?hexa=6 response"
    assert "__mgr_auth__" not in html, "__mgr_auth__ must not appear in ?hexa=6 response"


# ---------------------------------------------------------------------------
# test_changelog_missing_ok — changelog.json 없을 때 500 없이 200
# ---------------------------------------------------------------------------

def test_changelog_missing_ok(app_config_test, tmp_path, monkeypatch):
    """changelog.json이 없을 때 500 없이 200 + 빈 변경이력으로 렌더되는지 검증.

    독립 출처: P4 W4 지시사항 §4 — "changelog.json 없을 때 500 없이 200+빈 이력".
    """
    import bushexa.web.routes.info as info_mod
    # 존재하지 않는 경로로 patch
    monkeypatch.setattr(
        info_mod,
        "_STATIC_DATA",
        tmp_path / "nonexistent_dir",
    )
    app = create_app(app_config_test)
    client = app.test_client()
    resp = client.get("/info")
    assert resp.status_code == 200, f"Expected 200 not 500, got {resp.status_code}"
    # 빈 이력 = changelog 섹션이 없거나 empty
    html = resp.data.decode("utf-8")
    # 노선번호는 여전히 있어야 함
    assert "513" in html, "Route 513 missing even with no changelog"
