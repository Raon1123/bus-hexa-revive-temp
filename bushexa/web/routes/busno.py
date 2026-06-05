"""W3 — 버스번호별 시간표 라우트 (F02, TP-002).

GET /busno?bus=&day=&dep=

도메인 호출: bushexa.domain.busno.get_busno_page_data(bus, day, dep, clock, timetable_provider=...)
유효하지 않은 파라미터는 경고 배너로 표시하고 200 반환 (500 금지).
"""

from __future__ import annotations

from flask import Blueprint, current_app, render_template, request

from bushexa.data.timetable import get_timetable, timetable_dir
from bushexa.domain.busno import get_busno_page_data
from bushexa.services.holiday_service import read_effective_holidays
from bushexa.services.special_timetable import SpecialTimetableService, default_special_path
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

    # 특별 시간표: 오늘에 배정된 에디션이 있으면 day 미지정 시 해당 에디션 provider 사용
    tt_dir = timetable_dir()
    svc = SpecialTimetableService(
        map_path=default_special_path(config.data_dir),
        timetable_dir=tt_dir,
    )
    date_str = today.strftime("%Y%m%d")
    edition_id = svc.get_edition_for_date(date_str) if day is None else None
    if edition_id and svc.edition_exists(edition_id):
        edition_dir = svc.edition_dir(edition_id)
        def timetable_provider(busno, weekday, departure, *, dir=edition_dir):
            try:
                return get_timetable(busno, weekday, departure, dir=dir)
            except KeyError:
                return get_timetable(busno, 0, departure, dir=dir)
    else:
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
