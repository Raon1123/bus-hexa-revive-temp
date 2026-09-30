"""W5a + W5b — 운행 재구성 테이블 도메인 서비스.

F05 §4.4 구현: DB 로그에서 차량별 운행(trip) 재구성 및 그리드 생성.
결함 수정:
 - 마지막 운행 회차 유실 버그 수정: 루프 종료 후 누적된 마지막 run을 결과에 추가.
 - 정류장 길이 불일치 버그 수정: build_running_grid에서 모든 열을 stops_order 길이로 통일.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass, field

from bushexa.data.constants import TRACKED_ROUTES

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class VehicleRun:
    """단일 차량의 단일 운행 회차."""
    vehicle_no: str
    route_id: str
    stops: dict[str, str]  # stop_id → "HH:MM" 통과 시각


@dataclass
class DroppedStop:
    """노선 stop_ids에 없어 운행 재구성에서 제외된 정류장."""
    stop_id: str
    stop_name: str | None
    count: int


@dataclass
class RunSplit:
    """시간 간격 초과로 한 차량의 운행이 둘로 나뉜 지점."""
    vehicle_no: str
    before_idx: str   # 이전 run의 마지막 로그
    after_idx: str    # 새 run의 첫 로그
    gap_minutes: float


@dataclass
class StopOverwrite:
    """같은 run 안에서 한 정류장을 다시 통과해 이전 시각이 덮어써진 경우."""
    vehicle_no: str
    stop_id: str
    dropped: str      # 버려진 이전 "HH:MM"
    kept: str         # 남은 나중 "HH:MM"


@dataclass
class RunsExplanation:
    """parse_runs 결과 + 그리드에 드러나지 않는 재구성 과정 진단 정보."""
    runs: list[VehicleRun]
    total_rows: int = 0
    unknown_route: bool = False
    dropped_stops: list[DroppedStop] = field(default_factory=list)
    unparsable_idx: list[str] = field(default_factory=list)
    splits: list[RunSplit] = field(default_factory=list)
    overwrites: list[StopOverwrite] = field(default_factory=list)


@dataclass
class RunningGrid:
    """정류장(행) × 운행 회차(열) 그리드."""
    stops_order: list[str]            # 정류장 ID 순서
    runs: list[dict[str, str]]        # 각 run의 {stop_id: "HH:MM" 또는 마커}
    missing_marker: str = "レ"        # 미통과 정류장 셀 마커


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# 연속 정류장 로그 사이의 최대 간격(분) — 이를 초과하면 별개 운행으로 분리
_SPLIT_GAP_MINUTES = 60


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_timelog(idx: str) -> datetime.datetime:
    """타임로그 인덱스 문자열을 datetime으로 파싱.

    지원 형식: "YYYYMMDD_HH:MM:SS", "YYYY-MM-DD_HH:MM:SS"
    """
    # "YYYYMMDD_HH:MM:SS" 또는 "YYYY-MM-DD_HH:MM:SS"
    date_part, time_part = idx.split("_")
    if "-" in date_part:
        dt = datetime.datetime.strptime(date_part + " " + time_part, "%Y-%m-%d %H:%M:%S")
    else:
        dt = datetime.datetime.strptime(date_part + " " + time_part, "%Y%m%d %H:%M:%S")
    return dt


# ---------------------------------------------------------------------------
# W5a public function
# ---------------------------------------------------------------------------

def parse_runs(
    timelog_rows,  # list[LogRow]
    route_id: str,
) -> list[VehicleRun]:
    """차량 번호별로 로그를 그룹화하고 시간 간격으로 개별 운행(trip)을 분리한다.

    Parameters
    ----------
    timelog_rows :
        BusLogRepo.get_by_route 반환값 (LogRow 목록).
    route_id : str
        노선 ID. TRACKED_ROUTES에서 stop_ids 목록을 가져옴.

    Returns
    -------
    list[VehicleRun]
        F05 결함 수정: 마지막 운행 회차를 반드시 포함.
    """
    return explain_runs(timelog_rows, route_id).runs


def explain_runs(
    timelog_rows,  # list[LogRow]
    route_id: str,
) -> RunsExplanation:
    """parse_runs와 같은 재구성을 수행하면서 그 과정을 함께 기록한다.

    그리드에는 드러나지 않는 정보(제외된 정류장, 파싱 불가 idx, 운행 분리 지점,
    같은 run 내 재통과 덮어쓰기)를 돌려준다. parse_runs는 이 함수의 ``runs``만 쓰므로
    두 결과는 항상 일치한다.
    """
    rows = list(timelog_rows)
    if route_id not in TRACKED_ROUTES:
        return RunsExplanation(runs=[], total_rows=len(rows), unknown_route=True)

    _busno, _terminal, _dep, stop_ids = TRACKED_ROUTES[route_id]
    stop_id_set = set(stop_ids)
    explanation = RunsExplanation(runs=[], total_rows=len(rows))
    dropped: dict[str, DroppedStop] = {}

    # 차량별 로그 그룹화
    vehicle_logs: dict[str, list] = {}
    for row in rows:
        # 미등록 stop_id 건너뜀
        if row.stop_id not in stop_id_set:
            entry = dropped.setdefault(
                row.stop_id, DroppedStop(row.stop_id, getattr(row, "stop_name", None), 0))
            entry.count += 1
            continue
        vehicle_logs.setdefault(row.vehicle_no, []).append(row)
    explanation.dropped_stops = sorted(dropped.values(), key=lambda d: -d.count)

    runs = explanation.runs

    for vehicle_no, logs in vehicle_logs.items():
        # idx(YYYYMMDD_HH:MM:SS) 기준 오름차순 정렬
        logs.sort(key=lambda r: r.idx)

        current_run_stops: dict[str, str] = {}
        prev_dt: datetime.datetime | None = None
        prev_idx: str | None = None

        for log in logs:
            try:
                curr_dt = _parse_timelog(log.idx)
            except (ValueError, AttributeError):
                explanation.unparsable_idx.append(str(log.idx))
                continue

            # 큰 시간 간격이면 현재 run을 저장하고 새 run 시작
            if prev_dt is not None:
                gap_minutes = (curr_dt - prev_dt).total_seconds() / 60
                if gap_minutes > _SPLIT_GAP_MINUTES:
                    explanation.splits.append(RunSplit(
                        vehicle_no=vehicle_no,
                        before_idx=prev_idx,
                        after_idx=log.idx,
                        gap_minutes=gap_minutes,
                    ))
                    if current_run_stops:
                        runs.append(VehicleRun(
                            vehicle_no=vehicle_no,
                            route_id=route_id,
                            stops=dict(current_run_stops),
                        ))
                    current_run_stops = {}

            # 통과 시각 기록 (HH:MM)
            time_str = curr_dt.strftime("%H:%M")
            if log.stop_id in current_run_stops:
                explanation.overwrites.append(StopOverwrite(
                    vehicle_no=vehicle_no,
                    stop_id=log.stop_id,
                    dropped=current_run_stops[log.stop_id],
                    kept=time_str,
                ))
            current_run_stops[log.stop_id] = time_str
            prev_dt = curr_dt
            prev_idx = log.idx

        # F05 결함 수정: 루프 종료 후 마지막 run도 반드시 추가
        if current_run_stops:
            runs.append(VehicleRun(
                vehicle_no=vehicle_no,
                route_id=route_id,
                stops=dict(current_run_stops),
            ))

    return explanation


# ---------------------------------------------------------------------------
# W5b public function
# ---------------------------------------------------------------------------

def build_running_grid(
    runs: list[VehicleRun],
    stops_order: list[str],
    missing_marker: str = "レ",
) -> RunningGrid:
    """정류장(행) × 운행 회차(열) 그리드를 생성한다.

    Parameters
    ----------
    runs : list[VehicleRun]
        parse_runs 반환값.
    stops_order : list[str]
        그리드 행 순서로 사용할 stop_id 목록.
    missing_marker : str
        미통과 정류장 셀에 채울 마커 (기본 "レ").

    Returns
    -------
    RunningGrid
        모든 열이 stops_order 길이를 가짐. F05 결함 수정.
    """
    grid_runs: list[dict[str, str]] = []

    for run in runs:
        row_dict: dict[str, str] = {}
        for stop_id in stops_order:
            if stop_id in run.stops:
                row_dict[stop_id] = run.stops[stop_id]
            else:
                row_dict[stop_id] = missing_marker
        grid_runs.append(row_dict)

    return RunningGrid(
        stops_order=stops_order,
        runs=grid_runs,
        missing_marker=missing_marker,
    )
