"""부산 가는 길 페이지 (/busan).

GET /busan — 세 루트(부산역 KTX · 노포 1224 · 벡스코/부전 동해선) 안내.

공개 화면이므로 외부 API 를 부르지 않는다(ADR-010). 버스 도착은 arrival 워커 캐시,
시간표는 timetable_provider_for, 철도는 cache-refresh 워커가 채운 rail_timetable.json 만 읽는다.
"""
from __future__ import annotations

import logging

from flask import Blueprint, current_app, render_template, request

from bushexa.data.constants import (
    BUSAN_1224_ROUTE_ID,
    BUSAN_KTX_TRANSFER_MIN,
    BUSAN_NOPO_TRANSFER_STOP_ID,
    BUSAN_UNIST_TO_ULSAN_STATION_MIN,
    METRO_QUERIES,
    RAIL_BUJEON,
    RAIL_BUSAN,
    RAIL_TAEHWAGANG,
    RAIL_ULSAN,
    UNIST_VIA_STOP_ID,
)
from bushexa.domain.busan import build_busan_snapshot
from bushexa.domain.rail_board import board_trains
from bushexa.services.board_support import arrival_client, timetable_provider_for
from bushexa.services.holiday_service import read_effective_holidays
from bushexa.services.nopo_profile import load_nopo_profile
from bushexa.services.rail_timetable import (
    default_rail_path,
    load_rail_store,
    metro_day_type,
    metro_trips,
    trains_on,
)
from bushexa.time_utils import KSTClock, get_weekday

log = logging.getLogger("bushexa.web.routes.busan")

bp = Blueprint("busan", __name__)


def _build_snapshot():
    config = current_app.config["BUSHEXA_CONFIG"]
    now = KSTClock().now()
    today = now.date()
    holiday_set = read_effective_holidays(config.data_dir)
    weekday = get_weekday(today, holiday_set)

    store = load_rail_store(default_rail_path(config.data_dir))
    metro_origin = METRO_QUERIES[0][0]
    bexco_id, bujeon_id = METRO_QUERIES[1][0], METRO_QUERIES[2][0]
    day_type = metro_day_type(today, holiday_set)

    arrivals, fetched_at, errors = [], None, []
    transfer, transfer_at = [], None
    try:
        client = arrival_client(config)
        arrivals = client.fetch_arrivals(UNIST_VIA_STOP_ID)
        fetched_at = client.last_fetched_at(UNIST_VIA_STOP_ID)
        transfer = client.fetch_arrivals(BUSAN_NOPO_TRANSFER_STOP_ID)
        transfer_at = client.last_fetched_at(BUSAN_NOPO_TRANSFER_STOP_ID)
    except Exception as exc:  # 캐시 장애여도 시간표·철도 안내는 보여 준다(500 금지)
        log.warning("부산 페이지 도착 캐시 조회 실패: %s", exc)
        errors.append("arrival")

    snapshot = build_busan_snapshot(
        now, weekday,
        timetable_provider=timetable_provider_for(config, today, holiday_set),
        unist_arrivals=arrivals,
        arrival_fetched_at=fetched_at,
        transfer_arrivals=transfer,
        transfer_fetched_at=transfer_at,
        ktx_day=trains_on(store, RAIL_ULSAN, RAIL_BUSAN, today),
        intercity_day=trains_on(store, RAIL_TAEHWAGANG, RAIL_BUJEON, today),
        metro_to_bexco=metro_trips(store, metro_origin, bexco_id, day_type),
        metro_to_bujeon=metro_trips(store, metro_origin, bujeon_id, day_type),
        nopo_profile=load_nopo_profile(config.data_dir),
    )
    boards = {
        "ktx": board_trains(trains_on(store, RAIL_ULSAN, RAIL_BUSAN, today), now, RAIL_ULSAN, RAIL_BUSAN)[0],
        "intercity": board_trains(trains_on(store, RAIL_TAEHWAGANG, RAIL_BUJEON, today), now,
                                  RAIL_TAEHWAGANG, RAIL_BUJEON)[0],
    }
    return snapshot, errors, boards


@bp.route("/busan", methods=["GET"])
def busan_page() -> str:
    """부산 가는 길 전체 페이지."""
    snapshot, errors, boards = _build_snapshot()
    return render_template(
        "busan.html", snapshot=snapshot, arrival_error="arrival" in errors, boards=boards,
        view="board" if request.args.get("view") == "board" else "table",
        unist_to_station_min=BUSAN_UNIST_TO_ULSAN_STATION_MIN,
        ktx_transfer_min=BUSAN_KTX_TRANSFER_MIN,
        nopo_route_id=BUSAN_1224_ROUTE_ID,
    )
