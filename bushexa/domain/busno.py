"""W6 — 버스번호별 시간표 도메인 서비스.

F02 §4.4 구현: bus/day/dep 선택으로 Hour/Minute 구조 시간표 반환.
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

class TimetableHourRow(TypedDict):
    hour: str       # "HH" 형식
    minutes: str    # "MM, MM, MM" 형식 (쉼표 구분)


@dataclass(frozen=True)
class BusnoTimetable:
    current_time: str               # "HH:MM"
    weekday_str: str                # WEEKDAY_STR[weekday]
    busnos: list[str]               # 전체 버스번호 목록
    selected_bus: str               # 현재 선택된 버스번호
    day_options: list[str]          # ["Weekday", "Saturday", "Sunday/Holiday"]
    selected_day: int               # 0, 1, 2
    terminals: list[str]            # 선택된 버스의 출발지 목록
    selected_dep: str               # 현재 선택된 출발지
    timetable_rows: list[TimetableHourRow]  # 빈 리스트이면 데이터 없음
    warning: str | None             # 경고 메시지. 없으면 None.


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DAY_OPTIONS = ["Weekday", "Saturday", "Sunday/Holiday"]


def _times_to_hour_rows(times: list[str]) -> list[TimetableHourRow]:
    """"HH:MM" 목록 → Hour/Minute 행 구조로 변환."""
    hour_map: dict[str, list[str]] = {}
    for t in times:
        h = t[:2]
        m = t[3:]
        hour_map.setdefault(h, []).append(m)
    result: list[TimetableHourRow] = []
    for h in sorted(hour_map.keys()):
        minutes_list = sorted(hour_map[h])
        result.append(TimetableHourRow(hour=h, minutes=", ".join(minutes_list)))
    return result


# ---------------------------------------------------------------------------
# W6 public function
# ---------------------------------------------------------------------------

def get_busno_page_data(
    bus: str | None,
    day: int | None,
    dep: str | None,
    clock: Clock,
    *,
    timetable_provider: Callable[[str, int, str], list[str]],
    holiday_set: set[str] | None = None,
) -> BusnoTimetable:
    """버스번호별 시간표 페이지 컨텍스트를 반환한다.

    Parameters
    ----------
    bus : str | None
        버스 번호 문자열. None이면 busnos[0]으로 기본값.
    day : int | None
        요일 인덱스 (0=평일, 1=토, 2=일/공휴일). None이면 현재 KST 요일.
    dep : str | None
        출발지 문자열. None이면 해당 버스 첫 번째 출발지.
    clock : Clock
        시각 공급자.
    timetable_provider :
        Callable[[busno, weekday, departure], list[str]].
    holiday_set : set[str] | None
        공휴일 YYYYMMDD 문자열 집합. None이면 빈 set(공휴일 없음)으로 처리.
    """
    now = clock.now()
    now_h, now_m = now.hour, now.minute
    warning: str | None = None

    busnos, departure_dict = get_busroute_info()

    # bus 검증 및 기본값
    if bus is None or bus not in busnos:
        if bus is not None:
            warning = f"유효하지 않은 버스번호: {bus!r}. 기본값으로 변경."
        bus = busnos[0] if busnos else ""

    # day 검증 및 기본값
    if day is None:
        day = get_weekday(now, holiday_set or set(), clock=clock)
    elif day not in (0, 1, 2):
        day = 0

    terminals = departure_dict.get(bus, [])

    # dep 검증 및 기본값
    if dep is None or dep not in terminals:
        if dep is not None and terminals:
            warning = (warning or "") + f" 유효하지 않은 출발지: {dep!r}. 첫 번째 출발지로 변경."
        dep = terminals[0] if terminals else ""

    # 시간표 조회
    timetable_rows: list[TimetableHourRow] = []
    if bus and dep:
        try:
            times = timetable_provider(bus, day, dep)
            timetable_rows = _times_to_hour_rows(times)
        except (FileNotFoundError, KeyError) as exc:
            warning = (warning or "") + f" 시간표 파일을 찾을 수 없습니다: {exc}"

    weekday_label = WEEKDAY_STR.get(day, str(day))

    return BusnoTimetable(
        current_time=f"{now_h:02d}:{now_m:02d}",
        weekday_str=weekday_label,
        busnos=busnos,
        selected_bus=bus,
        day_options=_DAY_OPTIONS,
        selected_day=day,
        terminals=terminals,
        selected_dep=dep,
        timetable_rows=timetable_rows,
        warning=warning.strip() if warning else None,
    )
