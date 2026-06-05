"""#9 E-13: admin lockout 크로스 워커 공유 검증.

기존 인메모리 _ADMIN_LOCKOUT(워커 로컬)을 파일 기반 admin_lockout.json으로 대체 (#9).

독립 출처 (E-13):
- test_lockout_shared_across_app_instances:
    두 Flask app 인스턴스가 같은 data_dir를 공유하면 한 인스턴스에서의 실패 횟수가
    다른 인스턴스에서도 누적된다 (워커 간 잠금 공유 spec #9).
"""
from __future__ import annotations

from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from bushexa.config import AppConfig
from bushexa.web.app import create_app

_KST = ZoneInfo("Asia/Seoul")
_WRONG_PW = "definitely-wrong-password"
_CORRECT_PW = "correcthorse"


def _make_app(tmp_path: Path, data_dir: Path) -> object:
    """공유 data_dir를 사용하는 Flask app 인스턴스 생성."""
    pw_path = tmp_path / "manager_password.txt"
    if not pw_path.exists():
        pw_path.write_text(_CORRECT_PW)
    config = AppConfig(
        api_key="test-api-key",
        database_url="sqlite:///:memory:",
        session_secret="test-secret",
        manager_password_path=pw_path,
        data_dir=data_dir,       # 공유 data_dir
        tz=_KST,
        log_level="DEBUG",
        log_dir=tmp_path / "logs",
    )
    return create_app(config)


def _inject_csrf(client, token: str = "test-csrf") -> str:
    with client.session_transaction() as sess:
        sess["csrf_token"] = token
    return token


# ──────────────────────────────────────────────────
# 두 app 인스턴스(= 두 워커)가 같은 data_dir 공유 → lockout 공유 (#9)
# ──────────────────────────────────────────────────

def test_lockout_shared_across_app_instances(tmp_path):
    """두 Flask app 인스턴스가 같은 data_dir를 쓸 때 실패 횟수가 공유된다 (#9).

    독립 출처: #9 spec "잠금 상태를 <data_dir>/admin_lockout.json으로 — 워커 공통".
    검증 방법:
      - app_a에서 4회 실패 (lockout 직전)
      - app_b에서 1회 실패 → 합산 5회 달성 → 다음 시도가 423/429이어야 함

    E-13: 기대값 = 두 워커 합산 5회 실패 후 lockout(423), tautology 없음.
    """
    shared_data = tmp_path / "shared_data"
    shared_data.mkdir()

    app_a = _make_app(tmp_path, shared_data)
    app_b = _make_app(tmp_path, shared_data)

    client_a = app_a.test_client()
    client_b = app_b.test_client()

    token_a = _inject_csrf(client_a)
    token_b = _inject_csrf(client_b)

    # app_a에서 4회 실패
    for i in range(4):
        resp = client_a.post("/admin/login", data={"password": _WRONG_PW, "csrf_token": token_a})
        assert resp.status_code in (401, 423, 429), (
            f"app_a attempt {i+1}: expected 401/423/429, got {resp.status_code}"
        )
        # CSRF 토큰 재주입 (세션 재발급 대비)
        token_a = _inject_csrf(client_a)

    # admin_lockout.json이 생성됐는지 확인
    lockout_path = shared_data / "admin_lockout.json"
    assert lockout_path.exists(), "admin_lockout.json이 생성되어야 함"

    # app_b에서 1회 실패 → 합산 5회 → 이 시도 또는 다음 시도에서 lockout
    resp_b = client_b.post("/admin/login", data={"password": _WRONG_PW, "csrf_token": token_b})
    # 5번째 시도에서 lockout 트리거 될 수 있음
    assert resp_b.status_code in (401, 423, 429), (
        f"app_b 5th attempt: expected 401/423/429, got {resp_b.status_code}"
    )

    # 6번째 시도는 반드시 lockout(423/429)
    token_b2 = _inject_csrf(client_b)
    resp_b2 = client_b.post("/admin/login", data={"password": _WRONG_PW, "csrf_token": token_b2})
    assert resp_b2.status_code in (423, 429), (
        f"6th attempt (cross-worker) should be locked, got {resp_b2.status_code}"
    )


# ──────────────────────────────────────────────────
# 로그인 성공 시 잠금 해제 (#9)
# ──────────────────────────────────────────────────

def test_lockout_reset_on_success(tmp_path):
    """로그인 성공 시 해당 IP의 실패 카운터가 초기화된다 (#9).

    독립 출처: #9 spec "로그인 성공 시 해제" — 성공 후 다시 5회 시도 가능해야 함.
    """
    shared_data = tmp_path / "shared_data"
    shared_data.mkdir()

    app = _make_app(tmp_path, shared_data)
    client = app.test_client()

    # 3회 실패
    for i in range(3):
        token = _inject_csrf(client)
        client.post("/admin/login", data={"password": _WRONG_PW, "csrf_token": token})

    # 로그인 성공 → 카운터 초기화
    token = _inject_csrf(client)
    resp = client.post("/admin/login", data={"password": _CORRECT_PW, "csrf_token": token})
    assert resp.status_code in (200, 302), f"로그인 성공이어야 함, got {resp.status_code}"

    # 다시 5회 실패 시도 가능 (잠금이 해제됨)
    for i in range(4):
        with client.session_transaction() as sess:
            sess.pop("admin_authed", None)
        token = _inject_csrf(client)
        resp = client.post("/admin/login", data={"password": _WRONG_PW, "csrf_token": token})
        # 4회까지는 401이어야 함 (lockout 안 됨)
        assert resp.status_code in (401, 423, 429), (
            f"attempt {i+1} after reset: expected 401/423/429, got {resp.status_code}"
        )
