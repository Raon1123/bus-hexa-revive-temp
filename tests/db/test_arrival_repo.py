"""W11 BusArrivalRepo 검증 (ADR-010 백업본 스냅샷)."""
from __future__ import annotations

from bushexa.db.connection import create_connection
from bushexa.db.repo_arrival import BusArrivalRepo
from bushexa.db.schema import create_schema


def _repo() -> BusArrivalRepo:
    conn = create_connection("sqlite:///:memory:")
    create_schema(conn)
    return BusArrivalRepo(conn)


def test_upsert_replaces():
    """한 정류장에 2번 upsert하면 갱신이 일어나 행이 1개로 유지되고 최신값을 갖는지(스냅샷)."""
    repo = _repo()
    repo.upsert("S1", [{"route": "713", "sec": 180}], "2026-06-01T08:00:00+09:00")
    repo.upsert("S1", [{"route": "713", "sec": 60}], "2026-06-01T08:00:07+09:00")

    snap = repo.get("S1")
    assert snap is not None
    assert snap.payload == [{"route": "713", "sec": 60}]
    assert snap.fetched_at == "2026-06-01T08:00:07+09:00"
    assert repo.conn.execute("SELECT COUNT(*) FROM bus_arrival_cache").fetchone()[0] == 1


def test_get_roundtrip():
    """직렬화 저장한 도착 목록을 get으로 읽으면 동일 구조 + fetched_at이 복원되는지."""
    repo = _repo()
    payload = [{"route": "713", "present": "명촌", "sec": 420}]
    repo.upsert("S2", payload, "T1")
    snap = repo.get("S2")
    assert snap is not None
    assert snap.payload == payload
    assert snap.fetched_at == "T1"


def test_get_many():
    """여러 stop_id를 한 번에 조회해 stop_id→snapshot 매핑이 반환되는지(화면 일괄 조회)."""
    repo = _repo()
    repo.upsert("A", [1], "t")
    repo.upsert("B", [2], "t")
    out = repo.get_many(["A", "B", "C"])  # C는 미존재
    assert set(out.keys()) == {"A", "B"}
    assert out["A"].payload == [1]
