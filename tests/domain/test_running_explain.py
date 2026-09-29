"""explain_runs tests: /running 재구성 과정 진단 정보.

테스트 의도:
- test_matches_parse_runs: explain_runs().runs 가 parse_runs 결과와 동일 (단일 구현 보장).
- test_dropped_stops_counted: 노선 stop_ids 밖의 stop_id가 이름·개수와 함께 집계.
- test_split_recorded: 60분 초과 간격 분리 지점이 전후 idx·간격과 함께 기록.
- test_overwrite_recorded: 같은 run 안 재통과 시 버려진 이전 시각이 기록.
- test_unparsable_idx_recorded: 파싱 불가 idx 행이 기록.
- test_unknown_route: 미등록 route_id → 빈 runs + unknown_route 플래그.
"""
from __future__ import annotations

from dataclasses import dataclass

from bushexa.domain.running import explain_runs, parse_runs

ROUTE_ID_713 = "195000178"
STOP_A = "196040233"  # UNIST 기점
STOP_B = "196040231"  # 울산과학기술원정문 (시내)
UNKNOWN_STOP = "XXXXXXXX"


@dataclass
class FakeLogRow:
    idx: str
    stop_id: str
    route_id: str
    vehicle_no: str
    stop_name: str | None = None
    route_nm: str | None = None


def _row(idx: str, stop_id: str, vehicle_no: str = "A001", stop_name: str | None = None):
    return FakeLogRow(idx=idx, stop_id=stop_id, route_id=ROUTE_ID_713,
                      vehicle_no=vehicle_no, stop_name=stop_name)


def test_matches_parse_runs():
    logs = [
        _row("20260601_08:00:00", STOP_A),
        _row("20260601_08:05:00", STOP_B),
        _row("20260601_09:35:00", STOP_A),
        _row("20260601_08:10:00", STOP_A, vehicle_no="B002"),
    ]
    assert explain_runs(logs, ROUTE_ID_713).runs == parse_runs(logs, ROUTE_ID_713)


def test_dropped_stops_counted():
    logs = [
        _row("20260601_08:00:00", STOP_A),
        _row("20260601_08:02:00", UNKNOWN_STOP, stop_name="범서중학교"),
        _row("20260601_08:03:00", UNKNOWN_STOP, stop_name="범서중학교"),
        _row("20260601_08:05:00", STOP_B),
    ]
    ex = explain_runs(logs, ROUTE_ID_713)

    assert ex.total_rows == 4
    assert len(ex.dropped_stops) == 1
    assert ex.dropped_stops[0].stop_id == UNKNOWN_STOP
    assert ex.dropped_stops[0].stop_name == "범서중학교"
    assert ex.dropped_stops[0].count == 2


def test_split_recorded():
    logs = [
        _row("20260601_08:00:00", STOP_A),
        _row("20260601_08:05:00", STOP_B),
        _row("20260601_09:35:00", STOP_A),
    ]
    ex = explain_runs(logs, ROUTE_ID_713)

    assert len(ex.runs) == 2
    assert len(ex.splits) == 1
    split = ex.splits[0]
    assert split.vehicle_no == "A001"
    assert split.before_idx == "20260601_08:05:00"
    assert split.after_idx == "20260601_09:35:00"
    assert split.gap_minutes == 90


def test_overwrite_recorded():
    # 60분 이내에 같은 정류장 재통과 → 한 run 안에서 이전 시각이 덮어써짐
    logs = [
        _row("20260601_08:00:00", STOP_A),
        _row("20260601_08:05:00", STOP_B),
        _row("20260601_08:50:00", STOP_A),
    ]
    ex = explain_runs(logs, ROUTE_ID_713)

    assert len(ex.runs) == 1
    assert ex.runs[0].stops[STOP_A] == "08:50"
    assert len(ex.overwrites) == 1
    assert (ex.overwrites[0].stop_id, ex.overwrites[0].dropped, ex.overwrites[0].kept) == (
        STOP_A, "08:00", "08:50")


def test_unparsable_idx_recorded():
    logs = [
        _row("20260601_08:00:00", STOP_A),
        _row("garbage", STOP_B),
    ]
    ex = explain_runs(logs, ROUTE_ID_713)

    assert ex.unparsable_idx == ["garbage"]
    assert len(ex.runs) == 1


def test_unknown_route():
    ex = explain_runs([_row("20260601_08:00:00", STOP_A)], "NOT-A-ROUTE")

    assert ex.unknown_route is True
    assert ex.runs == []
    assert ex.total_rows == 1
