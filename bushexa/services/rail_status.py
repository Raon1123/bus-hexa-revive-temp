"""``rail_timetable.json`` 구간별 상태 요약과 경고 — 관리자 화면용(읽기 전용)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from bushexa.data.constants import (
    METRO_DAY_TYPES,
    METRO_QUERIES,
    METRO_STATIONS,
    RAIL_PAIRS,
    RAIL_STATIONS,
    RAIL_STOP_CANDIDATES,
)
from bushexa.services.rail_timetable import metro_key, pair_key


@dataclass(frozen=True)
class PairStatus:
    label: str                      # "울산→서울"
    key: str
    dates: int                      # 저장된 날짜 수
    first: str | None
    last: str | None
    today_trains: int | None        # 오늘 편수(없으면 None)
    suspect: tuple[str, ...]        # 편수 급감 날짜
    wants_stops: bool               # 정차역 후보가 있는 구간
    stop_dates: tuple[str, ...]     # 정차역을 한 편이라도 아는 날짜
    stops_unknown_today: int        # 오늘 정차역을 모르는 편수
    fetched_at: str | None          # 가장 최근 저장 시각
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class MetroStatus:
    label: str
    key: str
    count: int | None               # 시각 수(없으면 None)
    fetched_at: str | None


@dataclass(frozen=True)
class RailStatus:
    updated_at: str | None
    last_success_date: str | None
    ok_today: bool
    pairs: list[PairStatus] = field(default_factory=list)
    metro: list[MetroStatus] = field(default_factory=list)
    metro_updated_at: str | None = None
    metro_last_success_date: str | None = None


def _name(station_id: str) -> str:
    return RAIL_STATIONS.get(station_id, station_id)


def summarize_rail_store(store: dict, today: date) -> RailStatus:
    trains = store.get("trains") or {}
    pairs = trains.get("pairs") or {}
    today_s = today.isoformat()
    out: list[PairStatus] = []
    for dep_id, arr_id in RAIL_PAIRS:
        key = pair_key(dep_id, arr_id)
        dates = (pairs.get(key) or {}).get("dates") or {}
        ds = sorted(d for d in dates if d >= today_s)
        entry = dates.get(today_s) or {}
        rows = entry.get("trains") or []
        wants = (dep_id, arr_id) in RAIL_STOP_CANDIDATES
        stop_dates = tuple(d for d in ds
                           if any(isinstance(t, dict) and t.get("stops") is not None
                                  for t in dates[d].get("trains") or []))
        unknown_today = sum(1 for t in rows if isinstance(t, dict) and t.get("stops") is None) if wants else 0
        warnings = []
        if not ds:
            warnings.append("저장된 날짜 없음 — 재수집 필요")
        elif today_s not in dates:
            warnings.append("오늘 열차 없음")
        suspect = tuple(d for d in ds if dates[d].get("suspect"))
        if suspect:
            warnings.append(f"편수 급감 {len(suspect)}일")
        if wants and ds and not stop_dates:
            warnings.append("정차역 정보 없음")
        fetched = max((dates[d].get("fetched_at") or "" for d in ds), default="") or None
        out.append(PairStatus(
            label=f"{_name(dep_id)}→{_name(arr_id)}", key=key, dates=len(ds),
            first=ds[0] if ds else None, last=ds[-1] if ds else None,
            today_trains=len(rows) if today_s in dates else None, suspect=suspect,
            wants_stops=wants, stop_dates=stop_dates, stops_unknown_today=unknown_today,
            fetched_at=fetched, warnings=tuple(warnings),
        ))
    metro = store.get("metro") or {}
    schedules = metro.get("schedules") or {}
    mout = []
    for station_id, direction in METRO_QUERIES:
        for day_type in METRO_DAY_TYPES:
            key = metro_key(station_id, direction, day_type)
            entry = schedules.get(key)
            mout.append(MetroStatus(
                label=f"{METRO_STATIONS.get(station_id, station_id)} {direction} {day_type}", key=key,
                count=len(entry.get("times") or []) if isinstance(entry, dict) else None,
                fetched_at=entry.get("fetched_at") if isinstance(entry, dict) else None,
            ))
    return RailStatus(
        updated_at=trains.get("updated_at"), last_success_date=trains.get("last_success_date"),
        ok_today=trains.get("last_success_date") == today_s, pairs=out, metro=mout,
        metro_updated_at=metro.get("updated_at"), metro_last_success_date=metro.get("last_success_date"),
    )
