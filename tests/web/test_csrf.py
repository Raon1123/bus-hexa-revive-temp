"""EC-11 / S5 CSRF 인프라 테스트 (W10 + CSRF infra).

E-13 준수: 기대값은 spec상 "CSRF 토큰 없으면 거부(400/403)" 출처.
"""
from __future__ import annotations

from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from bushexa.config import AppConfig
from bushexa.web.app import create_app

_KST = ZoneInfo("Asia/Seoul")
_CORRECT_PW = "correcthorse"


def _make_app(tmp_path: Path) -> object:
    pw_path = tmp_path / "manager_password.txt"
    pw_path.write_text(_CORRECT_PW)
    config = AppConfig(
        api_key="test-api-key",
        database_url="sqlite:///:memory:",
        session_secret="test-secret",
        manager_password_path=pw_path,
        data_dir=tmp_path / "data",
        tz=_KST,
        log_level="DEBUG",
        log_dir=tmp_path / "logs",
    )
    return create_app(config)


# ──────────────────────────────────────────────────
# 1. 토큰 없는 POST /admin/login → 400/403
# ──────────────────────────────────────────────────

def test_csrf_missing_token_rejected(tmp_path):
    """CSRF 토큰이 없는 POST /admin/login은 400/403으로 거부된다.

    독립 출처: S5 spec "토큰 없으면 거부", EC-11.
    """
    app = _make_app(tmp_path)
    client = app.test_client()
    # 세션 초기화 (csrf_token seed는 before_request에서 자동으로 이뤄짐)
    # — 하지만 토큰을 form body에 포함하지 않음
    resp = client.post("/admin/login", data={"password": _CORRECT_PW})
    assert resp.status_code in (400, 403), (
        f"POST without csrf_token should be 400/403, got {resp.status_code}"
    )


# ──────────────────────────────────────────────────
# 2. 올바른 토큰 → 로그인 로직까지 진행 (400/403 아님)
# ──────────────────────────────────────────────────

def test_csrf_correct_token_passes(tmp_path):
    """올바른 CSRF 토큰 포함 POST는 400/403으로 거부되지 않고 로그인 로직까지 진행.

    독립 출처: S5 spec "올바른 토큰 포함 시 통과", EC-11.
    """
    app = _make_app(tmp_path)
    client = app.test_client()

    # 세션에 토큰 주입
    token = "valid-csrf-token-xyz"
    with client.session_transaction() as sess:
        sess["csrf_token"] = token

    resp = client.post("/admin/login", data={"password": _CORRECT_PW, "csrf_token": token})
    # 로그인 성공 → 302로 redirect (401/400/403 아님)
    assert resp.status_code not in (400, 403), (
        f"POST with correct csrf_token should not be 400/403, got {resp.status_code}"
    )


# ──────────────────────────────────────────────────
# 3. 불일치 토큰 → 400/403
# ──────────────────────────────────────────────────

def test_csrf_wrong_token_rejected(tmp_path):
    """CSRF 토큰이 세션 값과 다르면 400/403으로 거부된다.

    독립 출처: S5 spec "토큰 불일치 시 거부", EC-11.
    """
    app = _make_app(tmp_path)
    client = app.test_client()

    with client.session_transaction() as sess:
        sess["csrf_token"] = "correct-token"

    resp = client.post("/admin/login", data={"password": _CORRECT_PW, "csrf_token": "wrong-token"})
    assert resp.status_code in (400, 403), (
        f"POST with wrong csrf_token should be 400/403, got {resp.status_code}"
    )


# ──────────────────────────────────────────────────
# 4. 비-admin GET은 CSRF 영향 없음
# ──────────────────────────────────────────────────

def test_non_admin_get_unaffected(tmp_path):
    """비-admin GET (/board 등)은 CSRF 토큰 없이도 영향받지 않는다.

    독립 출처: S5 spec — admin POST만 적용, GET 면제, 비-admin 라우트 면제.
    """
    app = _make_app(tmp_path)
    client = app.test_client()
    # /board GET — 토큰 없이도 400/403이 아니어야 함
    # 도메인 mock 없이 500이 날 수 있으나 400/403은 아님
    resp = client.get("/board")
    assert resp.status_code not in (400, 403), (
        f"GET /board should not be CSRF-rejected, got {resp.status_code}"
    )
