"""W7c H10 회귀: BusLogRepo가 context manager로 안전하게 닫히는지(__del__ 의존 제거)."""
from __future__ import annotations

import sqlite3

import pytest

from bushexa.db.connection import create_connection
from bushexa.db.repo import BusLogRepo, LogRow
from bushexa.db.schema import create_schema


def _fresh_repo_conn():
    conn = create_connection("sqlite:///:memory:")
    create_schema(conn)
    return BusLogRepo(conn), conn


def test_close_order_safe():
    """BusLogRepo를 with로 열고 블록 종료 시 connection이 안전하게 닫혀 예외가 없는지 검증한다 — H10 회귀."""
    repo, conn = _fresh_repo_conn()
    with repo as r:
        r.insert_log(idx="20260601_08:00:00", stop_id="999000149",
                     route_id="195000177", vehicle_no="veh-A", stop_name="명촌")
        assert r.count() == 1
    # 블록 종료 후 연결이 닫혀 추가 쿼리는 실패해야 한다(닫혔음을 입증).
    with pytest.raises(sqlite3.ProgrammingError):
        conn.execute("SELECT 1")


def test_exception_in_block_still_closes():
    """with 블록 내부 예외가 발생해도 연결이 닫히고, 예외는 삼켜지지 않고 전파되는지 검증한다."""
    repo, conn = _fresh_repo_conn()
    with pytest.raises(ValueError):
        with repo:
            repo.insert_batch([LogRow(idx="20260601_08:00:00", stop_id="999000149",
                                      route_id="195000177", vehicle_no="veh-A")])
            raise ValueError("boom")
    with pytest.raises(sqlite3.ProgrammingError):
        conn.execute("SELECT 1")  # 예외 경로에서도 닫혔다
