"""요일별 KTX 연계표 페이지 (/ktx) — 열차마다 이어 타는 513 을 평일·토·일/공휴일로 나눠 보인다.

GET /ktx?dir=out|in&to=busan|seoul|suseo&day=0|1|2&ts=5&tj=5
  - dir=out(기본): UNIST → 울산역 → KTX(부산·서울·수서행). 열차마다 최소한 타야 하는 버스.
  - dir=in: KTX(부산·서울·수서발) → 울산역 → UNIST. 열차마다 이어 타는 첫 버스.
  - day 를 주지 않으면 오늘의 요일구분.
  - ts / tj: 환승 최소 시간(분) — ts 울산역 버스 정류장 ↔ KTX, tj 진목회관 길 건너 버스 ↔ 버스.
    기본 5분, 0~``KTX_TRANSFER_MAX_MIN``.

공개 화면이므로 외부 API 를 부르지 않는다(ADR-010). 철도는 rail_timetable.json, 버스는
timetable_provider_for, 소요는 ktx_leg_profile.json 만 읽는다.
"""
from __future__ import annotations

from flask import Blueprint, current_app, render_template, request

from bushexa.data.constants import KTX_CONNECT_DESTS, KTX_TRANSFER_MAX_MIN
from bushexa.domain.ktx_connect import DAYS, DIRECTIONS, Transfers, split_blocks
from bushexa.services.holiday_service import read_effective_holidays
from bushexa.services.ktx_connections import build_connect_table
from bushexa.time_utils import KSTClock, get_weekday

bp = Blueprint("ktx", __name__)


def _choice(value, allowed, default):
    return value if value in allowed else default


def _minutes_arg(name: str, default: int) -> int:
    """쿼리의 환승 최소 시간(분). 숫자가 아니거나 범위 밖이면 기본값."""
    value = request.args.get(name, "")
    if value.isdigit() and int(value) <= KTX_TRANSFER_MAX_MIN:
        return int(value)
    return default


@bp.route("/ktx", methods=["GET"])
def ktx_page() -> str:
    """요일별 KTX 연계표."""
    config = current_app.config["BUSHEXA_CONFIG"]
    now = KSTClock().now()
    today = now.date()
    holiday_set = read_effective_holidays(config.data_dir)
    today_day = get_weekday(today, holiday_set)

    direction = _choice(request.args.get("dir"), DIRECTIONS, "out")
    dest = _choice(request.args.get("to"), tuple(KTX_CONNECT_DESTS), "busan")
    day_arg = request.args.get("day", "")
    day = int(day_arg) if day_arg.isdigit() and int(day_arg) in DAYS else today_day

    base = Transfers()
    transfers = Transfers(station=_minutes_arg("ts", base.station), jinmok=_minutes_arg("tj", base.jinmok))

    table, errors, profile = build_connect_table(
        config, today, holiday_set, direction=direction, dest=dest, day=day, transfers=transfers)
    return render_template(
        "ktx.html", table=table, blocks=split_blocks(table.rows, table.direction), errors=errors,
        profile=profile, today_day=today_day, transfer_max=KTX_TRANSFER_MAX_MIN, dests=tuple(KTX_CONNECT_DESTS), days=DAYS,
    )
