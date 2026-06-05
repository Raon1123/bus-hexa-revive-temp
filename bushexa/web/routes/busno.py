"""W3 — 버스번호별 시간표 라우트 (F02, TP-002).

GET /busno?bus=&day=&dep=

도메인 호출: bushexa.domain.busno.get_busno_page_data(bus, day, dep, clock, timetable_provider=...)
유효하지 않은 파라미터는 경고 배너로 표시하고 200 반환 (500 금지).
"""

from __future__ import annotations

from flask import Blueprint, current_app, render_template, request

from bushexa.domain.busno import get_busno_page_data
from bushexa.services.board_support import timetable_provider_for
from bushexa.services.holiday_service import read_effective_holidays
from bushexa.time_utils import KSTClock

bp = Blueprint("busno", __name__)


@bp.route("/busno", methods=["GET"])
def busno_page() -> str:
    """버스번호별 시간표 전체 페이지."""
    bus = request.args.get("bus", default=None)
    raw_day = request.args.get("day", default=None)
    day: int | None = None
    if raw_day is not None:
        try:
            day = int(raw_day)
        except ValueError:
            day = 0  # 범위 오류는 도메인이 0으로 보정

    dep = request.args.get("dep", default=None)

    config = current_app.config["BUSHEXA_CONFIG"]
    clock = KSTClock()
    now = clock.now()
    today = now.date()

    # 공휴일 집합 (day가 명시적으로 지정되지 않은 경우 기본 요일 계산에 사용).
    # 읽기 경로: 외부 API 미호출 — 영속 캐시 + admin 지정만 읽는다(cache-refresh 워커가 갱신).
    holiday_set = read_effective_holidays(config.data_dir)

    # 특별 시간표: 오늘에 배정된 에디션이 있으면 day 미지정 시 해당 에디션 provider 사용.
    # 리뷰 E6: 기존 복제 래퍼를 board_support.timetable_provider_for로 단일화.
    # day가 명시적으로 지정되면 특별편을 적용하지 않는다(기존 동작 유지).
    if day is None:
        timetable_provider = timetable_provider_for(config, today, holiday_set)
    else:
        from bushexa.data.timetable import get_timetable
        timetable_provider = get_timetable

    timetable = get_busno_page_data(
        bus=bus,
        day=day,
        dep=dep,
        clock=clock,
        timetable_provider=timetable_provider,
        holiday_set=holiday_set,
    )
    return render_template("busno.html", timetable=timetable)
