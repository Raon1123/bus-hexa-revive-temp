"""W4 — 전체 시간표 컬러 그리드 도메인 서비스.

F08 §4.4 구현: 모든 노선의 시간표를 시(Hour)별로 그룹화·정렬.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, TypedDict

from bushexa.data.constants import WEEKDAY_STR
from bushexa.data.timetable import get_busroute_info
from bushexa.time_utils import Clock, get_weekday


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

class DepartureEntry(TypedDict):
    minute: str    # "MM" 형식
    busno: str     # 예: "713"


class TimetableHourRow(TypedDict):
    hour: str                          # "HH" 형식
    departures: list[DepartureEntry]   # 해당 시(Hour)의 모든 출발 항목 (분 오름차순 정렬)


@dataclass(frozen=True)
class FullTimetableSnapshot:
    current_time: str                       # "HH:MM"
    weekday_str: str                        # WEEKDAY_STR[weekday]
    selected_day: int                       # 0, 1, 2
    bus_legend: list[str]                   # 범례 버스번호 목록 (오름차순)
    timetable_rows: list[TimetableHourRow]  # 빈 리스트이면 데이터 없음
    is_empty: bool                          # timetable_rows가 빈 경우 True


# ---------------------------------------------------------------------------
# W4 public function
# ---------------------------------------------------------------------------

def get_full_timetable_data(
    weekday: int,
    clock: Clock,
    *,
    timetable_provider: Callable[[str, int, str], list[str]],
) -> FullTimetableSnapshot:
    """전체 시간표 페이지 데이터를 반환한다.

    Parameters
    ----------
    weekday : int
        요일 인덱스 (0=평일, 1=토, 2=일/공휴일). 0·1·2 범위 밖이면 0으로 보정.
    clock : Clock
        시각 공급자.
    timetable_provider :
        Callable[[busno, weekday, departure], list[str]].
    """
    # weekday 보정 (0·1·2 범위 밖 → 0)
    if weekday not in (0, 1, 2):
        weekday = 0

    now = clock.now()
    now_h, now_m = now.hour, now.minute
    weekday_label = WEEKDAY_STR.get(weekday, str(weekday))

    busnos, departure_dict = get_busroute_info()

    # 버스번호 정렬 (숫자 오름차순)
    sorted_busnos = sorted(busnos, key=lambda b: int(b))

    # 시(hour)별 그룹: {hour_str: [(minute_str, busno_str), ...]}
    schedules_by_hour: dict[str, list[tuple[str, str]]] = {}

    for busno in sorted_busnos:
        deps = departure_dict.get(busno, [])
        if not deps:
            continue
        departure = deps[0]  # F08: 첫 번째 출발지만 사용
        try:
            times = timetable_provider(busno, weekday, departure)
        except (FileNotFoundError, KeyError):
            continue
        for t in times:
            hour_str = t[:2]
            minute_str = t[3:]
            if hour_str not in schedules_by_hour:
                schedules_by_hour[hour_str] = []
            schedules_by_hour[hour_str].append((minute_str, busno))

    # hour 오름차순, 각 hour 내 minute 오름차순 정렬
    timetable_rows: list[TimetableHourRow] = []
    for hour_str in sorted(schedules_by_hour.keys()):
        entries_raw = schedules_by_hour[hour_str]
        # minute 오름차순 정렬
        entries_sorted = sorted(entries_raw, key=lambda x: int(x[0]))
        departures: list[DepartureEntry] = [
            DepartureEntry(minute=minute_str, busno=busno_str)
            for minute_str, busno_str in entries_sorted
        ]
        timetable_rows.append(TimetableHourRow(hour=hour_str, departures=departures))

    is_empty = len(timetable_rows) == 0

    return FullTimetableSnapshot(
        current_time=f"{now_h:02d}:{now_m:02d}",
        weekday_str=weekday_label,
        selected_day=weekday,
        bus_legend=sorted_busnos,
        timetable_rows=timetable_rows,
        is_empty=is_empty,
    )
