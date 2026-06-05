"""W15 — 라우트 smoke tests 통합 (P4 EC-2, TP 전반).

테스트 케이스:
  test_all_ui_routes_200       — 7개 UI 라우트 각 200 + 페이지 고유 마커
  test_partials                — partial 3종(/partial/board, /partial/stops, /partial/unist) 200
  test_admin_login_page_200    — GET /admin/login → 200 (admin login smoke)
  test_admin_dashboard_after_login — 로그인 세션으로 GET /admin/ → 200 + admin-dashboard 마커
                                     + govtrack-card 마커

E-13 준수:
  - 기대값은 spec상 각 라우트 URL 명세(W2~W8 AC-1, F01~F08 §4.2) + admin 명세(W10 AC-1/2).
  - smoke 기대값 = "HTTP 200 + 페이지 고유 마커" (spec 출처: P4 §3 EC-2, W15 AC-1/2).
  - 마커는 각 라우트의 <title> 또는 id 속성으로, 데이터 의존 없이 항상 렌더됨.
  - 외부 네트워크 없이: domain 함수를 최소 유효 dataclass로 mock, running은 빈 DB.

AC 달성:
  - AC-1: 9개 라우트(7 UI + admin login + admin dashboard) smoke 통과.
  - AC-2: partial 3종(board/stops/unist) 200.
"""

from __future__ import annotations

import sqlite3
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from bushexa.config import AppConfig
from bushexa.data.constants import ROUTEID, SERACH_STOPS
from bushexa.db.schema import create_schema
from bushexa.domain.board import BoardSnapshot
from bushexa.domain.busno import BusnoTimetable
from bushexa.domain.stops import StopSnapshot
from bushexa.domain.unist_board import BusCard, CardEntry, UnistBoardSnapshot
from bushexa.domain.unist_timetable import (
    DepartureEntry,
    FullTimetableSnapshot,
    TimetableHourRow,
)
from bushexa.web.app import create_app

_KST = ZoneInfo("Asia/Seoul")

# ─────────────────────────────────────────────────────────────────────────────
# 최소 유효 mock 데이터 (E-13: 알려진 입력, 구현 독립)
# ─────────────────────────────────────────────────────────────────────────────

_BOARD_SNAPSHOT = BoardSnapshot(
    current_time="08:30",
    weekday_str="평일",
    rows=[],
    error=None,
    is_last_bus=False,
)

_BUSNO_TIMETABLE = BusnoTimetable(
    current_time="08:30",
    weekday_str="평일 (working day)",
    busnos=["513", "713", "743", "753", "1115"],
    selected_bus="713",
    day_options=["Weekday", "Saturday", "Sunday/Holiday"],
    selected_day=0,
    terminals=["UNIST"],
    selected_dep="UNIST",
    timetable_rows=[],
    warning=None,
)

_STOP_SNAPSHOT = StopSnapshot(
    stop_id=SERACH_STOPS[0],
    stop_name="테스트 정류소",
    rows=[],
    has_no_bus=True,
    long_gap=False,
    error=None,
    minutes_until=[],
)

_UNIST_SNAPSHOT = UnistBoardSnapshot(
    cards=[
        BusCard(
            busno="713",
            direction="명촌 방면",
            entries=[CardEntry(text="08:30 출발 예정", source="timetable")],
            is_last_bus=False,
        ),
    ],
    bis_error=False,
)

_TIMETABLE_SNAPSHOT = FullTimetableSnapshot(
    current_time="08:30",
    weekday_str="평일 (working day)",
    selected_day=0,
    bus_legend=["713"],
    timetable_rows=[
        TimetableHourRow(
            hour="08",
            departures=[DepartureEntry(minute="30", busno="713")],
        )
    ],
    is_empty=False,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def smoke_app(tmp_path, tmp_sqlite_db):
    """smoke 테스트용 Flask app — 빈 SQLite DB (running은 빈 DB로 200 반환)."""
    conn = sqlite3.connect(str(tmp_sqlite_db))
    create_schema(conn)
    conn.close()
    config = AppConfig(
        api_key="test-api-key",
        database_url=f"sqlite:///{tmp_sqlite_db}",
        session_secret="test-session-secret",
        manager_password_path=tmp_path / "manager_password.txt",
        data_dir=tmp_path / "data",
        tz=_KST,
        log_level="DEBUG",
        log_dir=tmp_path / "logs",
    )
    return create_app(config)


@pytest.fixture
def smoke_client(smoke_app):
    return smoke_app.test_client()


def _inject_auth(client) -> None:
    """test_client 세션에 admin_authed=True를 주입한다 (test_admin_auth_flow 패턴 재사용)."""
    with client.session_transaction() as sess:
        sess["admin_authed"] = True
        sess["csrf_token"] = "test-csrf-token"


# ─────────────────────────────────────────────────────────────────────────────
# AC-1: test_all_ui_routes_200 — 7개 UI 라우트 각 200 + 고유 마커
# ─────────────────────────────────────────────────────────────────────────────

def test_all_ui_routes_200(smoke_client):
    """7개 UI 라우트가 각각 200이고 고유 마커를 포함하는지 smoke 검증.

    독립 출처: P4 §3 EC-2, W2~W8 AC-1, W15 AC-1.
    마커 기준: <title> 내용 또는 항상-렌더 컨테이너 id (데이터 의존 없음).
    외부 네트워크 없이: domain 함수를 최소 유효 mock으로 교체.
    """
    routes_and_markers = [
        # (URL, 마커, mock 대상, mock 반환값)
        (
            "/board",
            "UNIST 출발안내",  # <title>
            "bushexa.web.routes.board.get_board_data",
            _BOARD_SNAPSHOT,
        ),
        (
            "/busno",
            "버스번호별 시간표",  # <title>
            "bushexa.web.routes.busno.get_busno_page_data",
            _BUSNO_TIMETABLE,
        ),
        (
            "/info",
            "버스 노선 정보",  # <title>
            None,
            None,
        ),
        (
            "/stops",
            "정류소별 버스 도착 정보",  # <title>
            None,
            None,
        ),
        (
            "/unist",
            "UNIST 출발 버스 현황",  # <title>
            "bushexa.web.routes.unist_board.get_unist_board_data",
            _UNIST_SNAPSHOT,
        ),
        (
            "/timetable?day=0",
            "전체 시간표",  # <title>
            "bushexa.web.routes.unist_timetable.get_full_timetable_data",
            _TIMETABLE_SNAPSHOT,
        ),
        (
            "/running",
            "운행 이력 테이블",  # <title>
            None,
            None,
        ),
    ]

    for url, marker, mock_target, mock_return in routes_and_markers:
        if mock_target:
            with patch(mock_target, return_value=mock_return):
                resp = smoke_client.get(url)
        else:
            resp = smoke_client.get(url)

        assert resp.status_code == 200, (
            f"GET {url} expected 200, got {resp.status_code} "
            f"(독립 출처: P4 W15 AC-1, EC-2)"
        )
        html = resp.data.decode("utf-8")
        assert marker in html, (
            f"GET {url}: page marker {marker!r} not found in response "
            f"(마커는 <title>에서 — 항상 렌더됨)"
        )


# ─────────────────────────────────────────────────────────────────────────────
# AC-1 (admin 부분): GET /admin/login → 200
# ─────────────────────────────────────────────────────────────────────────────

def test_admin_login_page_200(smoke_client):
    """GET /admin/login이 200이고 로그인 폼 마커가 있는지 smoke 검증.

    독립 출처: P4 W10 AC-1, W15 AC-1 — admin login smoke.
    마커: 로그인 폼의 고유 마커 (항상 렌더됨).
    """
    resp = smoke_client.get("/admin/login")
    assert resp.status_code == 200, (
        f"GET /admin/login expected 200, got {resp.status_code}"
    )
    html = resp.data.decode("utf-8")
    # 로그인 페이지 고유 마커: action="/admin/login" 폼
    assert "/admin/login" in html, (
        "admin login form not found in /admin/login response"
    )


# ─────────────────────────────────────────────────────────────────────────────
# AC-1 (admin dashboard): 로그인 세션으로 GET /admin/ → 200
# 이월 1 검증: govtrack-card 마커 포함
# ─────────────────────────────────────────────────────────────────────────────

def test_admin_dashboard_after_login(smoke_client):
    """로그인 세션으로 GET /admin/ 이 200이고 대시보드 마커 + govtrack 카드 마커가 있는지.

    독립 출처: P4 W10 AC-2, W15 AC-1 — admin dashboard smoke.
    이월 1: govtrack 카드(id="govtrack-card")가 대시보드에 포함됨 확인 (F04 §4.5).
    마커: id="admin-dashboard"(항상 렌더), id="govtrack-card"(이월 1 배선 확인).
    """
    _inject_auth(smoke_client)
    resp = smoke_client.get("/admin/")
    assert resp.status_code == 200, (
        f"GET /admin/ after login expected 200, got {resp.status_code}"
    )
    html = resp.data.decode("utf-8")
    # 대시보드 고유 마커 (항상 렌더됨)
    assert "admin-dashboard" in html, (
        'id="admin-dashboard" marker not found in dashboard response'
    )
    # 이월 1: govtrack 카드 배선 확인
    assert "govtrack-card" in html, (
        'id="govtrack-card" not found in dashboard — govtrack card must be wired (이월 1, F04 §4.5)'
    )


# ─────────────────────────────────────────────────────────────────────────────
# AC-2: test_partials — partial 3종 200
# ─────────────────────────────────────────────────────────────────────────────

def test_partials(smoke_client):
    """partial 3종(/partial/board, /partial/stops, /partial/unist)이 200을 반환하는지 smoke.

    독립 출처: P4 W15 AC-2, EC-2 — partial GET 200.
    /partial/stops?stop_id=: SERACH_STOPS[0]를 사용 (유효한 stop_id).
    외부 네트워크 없이: domain 함수 mock.
    """
    # /partial/board
    with patch(
        "bushexa.web.routes.board.get_board_data",
        return_value=_BOARD_SNAPSHOT,
    ):
        resp_board = smoke_client.get("/partial/board")
    assert resp_board.status_code == 200, (
        f"GET /partial/board expected 200, got {resp_board.status_code} "
        f"(독립 출처: W15 AC-2)"
    )

    # /partial/stops?stop_id=<valid>
    valid_stop_id = SERACH_STOPS[0]
    with patch(
        "bushexa.web.routes.stops.get_stop_data",
        return_value=_STOP_SNAPSHOT,
    ):
        resp_stops = smoke_client.get(f"/partial/stops?stop_id={valid_stop_id}")
    assert resp_stops.status_code == 200, (
        f"GET /partial/stops?stop_id={valid_stop_id} expected 200, "
        f"got {resp_stops.status_code} (독립 출처: W15 AC-2)"
    )

    # /partial/unist
    with patch(
        "bushexa.web.routes.unist_board.get_unist_board_data",
        return_value=_UNIST_SNAPSHOT,
    ):
        resp_unist = smoke_client.get("/partial/unist")
    assert resp_unist.status_code == 200, (
        f"GET /partial/unist expected 200, got {resp_unist.status_code} "
        f"(독립 출처: W15 AC-2)"
    )
