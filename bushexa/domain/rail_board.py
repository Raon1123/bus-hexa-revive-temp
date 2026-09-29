"""역 발차 안내판(난카이 난바역 스타일) 행 만들기 — 순수 함수.

저장된 날짜별 열차(``rail_timetable.trains_on`` 결과)를 "지금 이후" 행으로 바꾸고,
정차역 띠(strip)를 만든다. 띠는 구간의 정차역 후보(``RAIL_STOP_CANDIDATES``) 전체를 운행
순서로 늘어놓고 선다/통과를 표시한다. 정차역을 모르는 열차(조회 실패·먼 날짜)는 띠가 None 이다
— 통과로 그리지 않는다.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass

from bushexa.data.constants import (
    RAIL_SPECIAL_STOPS,
    RAIL_STATIONS,
    RAIL_STOP_CANDIDATES,
    RAIL_STRIP_LAYOUT,
)

# 이 분 안에 출발하면 "곧 출발"로 깜빡인다.
SOON_MIN = 10


@dataclass(frozen=True)
class StopMark:
    name: str
    time: str | None      # 도착 "HH:MM"(정차) / None(통과)
    stops: bool
    special: bool = False  # 예외적 정차(서대구·수원) — 강조


@dataclass(frozen=True)
class BoardTrain:
    dep: str              # "HH:MM"
    arr: str              # "HH:MM"
    next_day: bool        # 도착이 다음 날
    grade: str
    origin: str
    dest: str
    strip: tuple[StopMark, ...] | None
    minutes_left: int
    soon: bool
    dep_at: datetime.datetime
    connect: bool = False  # 지금 오는 버스로 탈 수 있는 첫 열차
    specials: tuple[str, ...] = ()  # 예외 정차 배지 i18n 키(서대구 정차·수원 경유)


def _strip_candidates(dep_id: str, arr_id: str, stopped: set[str]) -> list[str]:
    """띠에 그릴 후보역(운행 순서). 갈래가 있으면 열차가 서는 역이 있는 갈래만 붙인다."""
    layout = RAIL_STRIP_LAYOUT.get((dep_id, arr_id))
    if not layout:
        return RAIL_STOP_CANDIDATES.get((dep_id, arr_id), [])
    branches = layout["branches"]
    chosen = next((b for b in branches
                   if any(RAIL_STATIONS.get(c, c) in stopped for c in b)), branches[0])
    return layout["trunk"] + chosen


def _strip(dep_id: str, arr_id: str, stops) -> tuple[StopMark, ...] | None:
    if stops is None:
        return None
    by_name = {s.get("name"): s.get("arr") for s in stops}
    marks = []
    for cid in _strip_candidates(dep_id, arr_id, set(by_name)):
        name = RAIL_STATIONS.get(cid, cid)
        marks.append(StopMark(name, by_name.get(name), name in by_name,
                              special=name in by_name and name in RAIL_SPECIAL_STOPS))
    return tuple(marks)


def board_trains(day_entry: dict | None, now: datetime.datetime, dep_id: str, arr_id: str,
                 ) -> tuple[list[BoardTrain], str]:
    """지금 이후 열차 행(출발순, 중련은 한 줄)과 상태(ok/suspect/missing)."""
    if not day_entry or not day_entry.get("trains"):
        return [], "missing"
    out: list[BoardTrain] = []
    seen: set = set()
    for t in day_entry["trains"]:
        try:
            dep = datetime.datetime.fromisoformat(t["dep"])
            arr = datetime.datetime.fromisoformat(t["arr"])
        except (KeyError, ValueError):
            continue
        if dep < now or (dep, arr) in seen:
            continue
        seen.add((dep, arr))
        left = int((dep - now).total_seconds() // 60)
        out.append(BoardTrain(
            dep=dep.strftime("%H:%M"), arr=arr.strftime("%H:%M"),
            next_day=arr.date() > dep.date(), grade=t.get("grade", ""),
            origin=RAIL_STATIONS.get(dep_id, dep_id), dest=RAIL_STATIONS.get(arr_id, arr_id),
            strip=(_strip(dep_id, arr_id, t.get("stops")) if "stops" in t else None)
            if (dep_id, arr_id) in RAIL_STOP_CANDIDATES else (),   # 중간 정차역 후보가 없는 구간(울산→부산)
            minutes_left=left, soon=left <= SOON_MIN, dep_at=dep,
            specials=tuple(RAIL_SPECIAL_STOPS[n] for n in RAIL_SPECIAL_STOPS
                           if any(x.get("name") == n for x in (t.get("stops") or []))),
        ))
    out.sort(key=lambda b: b.dep_at)
    return out, ("suspect" if day_entry.get("suspect") else "ok")
