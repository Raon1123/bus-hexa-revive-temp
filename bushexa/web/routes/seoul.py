"""서울 가는 길 페이지 (/seoul) — 513 → 울산역 → KTX 서울역·수서역, 역 발차 안내판.

GET /seoul?to=all|seoul|suseo

공개 화면이므로 외부 API 를 부르지 않는다(ADR-010). 버스 도착은 arrival 워커 캐시,
열차는 cache-refresh 워커가 채운 rail_timetable.json 만 읽는다.
"""
from __future__ import annotations

import logging

from flask import Blueprint, current_app, render_template, request

from bushexa.data.constants import (
    BUSAN_KTX_TRANSFER_MIN,
    BUSAN_UNIST_TO_ULSAN_STATION_MIN,
    RAIL_SEOUL,
    RAIL_SUSEO,
    RAIL_ULSAN,
    UNIST_VIA_STOP_ID,
)
from bushexa.domain.seoul import build_seoul_snapshot
from bushexa.services.board_support import arrival_client, timetable_provider_for
from bushexa.services.holiday_service import read_effective_holidays
from bushexa.services.rail_timetable import default_rail_path, load_rail_store, trains_on
from bushexa.time_utils import KSTClock, get_weekday

log = logging.getLogger("bushexa.web.routes.seoul")

bp = Blueprint("seoul", __name__)


@bp.route("/seoul", methods=["GET"])
def seoul_page() -> str:
    """서울 가는 길 전체 페이지."""
    config = current_app.config["BUSHEXA_CONFIG"]
    now = KSTClock().now()
    today = now.date()
    holiday_set = read_effective_holidays(config.data_dir)
    store = load_rail_store(default_rail_path(config.data_dir))

    arrivals, arrival_error = [], False
    try:
        arrivals = arrival_client(config).fetch_arrivals(UNIST_VIA_STOP_ID)
    except Exception as exc:  # 캐시 장애여도 안내판은 보여 준다(500 금지)
        log.warning("서울 페이지 도착 캐시 조회 실패: %s", exc)
        arrival_error = True

    snapshot = build_seoul_snapshot(
        now, get_weekday(today, holiday_set),
        timetable_provider=timetable_provider_for(config, today, holiday_set),
        seoul_day=trains_on(store, RAIL_ULSAN, RAIL_SEOUL, today),
        suseo_day=trains_on(store, RAIL_ULSAN, RAIL_SUSEO, today),
        seoul_ids=(RAIL_ULSAN, RAIL_SEOUL), suseo_ids=(RAIL_ULSAN, RAIL_SUSEO),
        unist_arrivals=arrivals, dest=request.args.get("to", "all"),
    )
    return render_template(
        "seoul.html", snapshot=snapshot, arrival_error=arrival_error,
        view="board" if request.args.get("view") == "board" else "table",
        unist_to_station_min=BUSAN_UNIST_TO_ULSAN_STATION_MIN,
        ktx_transfer_min=BUSAN_KTX_TRANSFER_MIN,
    )
