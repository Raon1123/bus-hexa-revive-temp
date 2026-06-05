"""W7 — 전체 시간표 라우트 (F08, TP-005).

GET /timetable?day=   (day=0 평일, 1=토, 2=일/공휴일)

도메인 호출: bushexa.domain.unist_timetable.get_full_timetable_data(weekday, clock, timetable_provider=...)
버스 색상은 .bus-{N} CSS 클래스(timetable.css)로 적용; 인라인 style="color:" 금지.
"""

from __future__ import annotations

from flask import Blueprint, current_app, render_template, request

from bushexa.data.timetable import get_timetable, timetable_dir
from bushexa.domain.unist_timetable import get_full_timetable_data
from bushexa.services.holiday_service import read_effective_holidays
from bushexa.services.special_timetable import SpecialTimetableService, default_special_path
from bushexa.time_utils import KSTClock, get_weekday

bp = Blueprint("unist_timetable", __name__)


@bp.route("/timetable", methods=["GET"])
def timetable_page() -> str:
    """전체 시간표 페이지. 요일 전환은 GET 링크."""
    raw_day = request.args.get("day", default=None)
    clock = KSTClock()
    now = clock.now()
    today = now.date()

    config = current_app.config["BUSHEXA_CONFIG"]

    # 공휴일 집합: 읽기 경로는 외부 API 미호출 — 영속 캐시 + admin 지정만 읽는다
    # (cache-refresh 워커가 새벽에 갱신).
    holiday_set = read_effective_holidays(config.data_dir)

    day: int
    if raw_day is None:
        # 기본값: 공휴일 포함한 오늘 요일
        day = get_weekday(today, holiday_set)
    else:
        try:
            day = int(raw_day)
        except ValueError:
            day = 0  # 범위 오류는 도메인이 0으로 보정

    # 특별 시간표: ?day 미지정(오늘)에 배정된 에디션이 있으면 provider 교체
    tt_dir = timetable_dir()
    svc = SpecialTimetableService(
        map_path=default_special_path(config.data_dir),
        timetable_dir=tt_dir,
    )
    date_str = today.strftime("%Y%m%d")
    edition_id = svc.get_edition_for_date(date_str) if raw_day is None else None
    if edition_id and svc.edition_exists(edition_id):
        edition_dir = svc.edition_dir(edition_id)
        def timetable_provider(busno, weekday, departure, *, dir=edition_dir):
            try:
                return get_timetable(busno, weekday, departure, dir=dir)
            except KeyError:
                return get_timetable(busno, 0, departure, dir=dir)
    else:
        timetable_provider = get_timetable

    snapshot = get_full_timetable_data(
        weekday=day,
        clock=clock,
        timetable_provider=timetable_provider,
    )
    return render_template("unist_timetable.html", snapshot=snapshot)
