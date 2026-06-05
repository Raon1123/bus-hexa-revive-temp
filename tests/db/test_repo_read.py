"""W6b BusLogRepo read 검증. 시드는 통제된 (route, day, vehicle) 조합으로 구성."""
from __future__ import annotations

from datetime import datetime

from bushexa.db.connection import create_connection
from bushexa.db.repo import BusLogRepo, LogRow
from bushexa.db.schema import create_schema


def _fresh() -> BusLogRepo:
    conn = create_connection("sqlite:///:memory:")
    create_schema(conn)
    return BusLogRepo(conn)


def _seeded() -> BusLogRepo:
    repo = _fresh()
    rows = []
    # route A / day 20260601 : 7건
    rows += [LogRow(idx=f"20260601_08:{i:02d}:00", stop_id=f"S{i}", route_id="A", vehicle_no="V1")
             for i in range(7)]
    # route B / day 20260601 : 3건
    rows += [LogRow(idx=f"20260601_09:{i:02d}:00", stop_id="SB", route_id="B", vehicle_no="V2")
             for i in range(3)]
    # route A / day 20260602 : 2건
    rows += [LogRow(idx=f"20260602_08:{i:02d}:00", stop_id="SC", route_id="A", vehicle_no="V1")
             for i in range(2)]
    repo.insert_batch(rows)
    return repo


def test_filter_matches_count():
    """route_id+day 필터 결과 행 수가 같은 조건 count()와 일치하는지."""
    repo = _seeded()
    page = repo.query_paged(route_id="A", day="20260601", size=1000)
    assert len(page.rows) == repo.count(route_id="A", day="20260601") == 7


def test_pagination_boundaries():
    """size=10으로 25건을 페이지 1/2/3로 나누면 10/10/5건이 나오고 total이 25인지."""
    repo = _fresh()
    repo.insert_batch([LogRow(idx=f"20260601_08:{i:02d}:00", stop_id="S", route_id="R", vehicle_no="V")
                       for i in range(25)])
    p1 = repo.query_paged(route_id="R", page=1, size=10)
    p2 = repo.query_paged(route_id="R", page=2, size=10)
    p3 = repo.query_paged(route_id="R", page=3, size=10)
    assert (len(p1.rows), len(p2.rows), len(p3.rows)) == (10, 10, 5)
    assert p1.total == 25


def test_latest_node_per_vehicle():
    """한 차량의 여러 통과 기록 중 가장 최근 stop_id가 반환되는지(H2 warm 기반)."""
    repo = _fresh()
    repo.insert_batch([
        LogRow(idx="20260601_08:00:00", stop_id="STOP1", route_id="A", vehicle_no="V1"),
        LogRow(idx="20260601_08:05:00", stop_id="STOP2", route_id="A", vehicle_no="V1"),
        LogRow(idx="20260601_08:10:00", stop_id="STOP3", route_id="A", vehicle_no="V1"),
    ])
    latest = repo.latest_node_per_vehicle(since=datetime(2026, 6, 1, 0, 0, 0))
    assert latest[("A", "V1")] == "STOP3"


def test_export_csv_has_bom():
    """export_csv 첫 청크가 UTF-8 BOM으로 시작하는지(엑셀 한글 깨짐 방지)."""
    repo = _seeded()
    chunks = list(repo.export_csv())
    assert chunks[0] == b"\xef\xbb\xbf"


def test_read_api_surface():
    """BusLogRepo에 5개 read 메서드가 모두 존재하는지."""
    for name in ("query_paged", "count", "get_by_route", "latest_node_per_vehicle", "export_csv"):
        assert callable(getattr(BusLogRepo, name))
