"""요일별 KTX 연계표 배선 — 로컬 파일(철도 시간표·513 시간표·구간 소요 프로필)만 읽어 표를 만든다.

공개 화면(/ktx)과 CLI ``bushexa ktx-connections`` 가 같이 쓴다. 외부 API 를 부르지 않는다(ADR-010).
"""
from __future__ import annotations

import datetime

from bushexa.data.constants import (
    KTX_5001,
    KTX_5001_FROM_STATION,
    KTX_5001_TO_STATION,
    KTX_CONNECT_DESTS,
    KTX_JINMOK_IN_FEEDERS,
    KTX_JINMOK_OUT_FEEDERS,
    KTX_IN_513_ORIGIN,
    KTX_OUT_513_ORIGIN,
    RAIL_ULSAN,
)
from bushexa.domain.ktx_connect import (
    ConnectTable,
    Transfers,
    build_inbound,
    build_outbound,
    reference_date,
)
from bushexa.services.board_support import timetable_provider_for
from bushexa.services.leg_profile import default_profile_path, load_profile
from bushexa.services.rail_timetable import (
    default_rail_path,
    load_rail_store,
    pair_key,
    trains_on,
)
from bushexa.time_utils import get_weekday


def rail_pair(direction: str, dest: str) -> tuple[str, str]:
    """(출발역, 도착역) — 가는 편은 울산역 출발, 오는 편은 울산역 도착."""
    other = KTX_CONNECT_DESTS[dest]
    return (RAIL_ULSAN, other) if direction == "out" else (other, RAIL_ULSAN)


def _stored_dates(store: dict, dep_id: str, arr_id: str) -> list[datetime.date]:
    pairs = (store.get("trains") or {}).get("pairs") or {}
    out = []
    for ds in ((pairs.get(pair_key(dep_id, arr_id)) or {}).get("dates") or {}):
        try:
            out.append(datetime.date.fromisoformat(ds))
        except ValueError:
            continue
    return out


def _same_kind_days(store: dict, dep_id: str, arr_id: str, ref: datetime.date, day: int,
                    holiday_set: set[str]) -> list[dict]:
    """기준일이 아닌, 요일구분이 같은 저장 날짜 항목들(가까운 날짜 먼저)."""
    others = sorted((d for d in _stored_dates(store, dep_id, arr_id)
                     if d != ref and get_weekday(d, holiday_set) == day), key=lambda d: abs((d - ref).days))
    return [e for e in (trains_on(store, dep_id, arr_id, d) for d in others) if e]


def borrow_stops(train_day: dict, others: list[dict]) -> dict:
    """정차역을 모르는 열차에 같은 요일구분 다른 날짜의 같은 번호·같은 시각 열차 정차역을 빌려 준다.

    KTX 는 같은 요일구분이면 편성·정차가 거의 같다. 번호와 출발·도착 시각(HH:MM)이 모두 같을 때만
    빌린다. 원본 dict 는 바꾸지 않는다.
    """
    def key(t):
        return (str(t.get("no", "")), str(t.get("dep", ""))[11:16], str(t.get("arr", ""))[11:16])
    pool: dict[tuple, list] = {}
    for entry in others:
        for t in entry.get("trains") or []:
            if isinstance(t, dict) and t.get("stops") is not None:
                pool.setdefault(key(t), t["stops"])
    trains = []
    for t in train_day.get("trains") or []:
        if isinstance(t, dict) and t.get("stops") is None and key(t) in pool:
            t = {**t, "stops": pool[key(t)]}
        trains.append(t)
    return {**train_day, "trains": trains}


def build_connect_table(config, today: datetime.date, holiday_set: set[str], *,
                        direction: str, dest: str, day: int,
                        transfers: Transfers | None = None,
                        ) -> tuple[ConnectTable, list[str], dict | None]:
    """(표, 오류 문구 목록(시간표 파일 없음 등), 구간 소요 프로필 — 출처·기간 표시용)."""
    errors: list[str] = []
    store = load_rail_store(default_rail_path(config.data_dir))
    dep_id, arr_id = rail_pair(direction, dest)
    ref = reference_date(today, day, holiday_set, _stored_dates(store, dep_id, arr_id))
    train_day = trains_on(store, dep_id, arr_id, ref) if ref else None
    if train_day:
        train_day = borrow_stops(train_day, _same_kind_days(store, dep_id, arr_id, ref, day, holiday_set))

    # 버스 시간표도 기준일의 것(특별편 지정일이면 그 편성)을 쓴다. 기준일이 없으면 오늘 기준 provider.
    provider = timetable_provider_for(config, ref or today, holiday_set)
    origin = KTX_OUT_513_ORIGIN if direction == "out" else KTX_IN_513_ORIGIN
    try:
        bus_times = list(provider("513", day, origin))
    except (FileNotFoundError, KeyError) as exc:
        errors.append(f"513 {origin} 시간표 없음: {exc}")
        bus_times = []

    # ② 5001 + 진목회관 환승 안의 시간표(5001 한 방향 + 환승 버스들). 없는 노선은 그 안에서 빠진다.
    keys = ([(KTX_5001, KTX_5001_TO_STATION)] + [(b, k) for b, k, _p, _l in KTX_JINMOK_OUT_FEEDERS]
            if direction == "out" else
            [(KTX_5001, KTX_5001_FROM_STATION)] + [(b, k) for b, k, _p, _l in KTX_JINMOK_IN_FEEDERS])
    timetables = {}
    for busno, key in keys:
        try:
            timetables[(busno, key)] = list(provider(busno, day, key))
        except (FileNotFoundError, KeyError) as exc:
            errors.append(f"{busno} {key} 시간표 없음: {exc}")

    profile = load_profile(default_profile_path(config.data_dir))
    build = build_outbound if direction == "out" else build_inbound
    table = build(day, ref, dest=dest, train_day=train_day, bus_times=bus_times, profile=profile,
                  pair=(dep_id, arr_id), timetables=timetables, transfers=transfers)
    return table, errors, profile
