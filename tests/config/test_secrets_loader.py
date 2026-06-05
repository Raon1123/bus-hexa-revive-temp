"""Unit tests for AppConfig.from_env secret precedence (P0 / W4).

Each test pins one rule of the ADR-005 precedence model: env beats file, file is
the fallback, and a missing required secret fails loudly.
"""

from __future__ import annotations

import pytest

from bushexa.config import AppConfig, ConfigError


def _write(path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def test_env_api_key_overrides_secret_file(tmp_path):
    """When BUSHEXA_API_KEY is in the environment, it wins over secret/key.txt:
    given key.txt='FILEKEY' but env BUSHEXA_API_KEY='ENVKEY', the resolved
    api_key must be 'ENVKEY'."""
    _write(tmp_path / "key.txt", "FILEKEY")
    cfg = AppConfig.from_env(
        environ={"BUSHEXA_API_KEY": "ENVKEY", "DATABASE_URL": "sqlite:///x.db"},
        secret_dir=tmp_path,
    )
    assert cfg.api_key == "ENVKEY"


def test_api_key_falls_back_to_secret_file(tmp_path):
    """When BUSHEXA_API_KEY is absent from the env, the loader falls back to
    secret/key.txt: with no env key but key.txt='FILEKEY', api_key=='FILEKEY'."""
    _write(tmp_path / "key.txt", "FILEKEY")
    cfg = AppConfig.from_env(
        environ={"DATABASE_URL": "sqlite:///x.db"},
        secret_dir=tmp_path,
    )
    assert cfg.api_key == "FILEKEY"


def test_missing_api_key_raises(tmp_path):
    """With neither BUSHEXA_API_KEY nor secret/key.txt present, from_env must
    raise ConfigError rather than return a config with an empty key."""
    with pytest.raises(ConfigError):
        AppConfig.from_env(
            environ={"DATABASE_URL": "sqlite:///x.db"},
            secret_dir=tmp_path,
        )


def test_missing_database_url_raises(tmp_path):
    """With an API key available but no DATABASE_URL and no secret/db.yaml,
    from_env must raise ConfigError (database URL is required)."""
    _write(tmp_path / "key.txt", "FILEKEY")
    with pytest.raises(ConfigError):
        AppConfig.from_env(environ={}, secret_dir=tmp_path)


def test_database_url_built_from_db_yaml(tmp_path):
    """When DATABASE_URL is absent, the loader builds a postgresql:// URL from
    the legacy secret/db.yaml fields (user/password/host/port/dbname)."""
    _write(tmp_path / "key.txt", "FILEKEY")
    _write(
        tmp_path / "db.yaml",
        "dbname: buslog\nuser: bushexa\npassword: pw\nhost: 10.0.0.1\nport: 15432\n",
    )
    cfg = AppConfig.from_env(environ={}, secret_dir=tmp_path)
    assert cfg.database_url == "postgresql://bushexa:pw@10.0.0.1:15432/buslog"


def test_ephemeral_session_secret_when_unset(tmp_path):
    """When BUSHEXA_SESSION_SECRET is not provided, the loader generates a
    non-empty ephemeral secret (so the app still runs, with a logged warning)."""
    _write(tmp_path / "key.txt", "FILEKEY")
    cfg = AppConfig.from_env(
        environ={"DATABASE_URL": "sqlite:///x.db"},
        secret_dir=tmp_path,
    )
    assert isinstance(cfg.session_secret, str) and len(cfg.session_secret) >= 16
