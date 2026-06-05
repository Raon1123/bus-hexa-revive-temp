"""W5a tests: parse_runs.

P-11 test case intents:
- test_last_run_included: 한 차량이 정류장 순회를 2번 완료한 로그에서 parse_runs가 2개 run 반환
                           (F05 "마지막 회차 유실" 결함 회귀).
- test_skip_unknown_stop: 노선 stop_ids에 없는 stop_id 로그가 결과에서 제외.
- test_split_by_time_gap: 같은 차량이라도 큰 시간 간격으로 떨어진 로그가 별개 run으로 분리.
"""
from __future__ import annotations

from dataclasses import dataclass

from bushexa.domain.running import parse_runs, VehicleRun


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@dataclass
class FakeLogRow:
    """Minimal LogRow-compatible stub for domain testing."""
    idx: str            # "YYYYMMDD_HH:MM:SS"
    stop_id: str
    route_id: str
    vehicle_no: str
    stop_name: str | None = None
    route_nm: str | None = None


# Route 195000178 = 713/UNIST→명촌
# stop_ids from ROUTEID:
#   ["196040233", "196040231", "196040205", "196040211", "196020807", "196020415",
#    "193040223", "192021209", "192021605", "193040419", "193012313", "999000148"]
ROUTE_ID_713 = "195000178"
# Use first and second stop from 713's stop_ids
STOP_A = "196040233"  # UNIST 기점
STOP_B = "196040231"  # 울산과학기술원정문 (시내)
STOP_C = "196040205"  # 진목회관 (시내)
UNKNOWN_STOP = "XXXXXXXX"  # not in any ROUTEID


# ---------------------------------------------------------------------------
# AC tests (spec P-11)
# ---------------------------------------------------------------------------

def test_last_run_included():
    """P-11: 한 차량이 정류장 순회를 2번 완료한 로그에서 parse_runs가 2개의 run을 반환.

    This is a regression test for F05 "마지막 회차 유실" bug:
    The old implementation forgot to append the last accumulated run after the loop.

    Fixture:
      Vehicle A001, route 195000178 (713).
      Run 1: 08:00, 08:05 at stops A, B
      Run 2 (after 90min gap): 09:35, 09:40 at stops A, B
    Expected: len(runs) == 2 (both runs captured).
    """
    logs = [
        FakeLogRow(idx="20260601_08:00:00", stop_id=STOP_A, route_id=ROUTE_ID_713, vehicle_no="A001"),
        FakeLogRow(idx="20260601_08:05:00", stop_id=STOP_B, route_id=ROUTE_ID_713, vehicle_no="A001"),
        # 90-minute gap → new run
        FakeLogRow(idx="20260601_09:35:00", stop_id=STOP_A, route_id=ROUTE_ID_713, vehicle_no="A001"),
        FakeLogRow(idx="20260601_09:40:00", stop_id=STOP_B, route_id=ROUTE_ID_713, vehicle_no="A001"),
    ]

    runs = parse_runs(logs, ROUTE_ID_713)

    assert len(runs) == 2, (
        f"Expected 2 runs (F05 마지막 회차 유실 regression), got {len(runs)}"
    )
    # Both runs should be for vehicle A001
    assert all(r.vehicle_no == "A001" for r in runs)


def test_skip_unknown_stop():
    """P-11: 노선 stop_ids에 없는 stop_id를 가진 로그 행이 결과에서 제외되고 예외가 없음.

    Fixture:
      Logs for vehicle A001 with stops: STOP_A (valid), UNKNOWN_STOP (invalid), STOP_B (valid).
    Expected: UNKNOWN_STOP log is silently skipped, only valid stops appear in run.
    """
    logs = [
        FakeLogRow(idx="20260601_08:00:00", stop_id=STOP_A, route_id=ROUTE_ID_713, vehicle_no="A001"),
        FakeLogRow(idx="20260601_08:03:00", stop_id=UNKNOWN_STOP, route_id=ROUTE_ID_713, vehicle_no="A001"),
        FakeLogRow(idx="20260601_08:05:00", stop_id=STOP_B, route_id=ROUTE_ID_713, vehicle_no="A001"),
    ]

    # Should not raise any exception
    runs = parse_runs(logs, ROUTE_ID_713)

    assert len(runs) >= 1, "At least one run should be produced"
    # The unknown stop should not appear in any run
    for run in runs:
        assert UNKNOWN_STOP not in run.stops, (
            f"Unknown stop {UNKNOWN_STOP!r} should not appear in run stops"
        )


def test_split_by_time_gap():
    """P-11: 같은 차량이라도 큰 시간 간격으로 떨어진 로그가 별개 run으로 분리.

    Fixture:
      Vehicle A001, same route.
      Segment 1: 08:00, 08:05
      Segment 2 (after 2 hours gap): 10:10, 10:15
    Expected: 2 separate VehicleRun objects (split by time gap > 60 minutes).
    """
    logs = [
        FakeLogRow(idx="20260601_08:00:00", stop_id=STOP_A, route_id=ROUTE_ID_713, vehicle_no="A001"),
        FakeLogRow(idx="20260601_08:05:00", stop_id=STOP_B, route_id=ROUTE_ID_713, vehicle_no="A001"),
        # 2-hour gap
        FakeLogRow(idx="20260601_10:10:00", stop_id=STOP_A, route_id=ROUTE_ID_713, vehicle_no="A001"),
        FakeLogRow(idx="20260601_10:15:00", stop_id=STOP_B, route_id=ROUTE_ID_713, vehicle_no="A001"),
    ]

    runs = parse_runs(logs, ROUTE_ID_713)

    assert len(runs) == 2, (
        f"Expected 2 runs after 2-hour gap, got {len(runs)}"
    )
