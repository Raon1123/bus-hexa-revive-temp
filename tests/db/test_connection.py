"""W4 db/connection 검증. WAL은 파일 DB에서만 켜지므로 :memory:가 아닌 tmp 파일을 쓴다."""
from __future__ import annotations

import sys

import pytest

from bushexa.db.connection import create_connection, placeholder


def test_sqlite_memory_connect():
    """sqlite:///:memory: DSN으로 연결 후 SELECT 1이 1을 반환하는지."""
    conn = create_connection("sqlite:///:memory:")
    try:
        assert conn.execute("SELECT 1").fetchone()[0] == 1
    finally:
        conn.close()


def test_wal_enabled(tmp_path):
    """파일 SQLite 연결 후 PRAGMA journal_mode가 'wal'인지(단일 writer+다중 reader 동시성).

    SQLite는 :memory: DB에서 WAL을 거부하므로 반드시 파일 경로로 검증한다.
    """
    dsn = f"sqlite:///{tmp_path / 'x.db'}"
    conn = create_connection(dsn)
    try:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert str(mode).lower() == "wal"
    finally:
        conn.close()


def test_placeholder_by_backend():
    """[executor-added] placeholder가 SQLite='?', PostgreSQL='%s'를 돌려주는지(W4 step4)."""
    assert placeholder("sqlite:///:memory:") == "?"
    assert placeholder("postgresql://u:p@h:5432/db") == "%s"


def test_postgres_dsn_without_driver_raises(monkeypatch):
    """psycopg2를 None으로 막은 뒤 postgresql DSN을 주면 안내 메시지를 가진 ImportError가 나는지."""
    monkeypatch.setitem(sys.modules, "psycopg2", None)
    with pytest.raises(ImportError):
        create_connection("postgresql://u:p@h:5432/db")
