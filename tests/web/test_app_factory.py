"""W1 テスト: app factory, cookie flags.

AC-1: create_app(test_config).test_client().get('/') → 200 or 302 to /board.
AC-2: session を発生させる応답の Set-Cookie に HttpOnly と SameSite=Lax が含まれる.
"""

from __future__ import annotations

import dataclasses

import pytest

from bushexa.web.app import create_app


# ---------------------------------------------------------------------------
# AC-1 — root route returns 200 or 302 to /board
# ---------------------------------------------------------------------------

def test_root_ok(app_config_test):
    """GET / → 200 또는 /board 302.

    독립 출처: P4 W1 AC-1 설계 명세 — '/' 는 200 또는 board로의 302.
    """
    app = create_app(app_config_test)
    client = app.test_client()
    resp = client.get("/")
    assert resp.status_code in (200, 302), (
        f"Expected 200 or 302, got {resp.status_code}"
    )
    if resp.status_code == 302:
        location = resp.headers.get("Location", "")
        assert "/board" in location, (
            f"302 redirect should go to /board, got Location: {location}"
        )


# ---------------------------------------------------------------------------
# AC-2 — session cookie flags: HttpOnly + SameSite=Lax
# ---------------------------------------------------------------------------

def test_cookie_flags(app_config_test):
    """세션을 발생시키는 응답의 Set-Cookie 에 HttpOnly 와 SameSite=Lax 포함 여부.

    독립 출처: S1 보안 명세 (P4 §10) — "HttpOnly·SameSite=Lax 설정".
    before_request 에서 csrf_token 을 session 에 쓰므로 첫 GET 에서 Set-Cookie 발생.
    """
    app = create_app(app_config_test)
    client = app.test_client()

    # GET / triggers before_request → session["csrf_token"] is written → Set-Cookie emitted
    resp = client.get("/")

    set_cookie = resp.headers.get("Set-Cookie", "")
    assert set_cookie, (
        "No Set-Cookie header found. "
        "The app must write to the session on the first request so Flask emits Set-Cookie."
    )

    cookie_lower = set_cookie.lower()
    assert "httponly" in cookie_lower, (
        f"HttpOnly flag missing from Set-Cookie: {set_cookie!r}"
    )
    assert "samesite=lax" in cookie_lower, (
        f"SameSite=Lax missing from Set-Cookie: {set_cookie!r}"
    )


# ---------------------------------------------------------------------------
# S1 회귀 — SESSION_COOKIE_SECURE 가 config 값을 그대로 따르는지
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("secure", [False, True])
def test_session_cookie_secure_follows_config(app_config_test, secure):
    """SESSION_COOKIE_SECURE는 config 값(env BUSHEXA_SESSION_COOKIE_SECURE)을 그대로 따라야 한다 (S1 회귀).

    독립 출처: P5 W1 설계 — app.config["SESSION_COOKIE_SECURE"] == config.session_cookie_secure.
    기본 fixture 를 dataclasses.replace 로 두 값(False/True) 모두 만들어 전파를 검증한다.
    """
    config = dataclasses.replace(app_config_test, session_cookie_secure=secure)
    app = create_app(config)
    assert app.config["SESSION_COOKIE_SECURE"] is secure, (
        f"SESSION_COOKIE_SECURE 가 config 값({secure})을 따르지 않음: "
        f"{app.config['SESSION_COOKIE_SECURE']!r}"
    )
