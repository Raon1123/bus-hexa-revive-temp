"""T8: DB UNIQUE 인덱스 + INSERT OR IGNORE 검증 (감사 2-5).

기대값은 삽입한 행 수와 충돌 조건에서 직접 도출한다(E-13).
"""
from __future__ import annotations

import pytest

from bushexa.db.connection import create_connection
from bushexa.db.repo import BusLogRepo, LogRow
from bushexa.db.schema import create_schema


def _fresh() -> BusLogRepo:
    conn = create_connection("sqlite:///:memory:")
    create_schema(conn)
    return BusLogRepo(conn)


def test_T8_unique_index_exists():
    """T8: create_schema 후 ux_bus_timelog_passage UNIQUE 인덱스가 존재하는지."""
    conn = create_connection("sqlite:///:memory:")
    create_schema(conn)
    names = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        )
    }
    assert "ux_bus_timelog_passage" in names, "UNIQUE 인덱스 ux_bus_timelog_passage가 없음"
    conn.close()


def test_T8_insert_or_ignore_skips_duplicate():
    """T8: 동일 (idx, vehicle_number, stop_id)를 두 번 insert_batch해도 1건만 남는지.

    INSERT OR IGNORE 동작 검증: 중복 행이 조용히 무시되어 중복 삽입이 없어야 한다(감사 2-5).
    """
    repo = _fresh()
    row = LogRow(idx="20260601_08:00:00", stop_id="999000149", route_id=ROUTE, vehicle_no="veh-A",
                 stop_name="명촌", route_nm="713")
    # 동일 행 두 번 삽입
    repo.insert_batch([row])
    repo.insert_batch([row])

    assert repo.count() == 1, "중복 행이 INSERT되었음 — UNIQUE 인덱스가 동작하지 않음"


def test_T8_duplicate_in_same_batch_skipped():
    """T8: 같은 배치 안에 중복 행이 있어도 한 건만 남는지."""
    repo = _fresh()
    row = LogRow(idx="20260601_08:00:00", stop_id="999000149", route_id=ROUTE, vehicle_no="veh-A",
                 stop_name="명촌")
    # 같은 배치에 2번 포함
    repo.insert_batch([row, row])

    assert repo.count() == 1, "배치 내 중복 행이 INSERT되었음"


def test_T8_different_keys_both_inserted():
    """T8: 서로 다른 키를 가진 행은 모두 삽입되어야 한다(UNIQUE는 중복만 막음)."""
    repo = _fresh()
    rows = [
        LogRow(idx="20260601_08:00:00", stop_id="S1", route_id=ROUTE, vehicle_no="veh-A"),
        LogRow(idx="20260601_08:00:00", stop_id="S2", route_id=ROUTE, vehicle_no="veh-A"),  # stop_id 다름
        LogRow(idx="20260601_08:00:00", stop_id="S1", route_id=ROUTE, vehicle_no="veh-B"),  # vehicle 다름
        LogRow(idx="20260601_08:01:00", stop_id="S1", route_id=ROUTE, vehicle_no="veh-A"),  # idx 다름
    ]
    repo.insert_batch(rows)

    assert repo.count() == 4, "정상 행들이 INSERT되지 않음"


def test_T8_create_schema_idempotent_with_unique():
    """T8: create_schema를 두 번 호출해도 예외 없이 통과하는지(UNIQUE 인덱스 포함)."""
    conn = create_connection("sqlite:///:memory:")
    create_schema(conn)
    create_schema(conn)  # 두 번째 호출도 안전해야 함
    conn.close()


def test_T8_existing_duplicate_does_not_block_startup():
    """T8: 기존 DB에 중복 행이 있어도 create_schema가 예외 없이 완료되는지(ADR-013).

    UNIQUE 인덱스 생성 실패가 데몬 기동을 막지 않는 것을 검증한다.
    """
    conn = create_connection("sqlite:///:memory:")
    # 먼저 테이블만 생성 (UNIQUE 없이)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bus_timelog (
            idx VARCHAR(40),
            stop_id VARCHAR(20),
            route_id VARCHAR(20),
            route_nm VARCHAR(20),
            vehicle_number VARCHAR(20),
            stop_name VARCHAR(50)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bus_arrival_cache (
            stop_id VARCHAR(20) PRIMARY KEY,
            payload TEXT,
            fetched_at VARCHAR(40)
        )
    """)
    conn.commit()
    # 중복 행 삽입 (UNIQUE 없는 상태)
    conn.execute(
        "INSERT INTO bus_timelog (idx, stop_id, route_id, vehicle_number) VALUES (?,?,?,?)",
        ("20260601_08:00:00", "S1", "R1", "V1")
    )
    conn.execute(
        "INSERT INTO bus_timelog (idx, stop_id, route_id, vehicle_number) VALUES (?,?,?,?)",
        ("20260601_08:00:00", "S1", "R1", "V1")
    )
    conn.commit()

    # create_schema 호출 — UNIQUE 인덱스 생성 실패해도 예외 없이 완료되어야 한다(ADR-013)
    try:
        create_schema(conn)
    except Exception as e:
        pytest.fail(f"기존 DB 중복 행 존재 시 create_schema가 예외를 던짐: {e}")
    finally:
        conn.close()


ROUTE = "195000177"
