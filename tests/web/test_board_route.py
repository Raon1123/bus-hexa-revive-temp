"""W2 테스트: board route + HTMX partial (F01, TP-001).

테스트 의도:
  test_board_ok         — GET /board → 200, id="board-table", hx-trigger="every 15s"
  test_partial_fragment — GET /partial/board → 200, 조각만 (<html> 없음)
  test_board_uses_domain — mock get_board_data 가 주는 행이 HTML 에 반영됨

E-13 준수: 기대값은 아래 hand-built BoardSnapshot (알려진 입력) 에서 독립적으로 정해짐.
도메인 실제 구현값을 읽어 기대값을 세우는 tautology 없음.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from bushexa.domain.board import BoardRow, BoardSnapshot
from bushexa.web.app import create_app

# ---------------------------------------------------------------------------
# Known test fixture — independent from domain implementation (E-13)
# ---------------------------------------------------------------------------

_KNOWN_ROW = BoardRow(
    arrival_time="09:15",
    bus_number="713",
    present="구영리 출발",
    via_string="굴화주공 - 신복로터리",
    source="timetable",
    arrival_minutes=45,
    terminal="UNIST",
    rank="FIRST",
)

_MOCK_SNAPSHOT = BoardSnapshot(
    current_time="08:30",
    weekday_str="평일",
    rows=[_KNOWN_ROW],
    error=None,
    is_last_bus=False,
)


@pytest.fixture
def app(app_config_test):
    return create_app(app_config_test)


@pytest.fixture
def client(app):
    return app.test_client()


# ---------------------------------------------------------------------------
# AC-1 — GET /board → 200, id="board-table", hx-trigger="every 15s"
# ---------------------------------------------------------------------------

def test_board_ok(client):
    """GET /board 가 200 이고 HTML 에 자동 갱신 컨테이너와 hx-trigger 가 있는지 검증.

    독립 출처: P4 W2 AC-1, TP-001 §2 설계 명세.
    """
    with patch(
        "bushexa.web.routes.board.get_board_data",
        return_value=_MOCK_SNAPSHOT,
    ):
        resp = client.get("/board")

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    html = resp.data.decode("utf-8")

    assert 'id="board-table"' in html, (
        'id="board-table" container missing from /board response'
    )
    assert 'hx-trigger="every 15s"' in html, (
        'hx-trigger="every 15s" missing from /board response (TP-001 §8)'
    )


# ---------------------------------------------------------------------------
# AC-2 — GET /partial/board → 200, 조각만 (<html> 없음, hx-trigger 없음)
# ---------------------------------------------------------------------------

def test_partial_fragment(client):
    """GET /partial/board 가 전체 페이지가 아닌 테이블 행 조각만 반환하는지 검증.

    독립 출처: P4 W2 AC-2, TP-001 §8 — "partial은 <html> 없는 행 조각만 반환".
    """
    with patch(
        "bushexa.web.routes.board.get_board_data",
        return_value=_MOCK_SNAPSHOT,
    ):
        resp = client.get("/partial/board")

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    html = resp.data.decode("utf-8")

    # 조각이므로 <html> 태그가 없어야 한다 (TP-001 §8 명시)
    assert "<html" not in html.lower(), (
        "Partial response must not contain <html> tag — it is a fragment only"
    )

    # hx-trigger 는 메인 페이지(/board)에만 있어야 한다 (W2 지시사항)
    assert "hx-trigger" not in html, (
        "hx-trigger should only be on the main /board page, not on the partial fragment"
    )


# ---------------------------------------------------------------------------
# test_board_uses_domain — mock 행이 렌더 HTML 에 반영
# ---------------------------------------------------------------------------

def test_board_uses_domain(client):
    """mock domain.get_board_data 가 주는 알려진 행이 렌더 HTML 에 반영되는지 검증.

    독립 출처: _KNOWN_ROW 는 이 테스트 파일에서 수기로 정의한 알려진 입력값 (E-13).
    구현 get_board_data 의 실제 출력값을 읽어 기대값을 세우는 tautology 없음.
    """
    with patch(
        "bushexa.web.routes.board.get_board_data",
        return_value=_MOCK_SNAPSHOT,
    ):
        resp = client.get("/board")

    html = resp.data.decode("utf-8")

    # 알려진 입력 행의 필드가 HTML 에 렌더됐는지 확인
    assert "713" in html, "Bus number '713' from mock row not found in rendered HTML"
    assert "09:15" in html, "Arrival time '09:15' from mock row not found in rendered HTML"
    assert "구영리 출발" in html, "Present stop from mock row not found in rendered HTML"
