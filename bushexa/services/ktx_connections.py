"""요일별 KTX 연계표 배선 — 로컬 파일(철도 시간표·513 시간표·구간 소요 프로필)만 읽어 표를 만든다.

공개 화면(/ktx)과 CLI ``bushexa ktx-connections`` 가 같이 쓴다. 외부 API 를 부르지 않는다(ADR-010).
"""
from __future__ import annotations

import datetime

from bushexa.data.constants import (
    KTX_CONNECT_DESTS,
    KTX_IN_513_ORIGIN,
    KTX_OUT_513_ORIGIN,
    RAIL_ULSAN,
)
from bushexa.domain.ktx_connect import ConnectTable, build_inbound, build_outbound, reference_date
from bushexa.services.board_support import timetable_provider_for
from bushexa.services.leg_profile import default_profile_path, load_profile
from bushexa.services.rail_timetable import (
    default_rail_path,
    load_rail_store,
    pair_key,
    trains_on,
)


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


def build_connect_table(config, today: datetime.date, holiday_set: set[str], *,
                        direction: str, dest: str, day: int,
                        ) -> tuple[ConnectTable, list[str], dict | None]:
    """(표, 오류 문구 목록(시간표 파일 없음 등), 구간 소요 프로필 — 출처·기간 표시용)."""
    errors: list[str] = []
    store = load_rail_store(default_rail_path(config.data_dir))
    dep_id, arr_id = rail_pair(direction, dest)
    ref = reference_date(today, day, holiday_set, _stored_dates(store, dep_id, arr_id))
    train_day = trains_on(store, dep_id, arr_id, ref) if ref else None

    # 버스 시간표도 기준일의 것(특별편 지정일이면 그 편성)을 쓴다. 기준일이 없으면 오늘 기준 provider.
    provider = timetable_provider_for(config, ref or today, holiday_set)
    origin = KTX_OUT_513_ORIGIN if direction == "out" else KTX_IN_513_ORIGIN
    try:
        bus_times = list(provider("513", day, origin))
    except (FileNotFoundError, KeyError) as exc:
        errors.append(f"513 {origin} 시간표 없음: {exc}")
        bus_times = []

    profile = load_profile(default_profile_path(config.data_dir))
    build = build_outbound if direction == "out" else build_inbound
    table = build(day, ref, dest=dest, train_day=train_day, bus_times=bus_times, profile=profile)
    return table, errors, profile
