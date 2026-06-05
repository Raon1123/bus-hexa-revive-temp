"""W9 — 관리자 인증 서비스 (F04 §4.4).

AuthService: **Argon2id** 해시(신규 저장) + 하위호환 검증(PBKDF2-SHA256 / legacy 평문) +
로그인 시 구형 해시 자동 재해시(rehash) + change_password(D8 봉인).
시크릿 하드코딩 0(S7). 파일 권한 0600(S8).

비밀번호 저장 정책:
    비밀번호는 복호화 불가능한 단방향 해시로만 저장한다(RSA 등 암호화는 부적합). 미국 표준
    NIST SP 800-63B를 따르며, 현재 OWASP 1순위 권장인 **Argon2id**(메모리-하드, GPU/ASIC
    내성)로 저장한다. 기존 PBKDF2/평문 자격증명은 검증만 호환하고, 로그인 성공 시 Argon2id로
    재해시해 점진 마이그레이션한다.

저장 포맷:
    신규: argon2-cffi PHC 문자열  ``$argon2id$v=19$m=...,t=...,p=...$<salt>$<hash>``
    legacy(검증만): ``pbkdf2_sha256$<iterations>$<salt_hex>$<dk_hex>`` 또는 평문
"""
from __future__ import annotations

import hashlib
import logging
import os
import secrets
from dataclasses import dataclass
from pathlib import Path

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from bushexa import fileio

logger = logging.getLogger("bushexa.services.auth")

_ARGON2_PREFIX = "$argon2"
_PBKDF2_PREFIX = "pbkdf2_sha256$"
_ITERATIONS = 200_000

# OWASP Password Storage Cheat Sheet 권장 최소값(m=19MiB, t=2, p=1). 저사양 컨테이너에서도
# 안정적으로 동작하도록 보수적으로 둔다. check_needs_rehash가 파라미터 변경 시 자동 재해시.
_ph = PasswordHasher(time_cost=2, memory_cost=19_456, parallelism=1)
_MIN_PASSWORD_LEN = 8


# ──────────────────────────────────────────────
# Result (F04 §6)
# ──────────────────────────────────────────────

@dataclass(frozen=True)
class Result:
    success: bool
    code: str | None = None  # None when success=True

    @classmethod
    def ok(cls) -> "Result":
        return cls(success=True)

    @classmethod
    def error(cls, code: str) -> "Result":
        return cls(success=False, code=code)


# ──────────────────────────────────────────────
# 내부 해시 헬퍼 (신규 Argon2id, 검증은 하위호환)
# ──────────────────────────────────────────────

def _hash_password(plain: str) -> str:
    """신규 비밀번호 해시 생성 — Argon2id PHC 문자열. 매 호출마다 fresh salt(내부 생성)."""
    return _ph.hash(plain)


def _verify_hash(plain: str, stored: str) -> bool:
    """저장된 해시(Argon2id / legacy PBKDF2 / legacy 평문)와 평문을 비교."""
    try:
        if stored.startswith(_ARGON2_PREFIX):
            try:
                return _ph.verify(stored, plain)
            except (VerifyMismatchError, VerificationError, InvalidHashError):
                return False
        if stored.startswith(_PBKDF2_PREFIX):
            _, iter_str, salt_hex, hash_hex = stored.split("$")
            iterations = int(iter_str)
            salt = bytes.fromhex(salt_hex)
            expected = bytes.fromhex(hash_hex)
            computed = hashlib.pbkdf2_hmac(
                "sha256", plain.encode("utf-8"), salt, iterations
            )
            return secrets.compare_digest(computed, expected)
        # Legacy 평문 비교
        return secrets.compare_digest(plain.encode("utf-8"), stored.encode("utf-8"))
    except Exception:
        return False


def _needs_rehash(stored: str) -> bool:
    """저장된 해시가 현재 정책(Argon2id + 현 파라미터)이 아니면 True → 로그인 시 재해시."""
    if not stored.startswith(_ARGON2_PREFIX):
        return True
    try:
        return _ph.check_needs_rehash(stored)
    except Exception:
        return True


# ──────────────────────────────────────────────
# AuthService
# ──────────────────────────────────────────────

class AuthService:
    """관리자 비밀번호 검증 및 변경.

    Parameters
    ----------
    secret_path:
        비밀번호 해시 파일 경로 (``secret/manager_password.txt``).
    env_password:
        환경변수 MANAGER_PASSWORD 값. None이면 파일만 사용.
    """

    def __init__(self, secret_path: Path, env_password: str | None) -> None:
        self._secret_path = Path(secret_path)
        self._env_pw = env_password  # E-13 grep-safe naming

    # ── 내부 헬퍼 ──────────────────────────────

    def _load_stored(self) -> str | None:
        """파일에서 저장된 비밀번호(해시 또는 legacy 평문)를 읽어 반환. 부재시 None."""
        try:
            return self._secret_path.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            return None
        except OSError as exc:
            logger.warning("secret_path read failed: %s", exc)
            return None

    # ── 공개 API ───────────────────────────────

    def verify(self, plain: str) -> bool:
        """평문 비밀번호를 검증한다.

        검증 순서:
        1. env_password가 설정되어 있으면 먼저 비교.
        2. secret_path 파일(PBKDF2 또는 legacy 평문)과 비교.
        """
        if self._env_pw is not None and _verify_hash(plain, self._env_pw):
            return True
        stored = self._load_stored()
        if stored is None:
            return False
        if not _verify_hash(plain, stored):
            return False
        # 로그인 성공 — 구형 해시(평문/PBKDF2/구 파라미터)면 Argon2id로 재해시 저장(점진 마이그레이션).
        self._maybe_rehash(plain, stored)
        return True

    def _maybe_rehash(self, plain: str, stored: str) -> None:
        """파일 저장 자격증명이 현재 정책이 아니면 Argon2id로 재해시한다(best-effort)."""
        if not _needs_rehash(stored):
            return
        try:
            fileio.atomic_write_text(self._secret_path, _hash_password(plain), logger=logger)
            os.chmod(self._secret_path, 0o600)  # S8
            logger.info("관리자 비밀번호 해시를 Argon2id로 재해시했습니다.")
        except OSError as exc:
            logger.warning("비밀번호 재해시 저장 실패(검증은 정상): %s", exc)

    def change_password(self, current_plain: str, new_plain: str) -> Result:
        """비밀번호를 변경한다.

        D8 봉인: 현재 비밀번호를 먼저 검증. 실패 시 파일 미변경.
        Legacy 평문/PBKDF2 파일이어도 변경 시 Argon2id로 저장.

        Returns
        -------
        Result.ok()                           — 성공
        Result.error('current_invalid')       — 현재 비밀번호 불일치
        Result.error('too_short')             — 신규 비밀번호 8자 미만
        Result.error('io_error')              — 파일 I/O 실패
        """
        if not self.verify(current_plain):
            return Result.error("current_invalid")

        if len(new_plain) < _MIN_PASSWORD_LEN:
            return Result.error("too_short")

        new_hash = _hash_password(new_plain)
        try:
            fileio.atomic_write_text(self._secret_path, new_hash, logger=logger)
            os.chmod(self._secret_path, 0o600)  # S8: 파일 권한 0600
        except OSError as exc:
            logger.error("change_password write failed: %s", exc)
            return Result.error("io_error")

        return Result.ok()

    def set_initial(self, new_plain: str) -> Result:
        """첫 부팅(setup 모드)에서 초기 비밀번호를 설정한다.

        change_password와 달리 '현재 비밀번호'를 요구하지 않지만, 이미 비밀번호가
        존재하면(=not needs_setup) 거부한다(인증 없는 재설정 방지 — 방어심층).

        Returns
        -------
        Result.ok()                       — 성공 (Argon2id 포맷 저장 + 0600)
        Result.error('already_set')       — 이미 비밀번호 존재 (setup 아님)
        Result.error('too_short')         — 신규 비밀번호 8자 미만
        Result.error('io_error')          — 파일 I/O 실패
        """
        if not self.needs_setup:
            return Result.error("already_set")

        if len(new_plain) < _MIN_PASSWORD_LEN:
            return Result.error("too_short")

        new_hash = _hash_password(new_plain)
        try:
            fileio.atomic_write_text(self._secret_path, new_hash, logger=logger)
            os.chmod(self._secret_path, 0o600)  # S8: 파일 권한 0600
        except OSError as exc:
            logger.error("set_initial write failed: %s", exc)
            return Result.error("io_error")

        return Result.ok()

    @property
    def needs_setup(self) -> bool:
        """비밀번호 파일도 env도 설정되지 않으면 True (첫 부팅/setup 모드)."""
        if self._env_pw is not None:
            return False
        return self._load_stored() is None
