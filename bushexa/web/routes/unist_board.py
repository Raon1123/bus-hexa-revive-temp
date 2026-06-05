"""W6 — UNIST 버스 카드 보드 라우트 (F07, TP-004).

GET /unist              — 전체 페이지 (6개 카드 그리드)
GET /partial/unist      — HTMX 폴링 조각 (30초), id="unist-grid" 조각만

도메인 호출: bushexa.domain.unist_board.get_unist_board_data(clock, client=..., timetable_provider=...)
"""

from __future__ import annotations

from flask import Blueprint, current_app, render_template

from bushexa.domain.unist_board import get_unist_board_data
from bushexa.services.board_support import arrival_client, timetable_provider_for
from bushexa.services.holiday_service import read_effective_holidays
from bushexa.time_utils import KSTClock

bp = Blueprint("unist_board", __name__)


def _build_snapshot():
    """도메인 get_unist_board_data 호출.

    리뷰 #4 수정: holiday_set을 도메인에 전달해 공휴일에 weekday=2를 사용한다.
    리뷰 #5 수정: bare get_timetable 대신 timetable_provider_for를 통해 특별편 적용.
    리뷰 E6/#8: arrival_client(board_support)로 워커 수명 재사용 연결 사용.
    """
    config = current_app.config["BUSHEXA_CONFIG"]
    clock = KSTClock()
    now = clock.now()
    today = now.date()

    # 공휴일 집합: 읽기 경로 전용 (외부 API 미호출 — cache-refresh 워커 담당).
    holiday_set = read_effective_holidays(config.data_dir)

    # 특별편 provider: 리뷰 #5 수정 — 기존 bare get_timetable 대신 edition 래퍼 적용.
    timetable_provider = timetable_provider_for(config, today, holiday_set)

    # ADR-010: 라이브 울산 API 대신 arrival poller가 채운 cache(bus_arrival_cache)를 읽는다.
    # 리뷰 #8/E6: 매 요청 새 연결+PRAGMA 대신 워커 수명 재사용 연결 사용.
    client = arrival_client(config)
    return get_unist_board_data(
        clock,
        client=client,
        timetable_provider=timetable_provider,
        holiday_set=holiday_set,
    )


@bp.route("/unist", methods=["GET"])
def unist_board_page() -> str:
    """UNIST 버스 카드 보드 전체 페이지."""
    snapshot = _build_snapshot()
    return render_template("unist_board.html", snapshot=snapshot)


@bp.route("/partial/unist", methods=["GET"])
def unist_board_partial():
    """HTMX 폴링 대상 — id="unist-grid" 조각만 반환. <html> 태그 없음."""
    snapshot = _build_snapshot()
    return render_template("unist_partial.html", snapshot=snapshot)
