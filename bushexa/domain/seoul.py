"""서울 가는 길(/seoul) 뷰모델 — 513 → 울산역 → KTX 서울역·수서역 (순수 함수).

513 UNIST 통과는 실시간 도착만 쓰고, 실시간이 없으면 덕하 출발 시각을 라벨과 함께 따로
돌려준다(timetable UX 결정 D1). 발차 안내판은 ``rail_board.board_trains`` 로 만든다.
"""
from __future__ import annotations

import dataclasses
import datetime
from dataclasses import dataclass, field
from typing import Callable

from bushexa.data.constants import (
    BUSAN_513_ORIGIN,
    BUSAN_513_ROUTE_ID,
    BUSAN_KTX_TRANSFER_MIN,
    BUSAN_UNIST_TO_ULSAN_STATION_MIN,
)
from bushexa.domain.rail_board import BoardTrain, board_trains
from bushexa.domain.rail_match import service_minutes

BOARD_ROWS = 12
DESTS = ("all", "seoul", "suseo")


@dataclass(frozen=True)
class LiveBus:
    eta_min: int
    unist_at: str
    station_at: str
    ready_at: datetime.datetime      # 울산역 도착 + 환승 여유
    seoul: BoardTrain | None
    suseo: BoardTrain | None


@dataclass(frozen=True)
class SeoulSnapshot:
    now: str
    dest: str
    live: list[LiveBus] = field(default_factory=list)
    origin_513: list[str] = field(default_factory=list)
    board: list[BoardTrain] = field(default_factory=list)
    states: dict = field(default_factory=dict)          # {"서울": ok/suspect/missing, "수서": …}
    errors: list[str] = field(default_factory=list)


def build_seoul_snapshot(
    now: datetime.datetime,
    weekday: int,
    *,
    timetable_provider: Callable,
    seoul_day: dict | None,
    suseo_day: dict | None,
    seoul_ids: tuple[str, str],
    suseo_ids: tuple[str, str],
    unist_arrivals: list | None = None,
    dest: str = "all",
    rows: int = BOARD_ROWS,
) -> SeoulSnapshot:
    """``seoul_ids``/``suseo_ids`` 는 (출발역, 도착역) TAGO ID — 정차역 띠 후보를 고르는 데 쓴다."""
    dest = dest if dest in DESTS else "all"
    errors: list[str] = []
    seoul, seoul_state = board_trains(seoul_day, now, *seoul_ids)
    suseo, suseo_state = board_trains(suseo_day, now, *suseo_ids)

    live: list[LiveBus] = []
    for a in sorted((a for a in (unist_arrivals or []) if a.route_id == BUSAN_513_ROUTE_ID),
                    key=lambda a: a.arrival_time):
        unist_at = now + datetime.timedelta(seconds=a.arrival_time)
        station_at = unist_at + datetime.timedelta(minutes=BUSAN_UNIST_TO_ULSAN_STATION_MIN)
        ready = station_at + datetime.timedelta(minutes=BUSAN_KTX_TRANSFER_MIN)
        live.append(LiveBus(
            eta_min=max(0, round(a.arrival_time / 60)),
            unist_at=unist_at.strftime("%H:%M"), station_at=station_at.strftime("%H:%M"),
            ready_at=ready,
            seoul=next((t for t in seoul if t.dep_at >= ready), None),
            suseo=next((t for t in suseo if t.dep_at >= ready), None),
        ))

    try:
        origin = list(timetable_provider("513", weekday, BUSAN_513_ORIGIN))
    except (FileNotFoundError, KeyError) as exc:
        errors.append(f"513 시간표 없음: {exc}")
        origin = []
    now_min = service_minutes(now.strftime("%H:%M:%S"))
    origin_513 = [t for t in origin if service_minutes(f"{t}:00") >= now_min][:5]

    board = {"all": seoul + suseo, "seoul": seoul, "suseo": suseo}[dest]
    board.sort(key=lambda b: b.dep_at)
    board = board[:rows]
    if live:
        first_ready = live[0].ready_at
        hit = next((t for t in board if t.dep_at >= first_ready), None)
        board = [dataclasses.replace(t, connect=True) if t is hit else t for t in board]

    return SeoulSnapshot(
        now=now.strftime("%H:%M"), dest=dest, live=live[:4], origin_513=origin_513,
        board=board, states={"서울": seoul_state, "수서": suseo_state}, errors=errors,
    )
