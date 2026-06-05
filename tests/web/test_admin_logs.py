"""W16 테스트: admin 로그 뷰어 (F04 §4.6, TP-015, AC-1/AC-2).

E-13 준수: 기대값은 구현 독립 출처에서 온다.
- test_requires_login: W16 AC-1, F04 AC-L1 "비로그인 /admin/logs → 302 /admin/login".
- test_uses_fixed_path: W16 AC-2, F04 AC-L5 "?file=../../secret/key.txt 줘도 고정 경로만 읽음".

보안 근거(S3): GET /admin/logs는 ?file= 파라미터를 무시하고
config.log_dir / "bushexa.log" 고정 경로만 읽는다.
"""
from __future__ import annotations

from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from bushexa.config import AppConfig
from bushexa.web.app import create_app

_KST = ZoneInfo("Asia/Seoul")


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def logs_app(tmp_path):
    """로그 디렉터리가 격리된 Flask app."""
    log_dir = tmp_path / "logs"
    log_dir.mkdir()

    config = AppConfig(
        api_key="test-api-key",
        database_url="sqlite:///:memory:",
        session_secret="test-secret",
        manager_password_path=tmp_path / "manager_password.txt",
        data_dir=tmp_path / "data",
        tz=_KST,
        log_level="DEBUG",
        log_dir=log_dir,
    )
    return create_app(config), log_dir


@pytest.fixture
def client(logs_app):
    app, _ = logs_app
    return app.test_client()


@pytest.fixture
def authed_client(logs_app):
    """로그인 세션이 주입된 test_client."""
    app, log_dir = logs_app
    c = app.test_client()
    with c.session_transaction() as sess:
        sess["admin_authed"] = True
        sess["csrf_token"] = "test-csrf-token"
    return c, log_dir


# ─────────────────────────────────────────────────────────────────────────────
# test_requires_login
# ─────────────────────────────────────────────────────────────────────────────

def test_requires_login(client):
    """비로그인 GET /admin/logs 는 로그인 페이지로 302 리다이렉트된다 (W16 AC-1).

    E-13 근거: F04 AC-L1 "비로그인 접근 → 302 /admin/login" 명세.
    """
    resp = client.get("/admin/logs")
    assert resp.status_code == 302
    assert "/admin/login" in resp.headers["Location"]


# ─────────────────────────────────────────────────────────────────────────────
# test_uses_fixed_path
# ─────────────────────────────────────────────────────────────────────────────

def test_uses_fixed_path(authed_client, tmp_path):
    """?file=../../secret/key.txt 를 줘도 고정 경로(config.log_dir/bushexa.log)만 읽는다.

    E-13 근거: F04 AC-L5 / W16 명세 "경로 파라미터 금지 — 파일은 고정경로" + S3 traversal 차단.

    검증 방법:
    1. secret/key.txt 에 sentinel 문자열을 기록한다.
    2. ?file=../../secret/key.txt 쿼리로 요청한다.
    3. 응답이 200이고 sentinel이 포함되지 않아야 한다 — 고정 경로만 읽음 증명.
    """
    c, log_dir = authed_client

    # 공격자가 읽으려는 파일
    secret_dir = tmp_path / "secret"
    secret_dir.mkdir(exist_ok=True)
    sentinel = "TOP_SECRET_API_KEY_12345"
    (secret_dir / "key.txt").write_text(sentinel)

    # 로그 파일은 비어 있거나 없어도 됨 (빈 목록 반환)
    resp = c.get("/admin/logs?file=../../secret/key.txt")
    assert resp.status_code == 200

    body = resp.data.decode("utf-8")
    # sentinel이 응답에 없어야 한다 (traversal 차단)
    assert sentinel not in body
    # "로그 파일이 아직 없습니다" 또는 빈 테이블이어야 함
    assert "로그 파일" in body or "admin" in body.lower()


# ─────────────────────────────────────────────────────────────────────────────
# test_logs_route_returns_200_with_log_file
# ─────────────────────────────────────────────────────────────────────────────

def test_logs_route_returns_200_with_log_file(authed_client):
    """로그 파일이 있을 때 /admin/logs 가 200을 반환한다."""
    c, log_dir = authed_client

    # 알려진 로그 라인 기록
    log_file = log_dir / "bushexa.log"
    log_file.write_text(
        "2026-06-01T08:00:00+09:00 [bushexa.test] INFO: test message\n",
        encoding="utf-8",
    )

    resp = c.get("/admin/logs")
    assert resp.status_code == 200
    body = resp.data.decode("utf-8")
    assert "test message" in body


# ─────────────────────────────────────────────────────────────────────────────
# test_logs_missing_file_returns_empty_notice
# ─────────────────────────────────────────────────────────────────────────────

def test_logs_missing_file_returns_empty_notice(authed_client):
    """로그 파일이 없을 때 500 대신 200 + '로그 파일이 아직 없습니다' 메시지 (F04 AC-L4)."""
    c, log_dir = authed_client
    # bushexa.log 파일 없이 요청

    resp = c.get("/admin/logs")
    assert resp.status_code == 200
    assert "로그 파일이 아직 없습니다" in resp.data.decode("utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# 이월 2 — 로그 마스킹 회귀테스트 (S7, W16, _mask_secrets)
# ─────────────────────────────────────────────────────────────────────────────
# 독립 출처: S7 "로그/에러 응답에 시크릿·내부경로 누출 0(W16 로그 뷰어는 표출 전 마스킹)"
# 기대값 근거: "시크릿 원문이 응답 본문에 없음" — 구현 독립 출처(S7 명세 직접 인용).
# tautology 없음: 시크릿 원문을 알려진 상수로 정해두고, 그것이 응답에 '없음'을 단언.

_LOG_FORMAT = "2026-06-01T08:00:00+09:00 [bushexa.test] INFO: {message}"


def _write_log_lines(log_dir, lines: list[str]) -> None:
    """log_dir/bushexa.log에 알려진 로그 라인들을 기록한다."""
    log_file = log_dir / "bushexa.log"
    content = "\n".join(
        _LOG_FORMAT.format(message=msg) for msg in lines
    ) + "\n"
    log_file.write_text(content, encoding="utf-8")


def test_masking_password_and_api_key(authed_client):
    """password=<value>와 api_key=<value> 시크릿이 응답 본문에서 마스킹되는지 검증.

    E-13 근거: S7 "로그 뷰어는 표출 전 시크릿 패턴 마스킹", W16 명세.
    기대값 = 시크릿 원문 부재 (구현 독립 출처).
    """
    c, log_dir = authed_client

    secret_password = "hunter2"
    secret_api_key = "ABCDEF123"

    _write_log_lines(log_dir, [
        f"password={secret_password}",
        f"api_key={secret_api_key}",
        "normal log message without secrets",
    ])

    resp = c.get("/admin/logs")
    assert resp.status_code == 200

    body = resp.data.decode("utf-8")
    # 원본 시크릿 값이 응답 본문에 노출되면 안 된다 (S7 마스킹 검증)
    assert secret_password not in body, (
        f"Secret password value {secret_password!r} must not appear in response body "
        f"(S7: 시크릿 마스킹 — 독립 출처: W16 명세)"
    )
    assert secret_api_key not in body, (
        f"Secret api_key value {secret_api_key!r} must not appear in response body "
        f"(S7: 시크릿 마스킹 — 독립 출처: W16 명세)"
    )
    # 마스킹 표시(****)가 있어야 한다
    assert "****" in body, (
        "Masking marker '****' not found in response — masking must replace secret values"
    )


def test_masking_bearer_token(authed_client):
    """Authorization: Bearer <token> 형태 엣지케이스 — 토큰이 응답에서 마스킹되는지 검증.

    E-13 근거: S7 + 이월 2 명세 "Authorization: Bearer <token> 형태 엣지케이스 포함".
    기대값 = 시크릿 원문 부재 (구현 독립 출처).

    Bearer 토큰 회귀: _mask_secrets의 \\S+ 패턴이 'Bearer'에서 멈추면 토큰이 노출된다.
    수정 후 'Authorization: Bearer secrettoken123' → 'Authorization=****'.
    """
    c, log_dir = authed_client

    bearer_token = "secrettoken123"

    _write_log_lines(log_dir, [
        f"Authorization: Bearer {bearer_token}",
        "other normal log line",
    ])

    resp = c.get("/admin/logs")
    assert resp.status_code == 200

    body = resp.data.decode("utf-8")
    # Bearer 토큰 원문이 응답에 없어야 한다 (S7 엣지케이스)
    assert bearer_token not in body, (
        f"Bearer token {bearer_token!r} must not appear in response body "
        f"(S7 Bearer 토큰 마스킹 — 이월 2 엣지케이스)"
    )
    # 마스킹 표시가 있어야 한다
    assert "****" in body, (
        "Masking marker '****' not found in response for Bearer token line"
    )
