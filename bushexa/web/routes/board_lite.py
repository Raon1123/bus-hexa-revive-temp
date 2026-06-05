"""FASTER 모드 — 폰트/JS 없는 경량 평문 HTML 출발 게시판.

기존 ``/board``는 Pretendard/SeoulNamsan woff2(~5.5MB) + htmx + splitflap.js를 로드해
저사양 기기·느린 네트워크에서 렌더가 무겁다. 이 ``/lite`` 페이지는 동일한 cache 기반
스냅샷(``board._build_snapshot``)을 쓰되, ``_base.html``을 상속하지 않는 독립 최소 HTML로
렌더한다: 시스템 폰트, JS 0, ``<meta http-equiv="refresh">``로만 자동 갱신.

데이터는 board와 동일하게 ``bus_arrival_cache``(arrival poller 백업본)에서 읽으므로
라이브 울산 API 호출이 없다(ADR-010).
"""
from __future__ import annotations

from flask import Blueprint, current_app, render_template

from bushexa.services.board_support import arrival_client
from bushexa.web.routes.board import _STOP_ID, _build_snapshot
from bushexa.web.timing import span

bp = Blueprint("board_lite", __name__)

# JS 없이 <meta refresh>로만 갱신 — board의 HTMX 폴링(수 초)보다 보수적으로 둔다.
_REFRESH_SECONDS = 15


def _last_fetched_at() -> str | None:
    """게시판 정류장 cache의 신선도(staleness) 표시용.

    리뷰 E2/E6: 기존에는 _build_snapshot과 별도의 두 번째 SQLite 연결을 열었다.
    board_support.arrival_client를 통해 워커 수명 재사용 연결을 공유한다.
    """
    config = current_app.config["BUSHEXA_CONFIG"]
    with span("lite_fetched_at"):
        return arrival_client(config).last_fetched_at(_STOP_ID)


@bp.route("/lite", methods=["GET"])
def board_lite() -> str:
    """경량 평문 HTML 게시판 (FASTER 모드)."""
    snapshot = _build_snapshot()
    fetched_at = _last_fetched_at()
    with span("render"):
        return render_template(
            "board_lite.html",
            snapshot=snapshot,
            refresh_seconds=_REFRESH_SECONDS,
            fetched_at=fetched_at,
        )
