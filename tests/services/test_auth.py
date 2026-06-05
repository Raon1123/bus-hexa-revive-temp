"""W9 AuthService 테스트 (E-13 준수).

기대값은 구현과 독립된 출처(표준 hashlib)에서 직접 계산.
구현 출력을 베껴 기대값으로 쓰는 것은 금지.
"""
from __future__ import annotations

import hashlib
import os
import stat

import pytest

from bushexa.services.auth import AuthService, Result


# ──────────────────────────────────────────────────────────────────────────
# 헬퍼: 테스트 전용 PBKDF2 해시 생성 (구현과 독립)
# ──────────────────────────────────────────────────────────────────────────

def _make_pbkdf2_stored(password: str, salt: bytes, iterations: int = 200_000) -> str:
    """알려진 파라미터로 PBKDF2 해시 문자열 생성 (테스트용 독립 출처)."""
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${dk.hex()}"


# ──────────────────────────────────────────────────────────────────────────
# AC-1: PBKDF2 검증 정답/오답 정확 구분
# ──────────────────────────────────────────────────────────────────────────

def test_verify_pbkdf2(tmp_path):
    """알려진 비밀번호를 직접 해시해 저장 후 정답/오답 구분 검증 (E-13)."""
    salt = bytes.fromhex("0102030405060708090a0b0c0d0e0f10")
    correct_password = "correct-horse-battery"
    wrong_password = "wrong-password-xx"

    # 테스트가 독립적으로 계산한 저장 해시
    stored = _make_pbkdf2_stored(correct_password, salt)
    secret_path = tmp_path / "manager_password.txt"
    secret_path.write_text(stored, encoding="utf-8")

    svc = AuthService(secret_path=secret_path, env_password=None)

    assert svc.verify(correct_password) is True, "정답 비밀번호는 True여야 함"
    assert svc.verify(wrong_password) is False, "오답 비밀번호는 False여야 함"
    assert svc.verify("") is False, "빈 문자열은 False여야 함"


# ──────────────────────────────────────────────────────────────────────────
# AC-2: change_password가 현재 비밀번호 불일치 시 실패 (D8 봉인)
# ──────────────────────────────────────────────────────────────────────────

def test_change_requires_current(tmp_path):
    """현재 비밀번호를 틀리게 주면 error('current_invalid') 반환."""
    salt = os.urandom(16)
    correct = "correct-password-123"
    stored = _make_pbkdf2_stored(correct, salt)
    secret_path = tmp_path / "manager_password.txt"
    secret_path.write_text(stored, encoding="utf-8")

    svc = AuthService(secret_path=secret_path, env_password=None)

    result = svc.change_password("wrong-current-pass", "new-password-xyz")

    assert result.success is False
    assert result.code == "current_invalid"
    # 파일은 변경되지 않아야 함
    assert secret_path.read_text(encoding="utf-8").strip() == stored


# ──────────────────────────────────────────────────────────────────────────
# Legacy 평문 → PBKDF2 마이그레이션
# ──────────────────────────────────────────────────────────────────────────

def test_legacy_plain_migrates(tmp_path):
    """legacy 평문 파일로 인증 후 비밀번호 변경 시 파일이 Argon2id 포맷으로 갱신됨."""
    legacy_password = "plaintext-legacy"
    secret_path = tmp_path / "manager_password.txt"
    secret_path.write_text(legacy_password, encoding="utf-8")

    svc = AuthService(secret_path=secret_path, env_password=None)

    # legacy 평문 인증 가능 확인
    assert svc.verify(legacy_password) is True

    # 비밀번호 변경
    new_password = "new-pbkdf2-password"
    result = svc.change_password(legacy_password, new_password)

    assert result.success is True, f"변경 실패: {result.code}"

    # 파일이 Argon2id 포맷으로 바뀌었는지 확인
    updated = secret_path.read_text(encoding="utf-8").strip()
    assert updated.startswith("$argon2id$"), "Argon2id 포맷이어야 함"

    # 새 비밀번호로 인증 가능
    assert svc.verify(new_password) is True
    # 이전 비밀번호로는 인증 불가
    assert svc.verify(legacy_password) is False


# ──────────────────────────────────────────────────────────────────────────
# needs_setup
# ──────────────────────────────────────────────────────────────────────────

def test_needs_setup(tmp_path):
    """파일도 env도 없으면 needs_setup=True."""
    secret_path = tmp_path / "manager_password.txt"
    # 파일 미생성 상태

    svc = AuthService(secret_path=secret_path, env_password=None)

    assert svc.needs_setup is True


def test_needs_setup_false_when_file_exists(tmp_path):
    """파일이 있으면 needs_setup=False."""
    salt = os.urandom(16)
    stored = _make_pbkdf2_stored("somepassword", salt)
    secret_path = tmp_path / "manager_password.txt"
    secret_path.write_text(stored, encoding="utf-8")

    svc = AuthService(secret_path=secret_path, env_password=None)

    assert svc.needs_setup is False


def test_needs_setup_false_with_env(tmp_path):
    """env_password가 있으면 파일 없어도 needs_setup=False."""
    secret_path = tmp_path / "nonexistent.txt"
    svc = AuthService(secret_path=secret_path, env_password="env-secret-pw")

    assert svc.needs_setup is False


# ──────────────────────────────────────────────────────────────────────────
# env_password 우선 검증
# ──────────────────────────────────────────────────────────────────────────

def test_verify_env_password(tmp_path):
    """env_password가 설정되면 파일 없이도 인증 가능."""
    secret_path = tmp_path / "nonexistent.txt"
    env_pw = "env-only-password-123"

    svc = AuthService(secret_path=secret_path, env_password=env_pw)

    assert svc.verify(env_pw) is True
    assert svc.verify("wrong") is False


# ──────────────────────────────────────────────────────────────────────────
# too_short 검증
# ──────────────────────────────────────────────────────────────────────────

def test_change_too_short(tmp_path):
    """신규 비밀번호가 8자 미만이면 error('too_short') 반환."""
    salt = os.urandom(16)
    current = "correct-current-123"
    stored = _make_pbkdf2_stored(current, salt)
    secret_path = tmp_path / "manager_password.txt"
    secret_path.write_text(stored, encoding="utf-8")

    svc = AuthService(secret_path=secret_path, env_password=None)

    result = svc.change_password(current, "short")  # 5자

    assert result.success is False
    assert result.code == "too_short"


# ──────────────────────────────────────────────────────────────────────────
# 파일 권한 0600
# ──────────────────────────────────────────────────────────────────────────

def test_change_sets_0600_permissions(tmp_path):
    """비밀번호 변경 후 파일 권한이 0600이어야 함 (S8)."""
    salt = os.urandom(16)
    current = "current-password-abc"
    stored = _make_pbkdf2_stored(current, salt)
    secret_path = tmp_path / "manager_password.txt"
    secret_path.write_text(stored, encoding="utf-8")

    svc = AuthService(secret_path=secret_path, env_password=None)
    result = svc.change_password(current, "new-password-xyz")

    assert result.success is True
    mode = oct(secret_path.stat().st_mode & 0o777)
    assert mode == "0o600", f"파일 권한이 0600이어야 하나 {mode}"


# ──────────────────────────────────────────────────────────────────────────
# set_initial (F04 §4.4) — setup 모드 초기 비밀번호 설정
# ──────────────────────────────────────────────────────────────────────────

def test_set_initial_when_needs_setup(tmp_path):
    """needs_setup 상태에서 set_initial → 성공 + Argon2id 포맷 + 0600 권한.

    독립 출처: F04 §4.4 set_initial 계약, argon2-cffi PHC 포맷 prefix.
    """
    secret_path = tmp_path / "manager_password.txt"  # 파일 없음 → needs_setup
    svc = AuthService(secret_path=secret_path, env_password=None)
    assert svc.needs_setup is True

    result = svc.set_initial("new-initial-pw-123")

    assert result.success is True
    stored = secret_path.read_text(encoding="utf-8").strip()
    # Argon2id 포맷이어야 한다 (평문 저장 금지)
    assert stored.startswith("$argon2id$"), f"Argon2id 포맷이어야 하나 {stored[:20]!r}"
    # 설정한 비밀번호로 검증 통과
    assert svc.verify("new-initial-pw-123") is True
    # 파일 권한 0600
    mode = oct(secret_path.stat().st_mode & 0o777)
    assert mode == "0o600", f"파일 권한이 0600이어야 하나 {mode}"


def test_set_initial_refuses_when_already_set(tmp_path):
    """비밀번호가 이미 존재하면 set_initial → error('already_set') + 파일 불변.

    독립 출처: F04 §4.4 — 인증 없는 재설정 방지(방어심층).
    """
    salt = os.urandom(16)
    existing = "existing-password-99"
    stored_before = _make_pbkdf2_stored(existing, salt)
    secret_path = tmp_path / "manager_password.txt"
    secret_path.write_text(stored_before, encoding="utf-8")

    svc = AuthService(secret_path=secret_path, env_password=None)
    assert svc.needs_setup is False

    result = svc.set_initial("attacker-new-pw-123")

    assert result.success is False
    assert result.code == "already_set"
    # 파일 내용이 변하지 않아야 한다
    assert secret_path.read_text(encoding="utf-8") == stored_before
    # 기존 비밀번호는 여전히 유효
    assert svc.verify(existing) is True


def test_set_initial_too_short(tmp_path):
    """setup 상태에서 8자 미만 신규 비밀번호 → error('too_short') + 파일 미생성."""
    secret_path = tmp_path / "manager_password.txt"
    svc = AuthService(secret_path=secret_path, env_password=None)

    result = svc.set_initial("short")  # 5자

    assert result.success is False
    assert result.code == "too_short"
    assert not secret_path.exists(), "거부 시 비밀번호 파일이 생성되면 안 됨"


# ──────────────────────────────────────────────────────────────────────────
# S8 regression: secret 파일 0600 권한 (stat.S_IMODE 형식, P5 보안 게이트)
# ──────────────────────────────────────────────────────────────────────────

def test_set_initial_secret_file_is_0600(tmp_path):
    """secret 파일은 0600으로 생성되어 그룹/타인이 읽을 수 없어야 한다 (S8).

    stat.S_IMODE(os.stat(path).st_mode) 로 퍼미션 비트만 추출해 0o600과 비교한다.
    """
    secret_path = tmp_path / "manager_password.txt"
    svc = AuthService(secret_path=secret_path, env_password=None)

    result = svc.set_initial("new-initial-pw-s8")

    assert result.success is True
    assert stat.S_IMODE(os.stat(secret_path).st_mode) == 0o600, (
        f"secret 파일 권한이 0600이어야 하나 {oct(stat.S_IMODE(os.stat(secret_path).st_mode))}"
    )


def test_change_password_secret_file_is_0600(tmp_path):
    """secret 파일은 0600으로 변경되어 그룹/타인이 읽을 수 없어야 한다 (S8).

    stat.S_IMODE(os.stat(path).st_mode) 로 퍼미션 비트만 추출해 0o600과 비교한다.
    """
    salt = os.urandom(16)
    current = "current-password-s8"
    stored = _make_pbkdf2_stored(current, salt)
    secret_path = tmp_path / "manager_password.txt"
    secret_path.write_text(stored, encoding="utf-8")

    svc = AuthService(secret_path=secret_path, env_password=None)
    result = svc.change_password(current, "new-password-s8!")

    assert result.success is True
    assert stat.S_IMODE(os.stat(secret_path).st_mode) == 0o600, (
        f"secret 파일 권한이 0600이어야 하나 {oct(stat.S_IMODE(os.stat(secret_path).st_mode))}"
    )


# ──────────────────────────────────────────────────────────────────────────
# 해시 강화: 로그인 성공 시 구형 해시(PBKDF2) → Argon2id 자동 재해시
# ──────────────────────────────────────────────────────────────────────────

def test_login_rehashes_pbkdf2_to_argon2id(tmp_path):
    """PBKDF2 저장본으로 로그인 성공 시 파일이 Argon2id로 재해시되고, 이후에도 인증 가능."""
    salt = os.urandom(16)
    password = "rehash-me-please-1"
    secret_path = tmp_path / "manager_password.txt"
    secret_path.write_text(_make_pbkdf2_stored(password, salt), encoding="utf-8")

    svc = AuthService(secret_path=secret_path, env_password=None)

    # 검증(=로그인) 성공
    assert svc.verify(password) is True
    # 파일이 Argon2id로 재해시됨 (점진 마이그레이션)
    rehashed = secret_path.read_text(encoding="utf-8").strip()
    assert rehashed.startswith("$argon2id$"), f"재해시 후 Argon2id여야 하나 {rehashed[:20]!r}"
    # 재해시 후에도 동일 비밀번호로 인증 가능
    assert svc.verify(password) is True
    # 권한 0600 유지
    assert stat.S_IMODE(os.stat(secret_path).st_mode) == 0o600
