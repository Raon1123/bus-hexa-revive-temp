"""부산 루트용 철도 시간표 스토어 — ``<data_dir>/rail_timetable.json``.

cache-refresh 워커(와 CLI ``crawl-rail``)만 TAGO 를 호출해 이 파일을 갱신하고, 공개 화면은
이 파일만 읽는다(ADR-010). 두 절로 나뉜다.

- ``trains`` : 날짜별 열차(울산→부산, 태화강→부전; ``RAIL_PAIRS``). 오늘부터 ``days`` 일치.
  TAGO 열차정보는 약 30일 앞까지만 값이 있고, 특정 날짜만 편수가 급감하는 응답이 있다
  (2026-10-13 울산→부산 3편, 다른 날 60편대). 그래서
    · 호출 실패 → 그 날짜의 기존 값 유지(PM-008: 실패로 좋은 캐시를 덮지 않는다)
    · 빈 결과 → 기존 값이 있으면 유지, 없으면 저장하지 않음(없음 = 모름)
    · 기존보다 절반 미만으로 급감 → 기존 값 유지 + 경고
    · 같은 구간 다른 날짜 중앙값의 절반 미만 → 저장하되 ``suspect: true`` (화면이 경고)
- ``metro``  : 동해선 광역전철 역·방향·요일구분별 시간표(``METRO_QUERIES`` × ``METRO_DAY_TYPES``).
  요일구분 시간표라 날짜와 무관하다. 토요일(02)은 비어 있어 읽을 때 03 으로 대체한다.

네트워크 호출은 잠금 밖에서 끝내고, 병합만 ``locked_update_json`` 안에서 한다.
"""
from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from bushexa.data.constants import (
    METRO_DAY_TYPES,
    METRO_QUERIES,
    METRO_SATURDAY_FALLBACK,
    METRO_STATIONS,
    RAIL_PAIRS,
    RAIL_STATIONS,
)
from bushexa.fileio import locked_update_json, read_json
from bushexa.time_utils import Clock, KSTClock, get_weekday

logger = logging.getLogger("bushexa.services.rail_timetable")

# 오늘 포함 수집 일수. TAGO 가 약 30일치를 주므로 여유 있게 2주(연휴 대비).
RAIL_HORIZON_DAYS = 14

# 급감 판정 비율: 새 편수가 기준의 이 비율 미만이면 급감으로 본다.
_DROP_RATIO = 0.5
# 급감 비교를 할 최소 기준 편수(편수가 원래 적은 구간의 오탐 방지).
_DROP_MIN_BASE = 10

def _empty_store() -> dict:
    """새 빈 스토어(중첩 dict 공유 방지를 위해 매번 새로 만든다)."""
    return {"version": 1, "trains": {}, "metro": {}}


def default_rail_path(data_dir) -> Path:
    return Path(data_dir) / "rail_timetable.json"


def pair_key(dep_id: str, arr_id: str) -> str:
    return f"{dep_id}-{arr_id}"


def metro_key(station_id: str, direction: str, day_type: str) -> str:
    return f"{station_id}:{direction}:{day_type}"


@dataclass
class RefreshSummary:
    """갱신 결과 요약. ``failed`` 가 비어 있어야 그날 갱신 완료로 기록된다."""
    stored: list[str] = field(default_factory=list)
    kept: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        return f"저장 {len(self.stored)} · 기존 유지 {len(self.kept)} · 실패 {len(self.failed)}"


def _is_drop(new_count: int, base_count: int) -> bool:
    return base_count >= _DROP_MIN_BASE and new_count < base_count * _DROP_RATIO


def _train_row(t) -> dict:
    return {
        "no": t.train_no, "grade": t.grade,
        "dep": t.dep_at.isoformat(), "arr": t.arr_at.isoformat(),
        "charge": t.adult_charge,
    }


def _mark_suspects(dates: dict) -> None:
    """같은 구간 날짜들의 편수 중앙값 대비 급감한 날짜에 ``suspect`` 를 단다."""
    counts = [len(v.get("trains", [])) for v in dates.values()]
    if len(counts) < 3:
        return
    median = statistics.median(counts)
    for entry in dates.values():
        entry["suspect"] = _is_drop(len(entry.get("trains", [])), median)


# ── 갱신 (워커 전용) ─────────────────────────────────────────────────────────

def refresh_trains(client, path, *, clock: Clock | None = None,
                   days: int = RAIL_HORIZON_DAYS) -> RefreshSummary:
    """``RAIL_PAIRS`` × (오늘..오늘+days-1) 열차를 받아 ``trains`` 절에 병합한다."""
    clock = clock or KSTClock()
    now = clock.now()
    today = now.date()
    targets = [today + timedelta(days=i) for i in range(days)]

    fetched: dict[tuple[str, str], list | Exception] = {}
    for dep_id, arr_id in RAIL_PAIRS:
        for d in targets:
            label = f"{RAIL_STATIONS.get(dep_id, dep_id)}→{RAIL_STATIONS.get(arr_id, arr_id)} {d}"
            try:
                fetched[(pair_key(dep_id, arr_id), d.isoformat())] = client.fetch_trains(dep_id, arr_id, d)
            except Exception as exc:  # 한 날짜 실패가 나머지를 막지 않게(ADR-013)
                logger.warning("열차 시간표 조회 실패(기존 유지) %s: %s", label, exc)
                fetched[(pair_key(dep_id, arr_id), d.isoformat())] = exc

    summary = RefreshSummary()

    def mutate(store):
        store = store if isinstance(store, dict) else _empty_store()
        section = store.setdefault("trains", {})
        pairs = section.setdefault("pairs", {})
        for dep_id, arr_id in RAIL_PAIRS:
            key = pair_key(dep_id, arr_id)
            entry = pairs.setdefault(key, {})
            entry.update(dep_id=dep_id, arr_id=arr_id,
                         dep_name=RAIL_STATIONS.get(dep_id, dep_id),
                         arr_name=RAIL_STATIONS.get(arr_id, arr_id))
            dates = entry.setdefault("dates", {})
            for d in targets:
                ds = d.isoformat()
                label = f"{key} {ds}"
                result = fetched[(key, ds)]
                old = dates.get(ds)
                old_count = len(old.get("trains", [])) if isinstance(old, dict) else 0
                if isinstance(result, Exception):
                    summary.failed.append(label)
                    continue
                if not result:
                    if old_count:
                        logger.warning("열차 시간표 빈 응답 — 기존 %d편 유지: %s", old_count, label)
                    summary.kept.append(label)
                    continue
                if _is_drop(len(result), old_count):
                    logger.warning("열차 편수 급감 %d→%d — 기존 유지: %s", old_count, len(result), label)
                    summary.kept.append(label)
                    continue
                dates[ds] = {"fetched_at": now.isoformat(),
                             "trains": [_train_row(t) for t in result]}
                summary.stored.append(label)
            for ds in [k for k in dates if k < today.isoformat()]:
                del dates[ds]   # 지난 날짜 정리
            _mark_suspects(dates)
        section["updated_at"] = now.isoformat()
        if not summary.failed:
            section["last_success_date"] = today.isoformat()
        return store

    locked_update_json(path, mutate, default=_empty_store())
    return summary


def refresh_metro(client, path, *, clock: Clock | None = None) -> RefreshSummary:
    """``METRO_QUERIES`` × ``METRO_DAY_TYPES`` 역별 시간표를 받아 ``metro`` 절에 병합한다."""
    clock = clock or KSTClock()
    now = clock.now()

    fetched: dict[str, list | Exception] = {}
    for station_id, direction in METRO_QUERIES:
        for day_type in METRO_DAY_TYPES:
            key = metro_key(station_id, direction, day_type)
            try:
                fetched[key] = client.fetch_station_schedule(station_id, day_type, direction)
            except Exception as exc:
                logger.warning("동해선 시간표 조회 실패(기존 유지) %s: %s", key, exc)
                fetched[key] = exc

    summary = RefreshSummary()

    def mutate(store):
        store = store if isinstance(store, dict) else _empty_store()
        section = store.setdefault("metro", {})
        schedules = section.setdefault("schedules", {})
        for station_id, direction in METRO_QUERIES:
            for day_type in METRO_DAY_TYPES:
                key = metro_key(station_id, direction, day_type)
                result = fetched[key]
                old = schedules.get(key)
                old_count = len(old.get("times", [])) if isinstance(old, dict) else 0
                if isinstance(result, Exception):
                    summary.failed.append(key)
                    continue
                if old_count and (not result or _is_drop(len(result), old_count)):
                    logger.warning("동해선 시간표 %d→%d건 급감 — 기존 유지: %s",
                                   old_count, len(result), key)
                    summary.kept.append(key)
                    continue
                schedules[key] = {
                    "station_id": station_id,
                    "station_name": METRO_STATIONS.get(station_id, station_id),
                    "direction": direction, "day_type": day_type,
                    "fetched_at": now.isoformat(),
                    "times": [{"dep": m.dep_time, "arr": m.arr_time,
                               "end_id": m.end_station_id, "end_name": m.end_station_name}
                              for m in result],
                }
                summary.stored.append(key)
        section["updated_at"] = now.isoformat()
        if not summary.failed:
            section["last_success_date"] = now.date().isoformat()
        return store

    locked_update_json(path, mutate, default=_empty_store())
    return summary


def refreshed_today(path, section: str, today: date) -> bool:
    """``section``(trains/metro)이 ``today`` 에 실패 없이 갱신됐는지."""
    store = load_rail_store(path)
    return (store.get(section) or {}).get("last_success_date") == today.isoformat()


# ── 읽기 (공개 화면용, 네트워크 없음) ────────────────────────────────────────

def load_rail_store(path) -> dict:
    return read_json(path, default=_empty_store(), expect=dict,
                     warn_label="철도 시간표", logger=logger)


def trains_on(store: dict, dep_id: str, arr_id: str, day: date) -> dict | None:
    """그날 구간 열차 항목(``trains``·``suspect``·``fetched_at``). 수집된 적 없으면 None."""
    pairs = (store.get("trains") or {}).get("pairs") or {}
    entry = (pairs.get(pair_key(dep_id, arr_id)) or {}).get("dates") or {}
    return entry.get(day.isoformat())


def metro_day_type(d: date, holiday_set: set[str]) -> str:
    """날짜 → TAGO 지하철 요일구분 코드(01 평일 / 02 토 / 03 일·공휴일, 공휴일 우선)."""
    return {0: "01", 1: "02", 2: "03"}[get_weekday(d, holiday_set)]


def metro_schedule(store: dict, station_id: str, direction: str,
                   day_type: str) -> dict | None:
    """역·방향·요일구분 시간표. 토요일(02)이 비었으면 ``METRO_SATURDAY_FALLBACK`` 으로 대체.

    반환 항목의 ``day_type`` 은 실제로 쓴 코드다(대체 여부를 화면이 표시할 수 있게).
    """
    schedules = (store.get("metro") or {}).get("schedules") or {}
    entry = schedules.get(metro_key(station_id, direction, day_type))
    if day_type == "02" and not (entry and entry.get("times")):
        entry = schedules.get(metro_key(station_id, direction, METRO_SATURDAY_FALLBACK))
    return entry
