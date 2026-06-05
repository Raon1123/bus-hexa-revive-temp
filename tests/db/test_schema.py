"""W5 db/schema 검증. in-memory SQLite에 생성·재생성."""
from __future__ import annotations

from bushexa.db.connection import create_connection
from bushexa.db.schema import create_schema


def test_table_created():
    """create_schema 후 bus_timelog·bus_arrival_cache와 인덱스 3종이 모두 존재하는지."""
    conn = create_connection("sqlite:///:memory:")
    try:
        create_schema(conn)
        names = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table','index')"
            )
        }
    finally:
        conn.close()

    assert "bus_timelog" in names
    assert "bus_arrival_cache" in names  # ADR-010 백업본
    assert {"ix_bus_timelog_route_idx", "ix_bus_timelog_stop_idx",
            "ix_bus_timelog_vehicle"} <= names


def test_idempotent():
    """create_schema를 두 번 호출해도 'table already exists' 없이 통과하는지(재시작 안전)."""
    conn = create_connection("sqlite:///:memory:")
    try:
        create_schema(conn)
        create_schema(conn)
    finally:
        conn.close()
