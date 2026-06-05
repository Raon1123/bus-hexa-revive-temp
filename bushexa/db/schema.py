"""DB 스키마 생성 (W5). SQLite/PostgreSQL 공통 DDL.

- ``bus_timelog``       : govtrack 버스 통과 기록 (F09 §5 컬럼·인덱스)
- ``bus_arrival_cache`` : 울산 도착정보 백업본 스냅샷 (ADR-010, stop_id별 upsert)

타입은 VARCHAR/TEXT 공통, 모든 DDL은 ``IF NOT EXISTS``로 idempotent — 컨테이너 재시작 안전.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("bushexa.db.schema")

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

# 감사 2-5: 중복 기록 방지용 UNIQUE 인덱스. 기존 운영 DB에 중복 행이 있으면 생성이
# 실패할 수 있으므로 try/except로 잡아 경고 후 계속한다(ADR-013, 기동 차단 금지).
_UNIQUE_INDEX_DDL = (
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_bus_timelog_passage "
    "ON bus_timelog(idx, vehicle_number, stop_id)"
)


def create_schema(conn) -> None:
    """bus_timelog(+인덱스 3종)과 bus_arrival_cache를 생성한다. 2회 호출해도 안전.

    감사 2-5: UNIQUE(idx, vehicle_number, stop_id) 인덱스를 별도 단계로 생성한다.
    기존 DB에 중복 행이 있으면 해당 단계만 실패하고 경고 로그 후 계속하므로(ADR-013),
    테이블 생성 자체는 항상 성공한다.
    """
    cur = conn.cursor()
    for ddl in _DDL:
        cur.execute(ddl)
    conn.commit()

    # UNIQUE 인덱스는 기존 DB 중복 행 존재 시 실패 가능 → 분리된 try/except(ADR-013).
    try:
        conn.cursor().execute(_UNIQUE_INDEX_DDL)
        conn.commit()
    except Exception as exc:
        logger.warning(
            "UNIQUE 인덱스 생성 실패 — 기존 DB에 중복 행이 있을 수 있습니다. "
            "INSERT OR IGNORE 보호는 이 인덱스 없이는 동작하지 않습니다. 원인: %s",
            exc,
        )
