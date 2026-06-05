"""W5 — 정류소별 버스 도착 정보 라우트 (F06, TP-003).

GET /stops              — 정류소 선택 페이지 전체
GET /partial/stops?stop_id=  — HTMX 폴링 대상 (10초), 도착 테이블 조각

도메인 호출: bushexa.domain.stops.get_stop_data(stop_id, clock, client=...)
서버 캐시: bushexa.services.stop_cache (TTL 10초, Clock 주입)
"""

from __future__ import annotations

from flask import Blueprint, abort, current_app, render_template, request

from bushexa.data.constants import SERACH_STOPS, STOP_IDS
from bushexa.domain.stops import get_stop_data
from bushexa.services import stop_cache
from bushexa.services.board_support import arrival_client
from bushexa.time_utils import KSTClock

bp = Blueprint("stops", __name__)


@bp.route("/stops", methods=["GET"])
def stops_page() -> str:
    """정류소 선택 전체 페이지."""
    stop_options = [
        (stop_id, STOP_IDS.get(stop_id, stop_id))
        for stop_id in SERACH_STOPS
    ]
    return render_template("stops.html", stop_options=stop_options)


@bp.route("/partial/stops", methods=["GET"])
def stops_partial():
    """HTMX 폴링 대상 — 도착 정보 테이블 조각. hx-trigger="every 10s" 는 템플릿에 있음."""
    stop_id = request.args.get("stop_id")
    if not stop_id or stop_id not in SERACH_STOPS:
        abort(400, description="유효하지 않은 stop_id입니다.")

    config = current_app.config["BUSHEXA_CONFIG"]
    clock = KSTClock()
    # ADR-010: 라이브 울산 API 대신 arrival poller가 채운 cache(bus_arrival_cache)를 읽는다.
    # 리뷰 #8/E6: 매 요청 새 연결+PRAGMA 대신 워커 수명 재사용 연결 사용.
    client = arrival_client(config)

    def _fetch(sid: str):
        return get_stop_data(sid, clock, client=client)

    snapshot = stop_cache.get_or_fetch(stop_id, _fetch, clock)
    return render_template("stops_partial.html", snapshot=snapshot)
