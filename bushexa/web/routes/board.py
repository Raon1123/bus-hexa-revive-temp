"""W2 — 출발 게시판 라우트 (F01, TP-001).

GET /board        전체 페이지 (board.html extends _base.html)
GET /partial/board  HTMX 폴링 조각 (partial/board_table.html — <html> 없음)

도메인 호출: bushexa.domain.board.get_board_data(stop_id, clock, client=…, timetable_provider=…)
외부 API 실패는 도메인이 BoardSnapshot.error 필드로 처리 — 500 회피 (TP-001 §6).
"""

from __future__ import annotations

from flask import Blueprint, current_app, render_template

from bushexa.domain.board import get_board_data
from bushexa.services.board_support import arrival_client, timetable_provider_for
from bushexa.services.holiday_service import read_effective_holidays
from bushexa.services.via_editor import ViaEditor, default_via_path
from bushexa.time_utils import KSTClock
from bushexa.web.timing import span

# F01 §4.2 (TP-001): URL은 /board 와 /partial/board — url_prefix 사용 안 함
bp = Blueprint("board", __name__)

# F01 §3.1 / TP-001: 정류소 ID 고정 (UNIST 경유 정류장)
_STOP_ID = "196040234"


def _build_snapshot():
    """도메인 get_board_data 호출. 의존성은 이 함수에서만 생성(테스트에서 이 함수 자체 또는
    get_board_data를 mock해 네트워크 없이 검증 가능)."""
    config = current_app.config["BUSHEXA_CONFIG"]
    clock = KSTClock()
    now = clock.now()
    today = now.date()

    # 공휴일 집합: 읽기 경로는 외부 API를 호출하지 않고 영속 캐시(holiday_cache.json) +
    # admin 지정(holidays.json)만 읽는다(로컬 파일 2회). API 갱신은 cache-refresh 워커 담당.
    # `holiday` 구간은 이제 파일 읽기뿐이라 cold/warm 모두 ~0ms 여야 한다.
    with span("holiday"):
        holiday_set = read_effective_holidays(config.data_dir)

    # 특별 시간표 적용: 오늘에 특별 에디션이 배정되어 있으면 provider를 교체.
    # 리뷰 E6: 기존 3벌의 복제 래퍼를 board_support.timetable_provider_for로 단일화.
    # D8 수정: board_support 내에서 FileNotFoundError도 잡아 부분 edition 폴백 보장.
    with span("special_tt"):
        timetable_provider = timetable_provider_for(config, today, holiday_set)

    with span("via"):
        via_overrides = ViaEditor(default_via_path(config.data_dir)).load()
    # ADR-010: 화면은 울산 API를 라이브 호출하지 않고 arrival poller가 채운 cache만 읽는다.
    # 리뷰 #8/E6: 매 요청 새 연결+PRAGMA 대신 워커 수명 재사용 연결 사용(board_support).
    with span("db_connect"):
        client = arrival_client(config)
    with span("domain"):
        return get_board_data(
            _STOP_ID,
            clock,
            client=client,
            timetable_provider=timetable_provider,
            via_overrides=via_overrides,
            holiday_set=holiday_set,
        )


@bp.route("/board", methods=["GET"])
def departure_board() -> str:
    """출발 게시판 전체 페이지."""
    snapshot = _build_snapshot()
    with span("render"):
        return render_template("board.html", snapshot=snapshot)


@bp.route("/partial/board", methods=["GET"])
def departure_board_partial():
    """HTMX 폴링 대상 — 테이블 조각만 반환. <html> 태그 없음 (TP-001 §8)."""
    snapshot = _build_snapshot()
    with span("render"):
        return render_template("partial/board_table.html", snapshot=snapshot)
