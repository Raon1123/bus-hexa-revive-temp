"""Application configuration and secret loading.

Implements the ADR-005 precedence: an environment variable always wins, then a
file under ``secret/`` is used as a fallback (preserving compatibility with the
legacy ``secret/key.txt`` and ``secret/db.yaml``). The required secrets are the
API key and the database URL; if neither source provides them, loading fails
loudly with :class:`ConfigError` rather than starting with a broken config.
"""

from __future__ import annotations

import logging
import os
import secrets
from dataclasses import dataclass
from datetime import tzinfo
from pathlib import Path

import yaml

from bushexa.time_utils import KST  # ADR-008: KST 단일 출처

log = logging.getLogger("bushexa")


class ConfigError(RuntimeError):
    """Raised when a required secret is missing from both env and ``secret/``."""


def _read_text(path: Path) -> str | None:
    """Return the stripped contents of *path*, or ``None`` if absent/empty."""
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return text or None


def _migrate_manager_password(old_path: Path, new_path: Path) -> None:
    """레거시 ``secret/manager_password.txt`` → ``data/manager_password.txt`` 1회 이전.

    새 경로 파일이 이미 있으면 아무것도 하지 않는다(이전 완료). 구 경로만 있으면 내용을
    복사하고 권한 0600을 유지한다(S8). 구 경로가 :ro 마운트라 삭제는 시도하지 않는다.
    """
    if new_path.exists() or not old_path.exists():
        return
    try:
        content = old_path.read_text(encoding="utf-8")
        new_path.parent.mkdir(parents=True, exist_ok=True)
        new_path.write_text(content, encoding="utf-8")
        new_path.chmod(0o600)
        log.info("manager_password를 %s → %s 로 이전했습니다.", old_path, new_path)
    except OSError as exc:  # pragma: no cover - 환경 의존
        log.warning("manager_password 이전 실패(%s → %s): %s", old_path, new_path, exc)


def _db_url_from_yaml(path: Path) -> str | None:
    """Build a ``postgresql://`` URL from the legacy ``secret/db.yaml`` keys."""
    if not path.exists():
        return None
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    required = ("user", "password", "host", "port", "dbname")
    if not all(key in data for key in required):
        return None
    return (
        f"postgresql://{data['user']}:{data['password']}"
        f"@{data['host']}:{data['port']}/{data['dbname']}"
    )


@dataclass(frozen=True)
class AppConfig:
    """Resolved runtime configuration. Construct via :meth:`from_env`."""

    api_key: str
    database_url: str
    session_secret: str
    manager_password_path: Path
    data_dir: Path
    tz: tzinfo
    log_level: str
    log_dir: Path = Path("logs")
    session_cookie_secure: bool = False

    @classmethod
    def from_env(
        cls,
        *,
        environ: dict | None = None,
        secret_dir: Path | str = "secret",
        data_dir: Path | str = "data",
    ) -> "AppConfig":
        """Resolve configuration from environment and ``secret/`` fallbacks.

        When *environ* is ``None`` (real runtime) a ``.env`` file is loaded into
        ``os.environ`` first; when an explicit dict is passed (tests) no dotenv
        loading happens so the test stays hermetic.
        """
        if environ is None:
            try:
                from dotenv import load_dotenv

                load_dotenv()
            except ImportError:  # python-dotenv optional at import time
                pass
            environ = os.environ

        secret_dir = Path(secret_dir)
        data_dir = Path(data_dir)

        api_key = environ.get("BUSHEXA_API_KEY") or _read_text(secret_dir / "key.txt")
        if not api_key:
            raise ConfigError(
                "API key missing: set BUSHEXA_API_KEY or create secret/key.txt"
            )

        database_url = environ.get("DATABASE_URL") or _db_url_from_yaml(
            secret_dir / "db.yaml"
        )
        if not database_url:
            raise ConfigError(
                "Database URL missing: set DATABASE_URL or create secret/db.yaml"
            )

        session_secret = environ.get("BUSHEXA_SESSION_SECRET")
        if not session_secret:
            session_secret = secrets.token_hex(32)
            log.warning(
                "BUSHEXA_SESSION_SECRET not set; using an ephemeral key "
                "(admin sessions reset on every restart)."
            )

        session_cookie_secure = (
            environ.get("BUSHEXA_SESSION_COOKIE_SECURE", "").lower() in {"1", "true", "yes", "on"}
        )

        # 비밀번호 해시는 data_dir에 둔다(secret/는 compose에서 :ro 마운트 → 쓰기 불가로
        # 초기설정/변경 POST가 실패하던 문제). API 키 등 읽기전용 시크릿과 분리.
        manager_password_path = data_dir / "manager_password.txt"
        _migrate_manager_password(secret_dir / "manager_password.txt", manager_password_path)

        return cls(
            api_key=api_key,
            database_url=database_url,
            session_secret=session_secret,
            manager_password_path=manager_password_path,
            data_dir=data_dir,
            tz=KST,
            log_level=environ.get("BUSHEXA_LOG_LEVEL", "INFO"),
            log_dir=Path(environ.get("BUSHEXA_LOG_DIR", "logs")),
            session_cookie_secure=session_cookie_secure,
        )
