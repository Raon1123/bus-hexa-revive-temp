"""W3 — UNIST 버스 정보 카드 도메인 서비스.

F07 §4.4 구현: via 노선(513) 라이브 + UNIST 출발 노선 시간표 기반.
결함 수정:
 - 중복 API 호출 제거: live 데이터를 1회만 fetch해 재사용 (F07 결함).
 - IndexError 방어: 시간표가 적을 때 bounds 검사 수행 (F07 결함).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Literal

from bushexa.data.constants import ROUTEID, UNIST_VIA_STOP_ID, WEEKDAY_STR
from bushexa.time_utils import Clock, get_weekday


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CardEntry:
    text: str                              # 표시 문자열
    source: Literal["live", "timetable"]   # 데이터 출처
    # 렌더 계층 번역용 구조 값(text 는 한국어 폴백). live: stop+seconds, timetable: time.
    stop: str = ""
    seconds: int | None = None
    time: str = ""


@dataclass(frozen=True)
class BusCard:
    busno: str                # 노선번호 문자열
    direction: str            # 목적지 + 부가설명
    entries: list[CardEntry]  # 최대 visualize(=2)개 항목
    is_last_bus: bool         # entries가 비어 있으면 True


@dataclass
class UnistBoardSnapshot:
    cards: list[BusCard]      # via 카드(경유 기반) + from 카드(시간표 기반) 순서
    bis_error: bool           # BIS API 호출 실패 시 True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_future(t: str, now_h: int, now_m: int) -> bool:
    """"HH:MM" 문자열이 현재 시각(h, m) 이후인지 확인."""
    h, m = int(t[:2]), int(t[3:])
    return (h > now_h) or (h == now_h and m >= now_m)


def _get_route_id(busno: str, departure: str) -> str | None:
    """busno + departure로 ROUTEID에서 route_id를 찾는다."""
    for rid, (bno, _terminal, dep, _stops) in ROUTEID.items():
        if bno == busno and dep == departure:
            return rid
    return None


def _build_via_card(
    busno: str,
    departure: str,
    direction: str,
    live_buses: list,  # list[Arrival]
    now_h: int,
    now_m: int,
    timetable_provider: Callable[[str, int, str], list[str]],
    weekday: int,
    visualize: int = 2,
) -> BusCard:
    """경유 정류소 기반 via 카드 생성. live 우선, 부족분은 시간표로 채움."""
    entries: list[CardEntry] = []

    # live 데이터에서 해당 노선 매칭
    route_id = _get_route_id(busno, departure)
    if route_id is not None:
        for arrival in live_buses:
            if len(entries) >= visualize:
                break
            if arrival.route_id == route_id:
                secs = arrival.arrival_time
                mins, secs_rem = divmod(secs, 60)
                text = f"{arrival.present_stop} {mins}분{secs_rem}초"
                entries.append(CardEntry(
                    text=text, source="live",
                    stop=arrival.present_stop, seconds=secs,
                ))

    # 부족분을 시간표로 채움
    if len(entries) < visualize:
        try:
            times = timetable_provider(busno, weekday, departure)
        except (FileNotFoundError, KeyError):
            times = []
        future_times = [t for t in times if _is_future(t, now_h, now_m)]
        for t in future_times:
            if len(entries) >= visualize:
                break
            entries.append(CardEntry(text=f"{t} 출발 예정", source="timetable", time=t))

    is_last_bus = len(entries) == 0
    return BusCard(busno=busno, direction=direction, entries=entries, is_last_bus=is_last_bus)


def _build_from_card(
    busno: str,
    departure: str,
    direction: str,
    now_h: int,
    now_m: int,
    timetable_provider: Callable[[str, int, str], list[str]],
    weekday: int,
    visualize: int = 2,
) -> BusCard:
    """UNIST 출발 노선 카드를 시간표만으로 생성. API 호출 없음."""
    entries: list[CardEntry] = []
    try:
        times = timetable_provider(busno, weekday, departure)
    except (FileNotFoundError, KeyError):
        times = []
    future_times = [t for t in times if _is_future(t, now_h, now_m)]
    # F07 IndexError 결함 수정: bounds 검사 후 슬라이스
    for t in future_times[:visualize]:
        entries.append(CardEntry(text=f"{t} 출발 예정", source="timetable", time=t))

    is_last_bus = len(entries) == 0
    return BusCard(busno=busno, direction=direction, entries=entries, is_last_bus=is_last_bus)


# ---------------------------------------------------------------------------
# W3 public function
# ---------------------------------------------------------------------------

def get_unist_board_data(
    clock: Clock,
    *,
    client,
    timetable_provider: Callable[[str, int, str], list[str]],
    holiday_set: frozenset[str] | set[str] = frozenset(),
    visualize: int = 2,
) -> UnistBoardSnapshot:
    """UNIST 버스 카드 그리드 데이터를 반환한다.

    Parameters
    ----------
    clock : Clock
        시각 공급자.
    client :
        UlsanBisClient 또는 mock. fetch_arrivals(stop_id) 메서드 제공.
    timetable_provider :
        Callable[[busno, weekday, departure], list[str]].
    holiday_set : frozenset[str] | set[str]
        공휴일 YYYYMMDD 문자열 집합. get_weekday에 전달해 공휴일 요일 코드를 결정한다.
        리뷰 #4 수정: 기존 코드는 이 파라미터를 받지 않아 공휴일에도 평일(0) 코드를
        사용했다(/board·/busno·/timetable은 모두 holiday_set을 전달).
    visualize : int
        카드당 최대 항목 수 (기본 2).

    Notes
    -----
    F07 결함 수정: crawl_busstop(live fetch)을 1회만 호출해 모든 카드에 재사용한다.
    """
    now = clock.now()
    # 리뷰 #4 수정: holiday_set을 get_weekday에 전달해 공휴일에 weekday=2(일/공휴일)를 반환한다.
    weekday = get_weekday(now, holiday_set, clock=clock)
    now_h, now_m = now.hour, now.minute

    # F07 결함 수정: live 데이터를 1회만 fetch (via 정류소 = constants.UNIST_VIA_STOP_ID, E7)
    bis_error = False
    try:
        live_buses = client.fetch_arrivals(UNIST_VIA_STOP_ID)
    except Exception:
        live_buses = []
        bis_error = True

    # 노선 분류: via vs from (F07 §2.3 분류 기준)
    # via: UNIST가 departure가 아닌 노선 = 513 양방향 (dep=덕하, dep=삼남)
    #      → 경유 정류소 실시간 데이터 사용
    # from: UNIST가 departure인 노선 = 713/743/753/1115 UNIST→명촌/꽃바위
    #       → 시간표만 사용
    # 513 양방향(2개) + UNIST 출발 4개 = 6개 카드
    via_cards: list[BusCard] = []
    from_cards: list[BusCard] = []

    seen_keys: set[tuple[str, str]] = set()
    for route_id, (busno, terminal, departure, _stops) in ROUTEID.items():
        key = (busno, departure)
        if key in seen_keys:
            continue
        seen_keys.add(key)

        if departure == "UNIST":
            # UNIST 출발 노선 → from 카드 (시간표 전용, API 호출 없음)
            from_cards.append(_build_from_card(
                busno=busno,
                departure=departure,
                direction=terminal,
                now_h=now_h,
                now_m=now_m,
                timetable_provider=timetable_provider,
                weekday=weekday,
                visualize=visualize,
            ))
        elif UNIST_VIA_STOP_ID in _stops:
            # via 정류소를 경유하는 노선(현재 513 양방향) → via 카드 (live 우선)
            # E7: busno "513" 하드코딩 대신 ROUTEID stop_ids 데이터로 분류
            via_cards.append(_build_via_card(
                busno=busno,
                departure=departure,
                direction=terminal,
                live_buses=live_buses,
                now_h=now_h,
                now_m=now_m,
                timetable_provider=timetable_provider,
                weekday=weekday,
                visualize=visualize,
            ))
        # 713/743/753/1115의 명촌/꽃바위 출발 routes는 보드에 포함하지 않음

    # via 2 + from 4 = 6 카드 (F07 §4.4: "via 1 + from 5"는 다른 분류 방식)
    # 실제로는 513 양방향(2) + UNIST 출발 4개(713/743/753/1115) = 6개
    cards = via_cards[:2] + from_cards[:4]

    return UnistBoardSnapshot(cards=cards, bis_error=bis_error)
