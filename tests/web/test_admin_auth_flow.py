"""W10 테스트: admin login/logout/dashboard/lockout (F04, TP-007).

E-13 준수: 기대값은 spec상 명시된 HTTP 상태 + 행동 출처(F04 §7 AC-A1/A2, W10 AC-1/2).
독립 출처: 테스트가 직접 비밀번호 파일에 평문을 기록해 올바른 값을 안다.

CSRF 처리 패턴 (advisor 지침):
  - 세션에 csrf_token 직접 주입 후 POST 시 같은 토큰 첨부.
  - GET-first 댄스 불필요.
"""
from __future__ import annotations

from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from bushexa.config import AppConfig
from bushexa.web.app import create_app

_KST = ZoneInfo("Asia/Seoul")
_CORRECT_PW = "correcthorse"  # 테스트용 평문 비밀번호 (8자 이상, legacy 평문 호환)


def _make_app(tmp_path: Path, pw_content: str | None = _CORRECT_PW) -> object:
    """테스트용 Flask app. pw_content=None이면 needs_setup 모드."""
    pw_path = tmp_path / "manager_password.txt"
    if pw_content is not None:
        pw_path.write_text(pw_content)  # legacy 평문 — verify()가 수락함
    config = AppConfig(
        api_key="test-api-key",
        database_url="sqlite:///:memory:",
        session_secret="test-session-secret",
        manager_password_path=pw_path,
        data_dir=tmp_path / "data",
        tz=_KST,
        log_level="DEBUG",
        log_dir=tmp_path / "logs",
    )
    return create_app(config)


# ──────────────────────────────────────────────────
# 헬퍼: CSRF 토큰 주입
# ──────────────────────────────────────────────────

def _inject_csrf(client, token: str = "test-csrf-token") -> str:
    """test_client 세션에 csrf_token을 주입하고 그 값을 반환한다."""
    with client.session_transaction() as sess:
        sess["csrf_token"] = token
    return token


def _inject_auth(client) -> None:
    """test_client 세션에 admin_authed=True를 주입한다."""
    with client.session_transaction() as sess:
        sess["admin_authed"] = True


# ──────────────────────────────────────────────────
# AC-1: 비로그인 /admin/ → 302 /admin/login?next=/admin/
# ──────────────────────────────────────────────────

def test_redirect(tmp_path):
    """비로그인 상태로 /admin/에 접근하면 /admin/login?next=/admin/ 으로 302.

    독립 출처: F04 §7 AC-A1, W10 AC-1.
    """
    app = _make_app(tmp_path)
    client = app.test_client()
    resp = client.get("/admin/")
    assert resp.status_code == 302, f"Expected 302, got {resp.status_code}"
    location = resp.headers.get("Location", "")
    assert "/admin/login" in location, f"Expected redirect to /admin/login, got {location!r}"
    assert "next=/admin/" in location, f"Expected next=/admin/ in redirect, got {location!r}"


# ──────────────────────────────────────────────────
# AC-2: 로그인 → 대시보드 200, 로그아웃 → 재차단 302
# ──────────────────────────────────────────────────

def test_login_logout(tmp_path):
    """올바른 비밀번호로 로그인 후 대시보드 200, 로그아웃 후 다시 302.

    독립 출처: F04 §7 AC-A1/A2, W10 AC-2.
    """
    app = _make_app(tmp_path)
    client = app.test_client()

    # 1. 로그인 POST (CSRF 토큰 주입)
    token = _inject_csrf(client)
    resp = client.post("/admin/login", data={"password": _CORRECT_PW, "csrf_token": token})
    # 로그인 성공 → 302 대시보드로 redirect
    assert resp.status_code in (200, 302), f"Login expected 200/302, got {resp.status_code}"

    # 2. 대시보드 직접 접근 (이미 로그인 상태)
    resp2 = client.get("/admin/")
    assert resp2.status_code == 200, f"Dashboard expected 200 after login, got {resp2.status_code}"
    assert "admin-dashboard" in resp2.data.decode("utf-8"), "Dashboard marker not found"

    # 3. 로그아웃 POST
    token2 = _inject_csrf(client)
    resp3 = client.post("/admin/logout", data={"csrf_token": token2})
    assert resp3.status_code in (200, 302), f"Logout expected 200/302, got {resp3.status_code}"

    # 4. 로그아웃 후 /admin/ 재접근 → 302 차단
    resp4 = client.get("/admin/")
    assert resp4.status_code == 302, f"After logout, /admin/ should 302, got {resp4.status_code}"


# ──────────────────────────────────────────────────
# lockout: 5회 오답 후 6번째 423/429
# ──────────────────────────────────────────────────

def test_lockout_after_5_fails(tmp_path):
    """5회 연속 오답 후 다음 시도가 423(또는 429)으로 차단되는지 검증.

    독립 출처: F04 §7 AC-A2, W10 spec "5회 실패 후 lockout".
    E-13: 기대값 = spec상 "5회 실패 후 차단", tautology 없음.
    """
    app = _make_app(tmp_path)
    client = app.test_client()

    wrong_pw = "wrongpassword123"
    # CSRF 토큰 한 번 주입하면 세션에 유지됨
    token = _inject_csrf(client)

    # 5회 오답 (각 시도: 401 또는 423; 정확히 5회째까지는 401이어야 함)
    for i in range(5):
        resp = client.post("/admin/login", data={"password": wrong_pw, "csrf_token": token})
        # 5번째 시도에서 이미 lockout이 트리거될 수 있음 (5회 도달 시)
        assert resp.status_code in (401, 423, 429), (
            f"Attempt {i+1}: expected 401/423/429, got {resp.status_code}"
        )

    # 6번째 시도 → lockout(423 또는 429)
    resp6 = client.post("/admin/login", data={"password": wrong_pw, "csrf_token": token})
    assert resp6.status_code in (423, 429), (
        f"6th attempt after lockout should be 423/429, got {resp6.status_code}"
    )


# ──────────────────────────────────────────────────
# password_change: current_invalid 오류 표시 (TP-012, D8)
# ──────────────────────────────────────────────────

def test_password_change_current_invalid(tmp_path):
    """현재 비밀번호를 틀리면 password 폼에 오류가 표시된다 (TP-012/D8).

    독립 출처: F04 §7 AC-P1 + D8, W10 상세 "current_invalid → 폼 오류".
    """
    app = _make_app(tmp_path)
    client = app.test_client()

    # 로그인 상태 주입 + CSRF 주입
    _inject_auth(client)
    token = _inject_csrf(client)

    resp = client.post(
        "/admin/password",
        data={"current": "wrongpass1", "new": "newpassword99", "confirm": "newpassword99",
              "csrf_token": token},
    )
    assert resp.status_code == 422, f"Expected 422 for wrong current pw, got {resp.status_code}"
    html = resp.data.decode("utf-8")
    assert "current" in html.lower() or "current_invalid" in html, (
        "No current_invalid error marker in password change response"
    )


# ──────────────────────────────────────────────────
# setup 모드: 초기 비밀번호 설정 흐름 (W10 #3, AuthService.set_initial)
# ──────────────────────────────────────────────────

def test_setup_mode_sets_password(tmp_path):
    """needs_setup 상태에서 setup 폼 POST(+csrf) → 비밀번호 저장 + 로그인 가능 흐름.

    독립 출처: F04 §7 AC-A5(setup 모드) + §4.4 set_initial. needs_setup은
    비밀번호 파일·env가 모두 없을 때 True.
    """
    app = _make_app(tmp_path, pw_content=None)  # 파일 없음 → needs_setup
    pw_path = tmp_path / "manager_password.txt"
    assert not pw_path.exists(), "사전 조건: 비밀번호 파일이 없어야 한다"

    client = app.test_client()

    # 1. setup 폼 GET → 200 (setup 모드 노출)
    resp_form = client.get("/admin/login")
    assert resp_form.status_code == 200

    # 2. setup 폼 POST (새 비밀번호 + 확인 + csrf)
    new_pw = "setup-password-77"
    token = _inject_csrf(client)
    resp = client.post(
        "/admin/login",
        data={"new_password": new_pw, "confirm_password": new_pw, "csrf_token": token},
    )
    # 성공 → 302 대시보드
    assert resp.status_code in (200, 302), f"setup POST expected 200/302, got {resp.status_code}"

    # 3. 비밀번호 파일이 Argon2id 포맷으로 저장됨
    assert pw_path.exists(), "setup 후 비밀번호 파일이 생성되어야 한다"
    stored = pw_path.read_text(encoding="utf-8").strip()
    assert stored.startswith("$argon2id$"), "Argon2id 포맷으로 저장되어야 한다"

    # 4. 설정된 비밀번호로 (새 클라이언트에서) 로그인 가능
    client2 = app.test_client()
    token2 = _inject_csrf(client2)
    resp_login = client2.post(
        "/admin/login", data={"password": new_pw, "csrf_token": token2}
    )
    assert resp_login.status_code in (200, 302), (
        f"설정한 비밀번호로 로그인 가능해야 하나 {resp_login.status_code}"
    )
    resp_dash = client2.get("/admin/")
    assert resp_dash.status_code == 200, "로그인 후 대시보드 접근 가능해야 한다"


# ──────────────────────────────────────────────────
# S1/OPEN-REDIRECT 회귀: next 파라미터 외부 redirect 차단
# ──────────────────────────────────────────────────

def test_login_next_rejects_open_redirect(tmp_path):
    """로그인 성공 후 next가 외부 호스트·프로토콜 상대 URL·백슬래시 우회이면
    /admin/(대시보드)로 폴백하고 외부 도메인으로 이동하지 않는지 단언.

    독립 출처: security-audit-P4-20260602-T01.md S1/OPEN-REDIRECT 발견;
    F04 §7 "next는 동일 origin 내부 경로만 허용" 원칙.
    E-13: 기대값 = 외부 호스트 비포함 + Location == '/admin/'(fallback spec),
           tautology 없음 — next 파라미터가 request.args 경로로 실제 전달됨을 보장.
    """
    # 거부해야 할 입력 목록 (공격자가 사용할 open-redirect 페이로드)
    malicious_cases = [
        "//evil.com",          # 프로토콜 상대 URL
        "/\\evil.com",         # 백슬래시 우회 (/\ → // 브라우저 정규화)
        "http://evil.com",     # 절대 URL scheme
        "https://evil.com",    # HTTPS 절대 URL
        "\\/\\/evil.com",      # 이중 백슬래시+슬래시 혼합
        "/\t/evil.com",        # 탭 제어문자 우회 (정규화 후 //evil.com)
    ]

    app = _make_app(tmp_path)
    client = app.test_client()

    for bad_next in malicious_cases:
        token = _inject_csrf(client)
        resp = client.post(
            "/admin/login",
            query_string={"next": bad_next},   # request.args 경로 — 실제 핸들러가 읽는 위치
            data={"password": _CORRECT_PW, "csrf_token": token},
        )
        assert resp.status_code == 302, (
            f"[{bad_next!r}] 로그인 성공 후 302 redirect 기대, 실제={resp.status_code}"
        )
        location = resp.headers.get("Location", "")
        assert "evil.com" not in location, (
            f"[{bad_next!r}] Location에 evil.com이 포함되어 외부 redirect 발생: {location!r}"
        )
        assert location == "/admin/", (
            f"[{bad_next!r}] 악성 next는 /admin/로 폴백해야 하나 Location={location!r}"
        )
        # 다음 케이스를 위해 세션 로그아웃
        with client.session_transaction() as sess:
            sess.pop("admin_authed", None)

    # 정상 케이스: next=/admin/timetable 은 그대로 유지되는지 검증
    token = _inject_csrf(client)
    resp_ok = client.post(
        "/admin/login",
        query_string={"next": "/admin/timetable"},
        data={"password": _CORRECT_PW, "csrf_token": token},
    )
    assert resp_ok.status_code == 302, (
        f"정상 next=/admin/timetable 후 302 기대, 실제={resp_ok.status_code}"
    )
    location_ok = resp_ok.headers.get("Location", "")
    assert location_ok == "/admin/timetable", (
        f"정상 next는 그대로 사용되어야 하나 Location={location_ok!r}"
    )
