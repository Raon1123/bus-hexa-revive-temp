"""W6a BusLogRepo write 검증. rollback은 제약 없는 테이블이라 bind 불가 객체로 강제."""
from __future__ import annotations

import inspect

import pytest

from bushexa.db.connection import create_connection
from bushexa.db.repo import BusLogRepo, LogRow
from bushexa.db.schema import create_schema


def _repo() -> BusLogRepo:
    conn = create_connection("sqlite:///:memory:")
    create_schema(conn)
    return BusLogRepo(conn)


def test_batch_inserts_100():
    """100개 LogRow를 insert_batch로 넣으면 반환값과 테이블 행 수가 모두 100인지."""
    repo = _repo()
    rows = [
        LogRow(idx=f"20260601_08:{i // 60:02d}:{i % 60:02d}", stop_id="S",
               route_id="R", vehicle_no=f"V{i}")
        for i in range(100)
    ]
    assert repo.insert_batch(rows) == 100
    assert repo.count() == 100


def test_batch_rollback_on_error():
    """배치 중간 행이 bind 불가(임의 객체)면 예외가 나고 트랜잭션 전체가 rollback되어 0건이 남는지(H5)."""
    repo = _repo()
    good = LogRow(idx="20260601_08:00:00", stop_id="S", route_id="R", vehicle_no="V1")
    bad = LogRow(idx="20260601_08:00:01", stop_id="S", route_id="R", vehicle_no=object())

    with pytest.raises(Exception):
        repo.insert_batch([good, bad])

    assert repo.count() == 0  # 먼저 넣은 good 행도 rollback으로 사라져야 한다


def test_insert_log_signature():
    """insert_log의 파라미터가 모두 keyword-only이고 이름이 명세와 정확히 일치하는지(F09 §4.4)."""
    params = [p for p in inspect.signature(BusLogRepo.insert_log).parameters.values()
              if p.name != "self"]
    assert all(p.kind == p.KEYWORD_ONLY for p in params)
    assert {p.name for p in params} == {"idx", "stop_id", "route_id", "vehicle_no", "stop_name"}
