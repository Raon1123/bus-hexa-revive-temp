"""W6 — UNIST 버스 카드 보드 라우트 (F07, TP-004).

GET /unist              — 전체 페이지 (6개 카드 그리드)
GET /partial/unist      — HTMX 폴링 조각 (30초), id="unist-grid" 조각만

도메인 호출: bushexa.domain.unist_board.get_unist_board_data(clock, client=..., timetable_provider=...)
"""

from __future__ import annotations

from flask import Blueprint, current_app, render_template

from bushexa.api_clients.cached_arrival import CachedArrivalClient
from bushexa.data.timetable import get_timetable
from bushexa.db.connection import create_connection
from bushexa.db.repo_arrival import BusArrivalRepo
from bushexa.domain.unist_board import get_unist_board_data
from bushexa.time_utils import KSTClock

bp = Blueprint("unist_board", __name__)


def _build_snapshot():
    """도메인 get_unist_board_data 호출."""
    config = current_app.config["BUSHEXA_CONFIG"]
    clock = KSTClock()
    # ADR-010: 라이브 울산 API 대신 arrival poller가 채운 cache(bus_arrival_cache)를 읽는다.
    conn = create_connection(config.database_url)
    try:
        client = CachedArrivalClient(BusArrivalRepo(conn))
        return get_unist_board_data(
            clock,
            client=client,
            timetable_provider=get_timetable,
        )
    finally:
        conn.close()


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
