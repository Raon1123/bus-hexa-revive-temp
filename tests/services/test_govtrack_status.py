"""W6 govtrack 상태 writer/reader 검증. 기대값은 주입한 CycleStats에서 직접 도출(E-13)."""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from bushexa.crawler.recorder import CycleStats, RouteStats
from bushexa.services.govtrack_status import GovtrackStatusReader, GovtrackStatusWriter

KST = ZoneInfo("Asia/Seoul")
BASE = datetime(2026, 6, 1, 8, 0, 0, tzinfo=KST)


def _cycle(started, *, route_inserts, total_errors=0, committed=True) -> CycleStats:
    routes = {rid: RouteStats(route_id=rid, inserts=n) for rid, n in route_inserts.items()}
    return CycleStats(cycle_started_at=started, route_results=routes,
                      total_inserts=sum(route_inserts.values()),
                      total_errors=total_errors, committed=committed)


def test_write_then_latest(tmp_path):
    """CycleStats를 write한 뒤 latest()가 동일한 last_success_at, total_inserts, route_breakdown을
    반환하는지 검증한다 — F04 AC-G1, F09 AC-M2."""
    path = tmp_path / "status.json"
    GovtrackStatusWriter(path).write(_cycle(BASE, route_inserts={"195000177": 2, "196000421": 1}))

    s = GovtrackStatusReader(path).latest()
    assert s is not None
    assert s.total_inserts == 3
    assert s.route_breakdown == {"195000177": 2, "196000421": 1}
    assert s.last_success_at == BASE.isoformat()
    assert s.consecutive_failures == 0


def test_failure_count(tmp_path):
    """실패 사이클을 연속 write하면 latest().consecutive_failures가 증가하고, 성공 사이클이 끼면
    0으로 리셋되는지 검증한다 — F04 AC-G2."""
    path = tmp_path / "status.json"
    w, r = GovtrackStatusWriter(path), GovtrackStatusReader(path)

    for i in range(3):  # 3사이클 연속 실패(오류>0)
        w.write(_cycle(BASE + timedelta(minutes=i), route_inserts={}, total_errors=10))
    assert r.latest().consecutive_failures == 3

    w.write(_cycle(BASE + timedelta(minutes=3), route_inserts={"195000177": 1}))  # 성공
    assert r.latest().consecutive_failures == 0


def test_history_limit(tmp_path):
    """60개 사이클 write 후 history(50)가 최근 50개를 최신순(역순)으로 반환하는지 검증한다."""
    path = tmp_path / "status.json"
    w = GovtrackStatusWriter(path)
    for i in range(60):
        w.write(_cycle(BASE + timedelta(minutes=i), route_inserts={"R": i}))

    hist = GovtrackStatusReader(path).history(50)
    assert len(hist) == 50
    assert hist[0].total_inserts == 59   # 가장 최신(i=59)
    assert hist[-1].total_inserts == 10  # 최근 50개 중 가장 오래된(i=10)
