"""W7 — 전체 시간표 라우트 (F08, TP-005).

GET /timetable?day=   (day=0 평일, 1=토, 2=일/공휴일)

도메인 호출: bushexa.domain.unist_timetable.get_full_timetable_data(weekday, clock, timetable_provider=...)
버스 색상은 .bus-{N} CSS 클래스(timetable.css)로 적용; 인라인 style="color:" 금지.
"""

from __future__ import annotations

from flask import Blueprint, current_app, render_template, request

from bushexa.domain.unist_timetable import get_full_timetable_data
from bushexa.services.board_support import timetable_provider_for
from bushexa.services.holiday_service import read_effective_holidays
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

    # 특별 시간표: ?day 미지정(오늘)에 배정된 에디션이 있으면 provider 교체.
    # 리뷰 E6: 기존 복제 래퍼를 board_support.timetable_provider_for로 단일화.
    # raw_day 지정 시 특별편을 적용하지 않는다(기존 동작 유지).
    if raw_day is None:
        timetable_provider = timetable_provider_for(config, today, holiday_set)
    else:
        from bushexa.data.timetable import get_timetable
        timetable_provider = get_timetable

    snapshot = get_full_timetable_data(
        weekday=day,
        clock=clock,
        timetable_provider=timetable_provider,
    )
    return render_template("unist_timetable.html", snapshot=snapshot)
