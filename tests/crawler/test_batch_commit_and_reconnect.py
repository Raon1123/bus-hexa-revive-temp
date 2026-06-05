"""W2b batch 트랜잭션 + 재연결 (H5 회귀). 기대값은 주입 응답·사이클 수에서 직접 도출(E-13)."""
from __future__ import annotations

import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

from bushexa.crawler.recorder import GovtrackRecorder
from bushexa.crawler.state import VehicleTimeline
from bushexa.db.repo import BusLogRepo
from bushexa.db.schema import create_schema
from tests.crawler._fakes import FakeTagoClient, SequenceTagoClient, make_response

KST = ZoneInfo("Asia/Seoul")


class _Clock:
    def now(self):
        return datetime(2026, 6, 1, 8, 0, 0, tzinfo=KST)


class CountingConnection(sqlite3.Connection):
    """commit 호출 횟수를 세는 sqlite3.Connection 서브클래스.

    서브클래스이므로 ``isinstance(conn, sqlite3.Connection)``가 참 → repo의 placeholder 판정이
    정상 동작한다(프록시로 감싸면 깨지는 문제를 피한다).
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.commit_count = 0

    def commit(self):
        self.commit_count += 1
        return super().commit()


def _counting_repo() -> tuple[BusLogRepo, CountingConnection]:
    conn = sqlite3.connect(":memory:", factory=CountingConnection)
    conn.execute("PRAGMA foreign_keys=ON")
    create_schema(conn)
    conn.commit_count = 0  # 스키마 생성 commit은 제외
    return BusLogRepo(conn), conn


def test_cycle_single_transaction():
    """run_cycle이 N개 INSERT를 commit 1회로 묶는지(commit 호출 횟수 == 1) 검증한다 — H5 회귀."""
    repo, conn = _counting_repo()
    resp = make_response([
        ("999000149", "명촌", "veh-A"),
        ("193012314", "태화강역", "veh-B"),
    ])
    client = FakeTagoClient(by_route={"195000177": resp})
    recorder = GovtrackRecorder(
        client, VehicleTimeline(), repo, _Clock(),
        tracked_stops_by_route={"195000177": {"999000149", "193012314"}},
        stop_names={"999000149": "명촌", "193012314": "태화강역"},
    )

    cyc = recorder.run_cycle()

    assert cyc.total_inserts == 2
    assert conn.commit_count == 1       # 2개 INSERT가 단일 트랜잭션
    assert repo.count() == 2            # 실제 적재 확인


def test_reconnect_after_drop():
    """첫 사이클에서 OperationalError를 주입해 연결이 끊긴 뒤, 두 번째 사이클에서 재연결되어
    정상 INSERT되고 **cycle1의 통과가 유실 없이 함께 적재**되는지 검증한다 — H5 재연결 + 무손실.

    (state는 record 시 즉시 전진하므로, commit 실패한 후보를 버리면 그 통과는 영구 유실된다 =
    PM-001 증상 재현. 후보 이월-재시도로 막는다. 이월 제거 시 count==1로 떨어져 실패한다.)"""
    class DropRepo:
        def insert_batch(self, rows):
            raise sqlite3.OperationalError("connection dropped")

    good, _ = _counting_repo()
    # veh-A가 cycle1엔 999000149, cycle2엔 193012314(둘 다 추적).
    client = SequenceTagoClient([
        make_response([("999000149", "명촌", "veh-A")]),
        make_response([("193012314", "태화강역", "veh-A")]),
    ])
    recorder = GovtrackRecorder(
        client, VehicleTimeline(), repo=DropRepo(), clock=_Clock(),
        tracked_stops_by_route={"195000177": {"999000149", "193012314"}},
        stop_names={"999000149": "명촌", "193012314": "태화강역"},
        reconnect=lambda: good,
    )

    c1 = recorder.run_cycle()
    assert c1.committed is False        # 연결 끊김으로 commit 실패
    assert c1.total_errors >= 1

    c2 = recorder.run_cycle()           # 사이클 시작 시 reconnect → good repo로 교체
    assert c2.committed is True
    assert good.count() == 2            # cycle1(이월) + cycle2 통과 모두 적재 — 무손실
    assert {r.stop_id for r in good.get_by_route("195000177")} == {"999000149", "193012314"}


def test_cycle_stats_aggregation():
    """run_cycle이 반환하는 CycleStats의 total_inserts가 route별 inserts 합과 일치하는지 검증한다."""
    repo, _ = _counting_repo()
    client = FakeTagoClient(by_route={
        "195000177": make_response([("999000149", "명촌", "vA"), ("193012314", "태화강역", "vB")]),
        "196000421": make_response([("196040234", "UNIST경유", "vC")]),
    })
    recorder = GovtrackRecorder(
        client, VehicleTimeline(), repo, _Clock(),
        tracked_stops_by_route={
            "195000177": {"999000149", "193012314"},
            "196000421": {"196040234"},
        },
        stop_names={},  # 이름 없어도 INSERT(H3)
    )

    cyc = recorder.run_cycle()

    assert cyc.total_inserts == 3
    assert cyc.total_inserts == sum(s.inserts for s in cyc.route_results.values())
