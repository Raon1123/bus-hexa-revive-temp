"""W1a + W1b — 출발 게시판 도메인 서비스.

F01 §4.4 구현: live 도착(UlsanBisClient) + 시간표(timetable_provider)를 합성.
모든 시각은 주입된 clock 기준 KST.
"""
from __future__ import annotations

import datetime
import re
from dataclasses import dataclass, replace
from typing import Callable, Literal, Protocol

from bushexa.data.constants import ROUTEID, STOP_IDS, VIA_STOPS, WEEKDAY_STR
from bushexa.time_utils import Clock, KSTClock, get_weekday

# ---------------------------------------------------------------------------
# 리뷰 E4(중복 제거): UNIST를 종점으로 갖는 버스번호 집합
#
# ROUTEID는 모듈 임포트 시 고정되는 상수이므로 lazy 함수 대신 모듈 레벨에서 한 번만
# 계산한다. _build_timetable_rows·_build_live_rows 두 곳의 동일 컴프리헨션 2벌을 대체.
# ---------------------------------------------------------------------------
_UNIST_BUSNOS: frozenset[str] = frozenset(
    b for (b, term, dep, _ids) in ROUTEID.values()
    if dep == "UNIST" or "UNIST" in term
)


# ---------------------------------------------------------------------------
# 경유지(via) 문자열 — 모든 행에 경유지가 채워지도록 보장
# ---------------------------------------------------------------------------

_PAREN_RE = re.compile(r"\s*\([^)]*\)")


def _clean_stop_name(name: str) -> str:
    """정류장명에서 괄호 주석((시내)/(UNIST)/(경유)/(기점)/(종점) 등)을 제거."""
    return _PAREN_RE.sub("", name).strip()


def _route_via_string(route_id: str) -> str:
    """노선 정류장 시퀀스(ROUTEID[route_id][3])를 정류장명으로 변환해 ' - '로 연결.

    curated VIA_STOPS에 없는 방향(예: UNIST 방면)도 경유지가 항상 표시되도록 하는 fallback.
    중복 명칭은 제거한다.
    """
    entry = ROUTEID.get(route_id)
    if not entry:
        return ""
    stop_ids = entry[3]
    names: list[str] = []
    seen: set[str] = set()
    for sid in stop_ids:
        nm = _clean_stop_name(STOP_IDS.get(sid, ""))
        if nm and nm not in seen:
            seen.add(nm)
            names.append(nm)
    return " - ".join(names)


def _via_for(
    route_id: str,
    busno: str,
    terminal: str,
    overrides: dict[str, dict[str, str]] | None = None,
) -> str:
    """경유지 문자열을 반환한다.

    1순위: 운영자 override(admin 편집, via_overrides.json) — 목적지 키.
    2순위: 목적지(terminal) 키로 curated VIA_STOPS 조회(짧고 깔끔한 손질 문자열).
    3순위: 위 둘 다 없으면 노선 실제 정류장 목록 기반 fallback(항상 완전).
    """
    via_key = terminal.split()[0] if terminal else ""
    if overrides:
        ov = overrides.get(busno, {}).get(via_key, "")
        if ov:
            return ov
    curated = VIA_STOPS.get(busno, {}).get(via_key, "")
    if curated:
        return curated
    return _route_via_string(route_id)


def via_default(route_id: str, busno: str, terminal: str) -> str:
    """override를 제외한 경유지 기본값(curated VIA_STOPS > 노선 정류장 fallback).

    admin 경유지 편집기가 '현재 기본값'을 표시할 때 사용한다(override 레이어는 편집기가 별도 관리).
    """
    return _via_for(route_id, busno, terminal, None)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BoardRow:
    arrival_time: str           # "HH:MM"
    bus_number: str             # "513", "713" 등
    present: str                # 현재 위치 + 상태 문자열
    via_string: str             # 경유지 설명
    source: Literal["live", "timetable"]
    arrival_minutes: int        # 정렬·비교용 (현재 시각 기준 분수)
    terminal: str = ""          # 목적지(방면) 문자열 — 동일 (bus_number, terminal) 쌍의 dedup용
    rank: Literal["FIRST", "SECOND", ""] = ""   # W1b: 가장 이른 2건 마킹

    @property
    def short_terminal(self) -> str:
        """방면 축약명 — "삼남 (울산역) 방면" → "삼남".

        좁은 화면(휴대전화)에서 행선 칸이 접혀 노선 번호만 보일 때, 양방향 운행하는
        513 등의 방향을 한눈에 구분할 수 있도록 첫 토큰만 노출하는 용도.
        """
        return self.terminal.split()[0] if self.terminal else ""


@dataclass
class BoardSnapshot:
    current_time: str           # "HH:MM"
    weekday_str: str            # WEEKDAY_STR[weekday]
    rows: list[BoardRow]        # 도착시각 오름차순, 최대 10개
    error: str | None           # BIS API 오류 시 메시지
    is_last_bus: bool           # 운행 종료 여부


# ---------------------------------------------------------------------------
# W1a helpers
# ---------------------------------------------------------------------------

def _hhmm_to_minutes(t: str, now_h: int, now_m: int) -> int:
    """"HH:MM" 문자열 → 현재 시각(h, m) 기준 앞으로 몇 분 후(음수 = 지났음)."""
    h, m = int(t[:2]), int(t[3:])
    return (h - now_h) * 60 + (m - now_m)


def _build_timetable_rows(
    weekday: int,
    now_h: int,
    now_m: int,
    timetable_provider: Callable[[str, int, str], list[str]],
    via_overrides: dict[str, dict[str, str]] | None = None,
) -> list[BoardRow]:
    """시간표에서 현재 시각 이후 출발편만 BoardRow로 변환.

    UNIST '출발' 게시판이므로, UNIST를 종점으로 갖는 노선(713/743/753/1115)은
    **UNIST에서 출발하는 방향(departure == "UNIST")만** 표시하고 UNIST로 들어오는
    방향("UNIST 방면")은 제외한다(레거시 departure_board.py와 동일). UNIST를 종점으로
    갖지 않고 경유만 하는 513은 양방향 모두 표시한다.
    """
    rows: list[BoardRow] = []
    for route_id, (busno, terminal, departure, _stop_ids) in ROUTEID.items():
        # UNIST 노선의 'UNIST 도착(=UNIST 방면)' 방향은 출발 게시판에서 제외
        # 리뷰 E4: 모듈 레벨 _UNIST_BUSNOS 사용 (ROUTEID 고정 상수 → lazy 불필요)
        if busno in _UNIST_BUSNOS and departure != "UNIST":
            continue
        try:
            times = timetable_provider(busno, weekday, departure)
        except (FileNotFoundError, KeyError):
            continue
        via_str = _via_for(route_id, busno, terminal, via_overrides)
        for t in times:
            mins = _hhmm_to_minutes(t, now_h, now_m)
            if mins < 0:
                continue  # 이미 지난 출발편 제외
            rows.append(BoardRow(
                arrival_time=t,
                bus_number=busno,
                present=f"{departure} 출발 예정",
                via_string=via_str,
                source="timetable",
                arrival_minutes=mins,
                terminal=terminal,  # 방면 문자열 (dedup용)
            ))
    return rows


def _build_live_rows(
    arrivals: list,  # list[Arrival]
    now_h: int,
    now_m: int,
    via_overrides: dict[str, dict[str, str]] | None = None,
) -> list[BoardRow]:
    """BIS API 도착 목록 → BoardRow. ROUTEID에 없는 route_id는 건너뜀.

    시간표와 동일하게 UNIST '출발' 방향만 남긴다(_build_timetable_rows 참고). 조회 정류소
    196040234에는 사실상 513만 정차하지만, UNIST 종점 노선의 'UNIST 방면'(도착) 차량이
    라이브에 섞여 들어오면 출발 게시판 취지에 어긋나므로 동일 규칙으로 방어한다.
    """
    rows: list[BoardRow] = []
    for arrival in arrivals:
        if arrival.route_id not in ROUTEID:
            continue
        busno, terminal, departure, _stop_ids = ROUTEID[arrival.route_id]
        # 리뷰 E4: 모듈 레벨 _UNIST_BUSNOS 사용 (ROUTEID 고정 상수 → lazy 불필요)
        if busno in _UNIST_BUSNOS and departure != "UNIST":
            continue
        arrival_secs = arrival.arrival_time
        arrival_mins = arrival_secs // 60
        # 도착 예상 시각 계산
        now_total_mins = now_h * 60 + now_m
        abs_arrival_mins = now_total_mins + arrival_mins
        arr_h = (abs_arrival_mins // 60) % 24
        arr_m = abs_arrival_mins % 60
        arrival_time_str = f"{arr_h:02d}:{arr_m:02d}"
        via_str = _via_for(arrival.route_id, busno, terminal, via_overrides)
        rows.append(BoardRow(
            arrival_time=arrival_time_str,
            bus_number=busno,
            present=f"{arrival.present_stop} 출발",
            via_string=via_str,
            source="live",
            arrival_minutes=arrival_mins,
            terminal=terminal,  # 방면 문자열 (dedup용)
        ))
    return rows


# ---------------------------------------------------------------------------
# W1a public function
# ---------------------------------------------------------------------------

def get_board_data(
    stop_id: str,
    clock: Clock,
    *,
    client,
    timetable_provider: Callable[[str, int, str], list[str]],
    via_overrides: dict[str, dict[str, str]] | None = None,
    holiday_set: set[str] | None = None,
) -> BoardSnapshot:
    """출발 게시판 데이터를 조회·병합해 BoardSnapshot을 반환한다.

    Parameters
    ----------
    stop_id : str
        BIS API 조회 대상 정류소 ID.
    clock : Clock
        시각 공급자 (테스트 시 FakeClock 주입).
    client :
        UlsanBisClient 또는 동일 인터페이스 mock. fetch_arrivals(stop_id) 메서드 제공.
    timetable_provider :
        Callable[[busno, weekday, departure], list[str]]. get_timetable 래퍼.
    holiday_set : set[str] | None
        공휴일 YYYYMMDD 문자열 집합. None이면 빈 set(공휴일 없음)으로 처리.
    """
    now = clock.now()
    weekday = get_weekday(now, holiday_set or set(), clock=clock)
    now_h, now_m = now.hour, now.minute

    # 1) 시간표 기반 rows
    timetable_rows = _build_timetable_rows(weekday, now_h, now_m, timetable_provider, via_overrides)

    # 2) Live 도착 fetch
    error: str | None = None
    live_rows: list[BoardRow] = []
    try:
        arrivals = client.fetch_arrivals(stop_id)
        live_rows = _build_live_rows(arrivals, now_h, now_m, via_overrides)
    except Exception as exc:
        error = f"BIS API 오류: {exc}"

    # 3) 병합: live가 있는 (bus_number, terminal) 쌍에서 시간표 제거 → live로 대체
    # F01 §6.1: "동일 (bus_number, terminal) 조합의 시간표 행을 제거하고 live 행으로 대체"
    live_keys = {(r.bus_number, r.terminal) for r in live_rows}
    merged = live_rows + [
        r for r in timetable_rows
        if (r.bus_number, r.terminal) not in live_keys
    ]
    # 리뷰 E5: 이 시점의 merged.sort()는 불필요 — 제거.
    # 증명: merge_live_rows(:306)가 항상 sorted(rows, key=(arrival_minutes, bus_number))로
    # 재정렬한다. K1=(arrival_minutes)는 K2=(arrival_minutes, bus_number)의 prefix이므로
    # K1 사전 정렬 결과와 K2 재정렬 결과는 항상 동일하다. merged의 유일한 소비자가
    # merge_live_rows이므로 사전 정렬은 완전한 no-op. merge_live_rows를 거치지 않는
    # merged 경로는 이 함수 내에 없음(is_last_bus는 rows_final 길이 기반).

    # 4) FIRST/SECOND 마킹
    ranked = merge_live_rows(merged)
    rows_final = ranked[:10]

    is_last_bus = len(rows_final) == 0

    weekday_label = WEEKDAY_STR.get(weekday, str(weekday))
    return BoardSnapshot(
        current_time=f"{now_h:02d}:{now_m:02d}",
        weekday_str=weekday_label,
        rows=rows_final,
        error=error,
        is_last_bus=is_last_bus,
    )


# ---------------------------------------------------------------------------
# W1b public function
# ---------------------------------------------------------------------------

def merge_live_rows(rows: list[BoardRow]) -> list[BoardRow]:
    """출발 '시각' 기준으로 FIRST/SECOND를 마킹한다.

    동시에 출발하는(같은 시각) 버스는 **모두 함께 FIRST**, 그 다음으로 이른 시각의 버스는
    **모두 함께 SECOND**가 된다(사용자 요구: "동시에 출발하는건 동시에 FIRST/SECOND").

    Parameters
    ----------
    rows : list[BoardRow]
        BoardRow 목록. 정렬 여부 무관 — 내부에서 (arrival_minutes, bus_number) 기준으로
        재정렬하므로 호출자가 사전 정렬할 필요 없다(리뷰 E5 사전 정렬 제거).

    Returns
    -------
    list[BoardRow]
        rank 필드가 채워진 새 BoardRow 목록.
    """
    if not rows:
        return []

    # 표시 정렬: arrival_minutes 오름차순 → bus_number 오름차순
    sorted_rows = sorted(rows, key=lambda r: (r.arrival_minutes, r.bus_number))

    # 출발 시각(HH:MM)의 distinct 순서 — 가장 이른 시각=FIRST, 두 번째 distinct 시각=SECOND
    distinct_times: list[str] = []
    for r in sorted_rows:
        if r.arrival_time not in distinct_times:
            distinct_times.append(r.arrival_time)
    rank_for: dict[str, Literal["FIRST", "SECOND", ""]] = {}
    if distinct_times:
        rank_for[distinct_times[0]] = "FIRST"
    if len(distinct_times) > 1:
        rank_for[distinct_times[1]] = "SECOND"

    return [replace(r, rank=rank_for.get(r.arrival_time, "")) for r in sorted_rows]
