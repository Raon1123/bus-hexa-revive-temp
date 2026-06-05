"""W8 — 운행 재구성 테이블 라우트 (F05, TP-006).

GET /running?route_id=&date=

도메인 호출: bushexa.domain.running.parse_runs + build_running_grid
DB 접근: bushexa.db.repo.BusLogRepo.get_by_route(route_id, day=date)
DB 연결 실패 → 500 아님, 사용자 친화 메시지 (F05 §1).
잘못된 date 형식 → 경고 + 기본값(어제).
"""

from __future__ import annotations

import logging
from datetime import date

from flask import Blueprint, current_app, render_template, request

from bushexa.data.constants import ROUTEID, STOP_IDS
from bushexa.db.connection import create_connection
from bushexa.db.repo import BusLogRepo
from bushexa.domain.running import build_running_grid, parse_runs
from bushexa.time_utils import KSTClock

log = logging.getLogger("bushexa.web.routes.running")

bp = Blueprint("running", __name__)


def _today_kst() -> date:
    return KSTClock().now().date()


def _parse_date(date_str: str | None) -> tuple[date, str | None]:
    """date 문자열을 date로 파싱. ``YYYYMMDD``/``YYYY-MM-DD`` 모두 허용.

    <input type="date">는 ``YYYY-MM-DD``로 제출하고, 레거시·테스트는 ``YYYYMMDD``를
    쓰므로 숫자만 추출해 동일하게 처리한다. 미지정/형식 오류 시 오늘(KST)로 폴백한다.
    (DB에는 오늘부터 데이터가 쌓이므로 기본값 '오늘'이 로드 시점 빈 화면을 막는다.)
    """
    if date_str is None:
        return _today_kst(), None
    digits = "".join(ch for ch in date_str if ch.isdigit())
    try:
        d = date(int(digits[:4]), int(digits[4:6]), int(digits[6:8]))
        return d, None
    except (ValueError, IndexError):
        return _today_kst(), f"날짜 형식이 올바르지 않습니다: {date_str!r}. 오늘 날짜로 대체합니다."


@bp.route("/running", methods=["GET"])
def running_page() -> str:
    """운행 재구성 테이블 페이지."""
    route_id_param = request.args.get("route_id", default=None)
    date_param = request.args.get("date", default=None)

    # 노선 목록 (선택 UI용)
    route_options = [
        (rid, f"{info[0]}번 {info[1]}행")
        for rid, info in ROUTEID.items()
    ]

    # route_id 검증 및 기본값
    warning: str | None = None
    if route_id_param is None or route_id_param not in ROUTEID:
        if route_id_param is not None:
            warning = f"유효하지 않은 노선 ID: {route_id_param!r}."
        route_id = next(iter(ROUTEID))
    else:
        route_id = route_id_param

    # date 파싱
    target_date, date_warn = _parse_date(date_param)
    if date_warn:
        warning = (warning or "") + " " + date_warn

    # 정류장 ID → 표시 명칭 (STOP_IDS, 없으면 ID 그대로)
    _, _, _, stops_order = ROUTEID[route_id]
    stop_names = {sid: STOP_IDS.get(sid, sid) for sid in stops_order}

    # DB 조회 + 도메인 처리
    grid = None
    db_error: str | None = None
    try:
        config = current_app.config["BUSHEXA_CONFIG"]
        conn = create_connection(config.database_url)
        with BusLogRepo(conn) as repo:
            timelog_rows = repo.get_by_route(route_id, day=target_date)
        runs = parse_runs(timelog_rows, route_id)
        grid = build_running_grid(runs, stops_order)
    except Exception as exc:
        log.error("running 페이지 DB 오류: %s", exc, exc_info=True)
        db_error = "데이터베이스에서 운행 정보를 가져올 수 없습니다."

    return render_template(
        "running.html",
        route_options=route_options,
        selected_route_id=route_id,
        target_date=target_date.strftime("%Y-%m-%d"),
        stop_names=stop_names,
        grid=grid,
        warning=warning,
        db_error=db_error,
    )
