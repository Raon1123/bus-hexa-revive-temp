"""DB 스키마 생성 (W5). SQLite/PostgreSQL 공통 DDL.

- ``bus_timelog``       : govtrack 버스 통과 기록 (F09 §5 컬럼·인덱스)
- ``bus_arrival_cache`` : 울산 도착정보 백업본 스냅샷 (ADR-010, stop_id별 upsert)

타입은 VARCHAR/TEXT 공통, 모든 DDL은 ``IF NOT EXISTS``로 idempotent — 컨테이너 재시작 안전.
"""
from __future__ import annotations

_DDL: list[str] = [
    """
    CREATE TABLE IF NOT EXISTS bus_timelog (
        idx VARCHAR(40),
        stop_id VARCHAR(20),
        route_id VARCHAR(20),
        route_nm VARCHAR(20),
        vehicle_number VARCHAR(20),
        stop_name VARCHAR(50)
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_bus_timelog_route_idx ON bus_timelog (route_id, idx)",
    "CREATE INDEX IF NOT EXISTS ix_bus_timelog_stop_idx ON bus_timelog (stop_id, idx)",
    "CREATE INDEX IF NOT EXISTS ix_bus_timelog_vehicle ON bus_timelog (vehicle_number, idx)",
    """
    CREATE TABLE IF NOT EXISTS bus_arrival_cache (
        stop_id VARCHAR(20) PRIMARY KEY,
        payload TEXT,
        fetched_at VARCHAR(40)
    )
    """,
]


def create_schema(conn) -> None:
    """bus_timelog(+인덱스 3종)과 bus_arrival_cache를 생성한다. 2회 호출해도 안전."""
    cur = conn.cursor()
    for ddl in _DDL:
        cur.execute(ddl)
    conn.commit()
