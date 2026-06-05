"""W5a + W5b — 운행 재구성 테이블 도메인 서비스.

F05 §4.4 구현: DB 로그에서 차량별 운행(trip) 재구성 및 그리드 생성.
결함 수정:
 - 마지막 운행 회차 유실 버그 수정: 루프 종료 후 누적된 마지막 run을 결과에 추가.
 - 정류장 길이 불일치 버그 수정: build_running_grid에서 모든 열을 stops_order 길이로 통일.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass, field

from bushexa.data.constants import ROUTEID

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
        노선 ID. ROUTEID에서 stop_ids 목록을 가져옴.

    Returns
    -------
    list[VehicleRun]
        F05 결함 수정: 마지막 운행 회차를 반드시 포함.
    """
    if route_id not in ROUTEID:
        return []

    _busno, _terminal, _dep, stop_ids = ROUTEID[route_id]
    stop_id_set = set(stop_ids)

    # 차량별 로그 그룹화
    vehicle_logs: dict[str, list] = {}
    for row in timelog_rows:
        # 미등록 stop_id 건너뜀
        if row.stop_id not in stop_id_set:
            continue
        vehicle_logs.setdefault(row.vehicle_no, []).append(row)

    runs: list[VehicleRun] = []

    for vehicle_no, logs in vehicle_logs.items():
        # idx(YYYYMMDD_HH:MM:SS) 기준 오름차순 정렬
        logs.sort(key=lambda r: r.idx)

        current_run_stops: dict[str, str] = {}
        prev_dt: datetime.datetime | None = None

        for log in logs:
            try:
                curr_dt = _parse_timelog(log.idx)
            except (ValueError, AttributeError):
                continue

            # 큰 시간 간격이면 현재 run을 저장하고 새 run 시작
            if prev_dt is not None:
                gap_minutes = (curr_dt - prev_dt).total_seconds() / 60
                if gap_minutes > _SPLIT_GAP_MINUTES:
                    if current_run_stops:
                        runs.append(VehicleRun(
                            vehicle_no=vehicle_no,
                            route_id=route_id,
                            stops=dict(current_run_stops),
                        ))
                    current_run_stops = {}

            # 통과 시각 기록 (HH:MM)
            time_str = curr_dt.strftime("%H:%M")
            current_run_stops[log.stop_id] = time_str
            prev_dt = curr_dt

        # F05 결함 수정: 루프 종료 후 마지막 run도 반드시 추가
        if current_run_stops:
            runs.append(VehicleRun(
                vehicle_no=vehicle_no,
                route_id=route_id,
                stops=dict(current_run_stops),
            ))

    return runs


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
