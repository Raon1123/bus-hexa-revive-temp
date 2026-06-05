"""CachedArrivalClient 검증 — 화면 서빙 경로가 cache(bus_arrival_cache)를 읽는지.

UlsanBisClient.fetch_arrivals와 동일 인터페이스로 BusArrivalRepo 백업본을 Arrival로 복원한다.
독립 출처: ADR-010(화면은 백업본을 읽는다) + Arrival/poller payload 계약(asdict 직렬화).
"""
from __future__ import annotations

from dataclasses import asdict

from bushexa.api_clients.cached_arrival import CachedArrivalClient
from bushexa.api_clients.ulsan_bis import Arrival
from bushexa.db.connection import create_connection
from bushexa.db.repo_arrival import BusArrivalRepo
from bushexa.db.schema import create_schema


def _repo() -> BusArrivalRepo:
    conn = create_connection("sqlite:///:memory:")
    create_schema(conn)
    return BusArrivalRepo(conn)


def test_fetch_arrivals_restores_arrival_objects():
    """poller가 asdict로 저장한 payload를 Arrival 객체로 복원해 돌려준다."""
    repo = _repo()
    arrivals = [
        Arrival(route_id="R1", present_stop="명촌", vehicle_no="123", arrival_time=180),
        Arrival(route_id="R2", present_stop="굴화", vehicle_no="456", arrival_time=60),
    ]
    repo.upsert("S1", [asdict(a) for a in arrivals], "2026-06-01T08:00:00+09:00")

    client = CachedArrivalClient(repo)
    result = client.fetch_arrivals("S1")

    assert result == arrivals  # 동일 구조로 복원 (frozen dataclass 동등성)


def test_fetch_arrivals_cache_miss_returns_empty():
    """cache 행이 없으면 [] (라이브 클라가 오류 시 [] 반환하는 것과 동일, ADR-013)."""
    client = CachedArrivalClient(_repo())
    assert client.fetch_arrivals("nope") == []


def test_fetch_arrivals_ignores_extra_payload_keys():
    """payload에 잉여 키가 섞여도 Arrival 필드만 추려 안전하게 복원한다."""
    repo = _repo()
    repo.upsert(
        "S2",
        [{"route_id": "R1", "present_stop": "명촌", "vehicle_no": "1", "arrival_time": 30, "junk": 1}],
        "T1",
    )
    result = CachedArrivalClient(repo).fetch_arrivals("S2")
    assert result == [Arrival(route_id="R1", present_stop="명촌", vehicle_no="1", arrival_time=30)]


def test_last_fetched_at():
    """staleness 표시용 fetched_at 노출. 없으면 None."""
    repo = _repo()
    repo.upsert("S3", [], "2026-06-01T09:00:00+09:00")
    client = CachedArrivalClient(repo)
    assert client.last_fetched_at("S3") == "2026-06-01T09:00:00+09:00"
    assert client.last_fetched_at("absent") is None
