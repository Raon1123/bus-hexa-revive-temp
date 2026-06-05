"""W2 — 정류소별 버스 도착 정보 도메인 서비스.

F06 §4.4 구현: BIS API 도착 목록을 ROUTEID 필터·정렬해 StopSnapshot 반환.
"""
from __future__ import annotations

from dataclasses import dataclass

from bushexa.data.constants import ROUTEID, STOP_IDS
from bushexa.time_utils import Clock, get_weekday


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BusArrivalRow:
    bus_number: str        # "513", "713" 등
    direction_str: str     # 방향 포함 표시 문자열
    arrival_str: str       # "N분 M초" 형식 표시용
    arrival_seconds: int   # 원시 초 단위 도착시간 (정렬·비교용)
    present_stop: str      # 현재 정류소명
    vehicle_no: str        # 차량번호


@dataclass
class StopSnapshot:
    stop_id: str
    stop_name: str                  # STOP_IDS[stop_id] 값
    rows: list[BusArrivalRow]       # arrival_seconds 오름차순
    has_no_bus: bool                # rows가 비어있으면 True
    long_gap: bool                  # 두 번째 버스까지 1800초 초과 시 True
    error: str | None               # API 실패 메시지, 정상 시 None
    # 남은 시간 정보 (clock 기준)
    minutes_until: list[int]        # 각 row에 대응하는 도착까지 남은 분


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _arrival_str(seconds: int) -> str:
    """초 → 'N분 M초' 표시 문자열."""
    m = seconds // 60
    s = seconds % 60
    return f"{m}분 {s}초"


def _check_long_gap(rows: list[BusArrivalRow]) -> bool:
    """rows가 2개 이상이고 두 번째 버스의 도착까지 첫 번째보다 1800초 이상 차이 나면 True."""
    if len(rows) < 2:
        return False
    return (rows[1].arrival_seconds - rows[0].arrival_seconds) > 1800


# ---------------------------------------------------------------------------
# W2 public function
# ---------------------------------------------------------------------------

def get_stop_data(
    stop_id: str,
    clock: Clock,
    *,
    client,
) -> StopSnapshot:
    """stop_id에 해당하는 정류소 버스 도착 정보를 반환한다.

    Parameters
    ----------
    stop_id : str
        SERACH_STOPS 목록 내 정류소 ID.
    clock : Clock
        시각 공급자 (테스트 시 FakeClock 주입).
    client :
        UlsanBisClient 또는 동일 인터페이스 mock. fetch_arrivals(stop_id) 메서드 제공.
    """
    stop_name = STOP_IDS.get(stop_id, stop_id)
    error: str | None = None
    rows: list[BusArrivalRow] = []

    now = clock.now()
    now_total_seconds = now.hour * 3600 + now.minute * 60 + now.second

    try:
        arrivals = client.fetch_arrivals(stop_id)
    except Exception as exc:
        error = f"BIS API 오류: {exc}"
        arrivals = []

    for arrival in arrivals:
        if arrival.route_id not in ROUTEID:
            continue
        busno, terminal, _dep, _stop_ids = ROUTEID[arrival.route_id]
        # 노선번호는 '노선' 칼럼에 이미 표시되므로 방향 문자열에는 붙이지 않는다.
        direction_str = terminal
        rows.append(BusArrivalRow(
            bus_number=busno,
            direction_str=direction_str,
            arrival_str=_arrival_str(arrival.arrival_time),
            arrival_seconds=arrival.arrival_time,
            present_stop=arrival.present_stop,
            vehicle_no=arrival.vehicle_no,
        ))

    # 도착 시각 오름차순 정렬
    rows.sort(key=lambda r: r.arrival_seconds)

    # 도착까지 남은 시간 계산 (clock 기준 분수)
    minutes_until = [r.arrival_seconds // 60 for r in rows]

    has_no_bus = len(rows) == 0
    long_gap = _check_long_gap(rows)

    return StopSnapshot(
        stop_id=stop_id,
        stop_name=stop_name,
        rows=rows,
        has_no_bus=has_no_bus,
        long_gap=long_gap,
        error=error,
        minutes_until=minutes_until,
    )
