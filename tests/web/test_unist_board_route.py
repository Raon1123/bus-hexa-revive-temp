"""W6 테스트: unist_board route + partial (F07, TP-004).

테스트 의도:
  test_six_cards — GET /unist → 200, class="bus-card" 정확히 6개
  test_partial   — GET /partial/unist → 200, id="unist-grid" 조각만 (전체 페이지 아님)

E-13 준수: 기대값은 hand-built UnistBoardSnapshot (알려진 입력) 에서 독립적으로 정해짐.
6개 카드 수는 F07 §4.4 설계 명세(513 양방향 2 + UNIST 출발 4 = 6).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from bushexa.domain.unist_board import BusCard, CardEntry, UnistBoardSnapshot
from bushexa.web.app import create_app


# ---------------------------------------------------------------------------
# Known test fixture — 6카드 (AC-1), E-13 독립 출처
# ---------------------------------------------------------------------------

def _make_card(busno: str, direction: str) -> BusCard:
    return BusCard(
        busno=busno,
        direction=direction,
        entries=[CardEntry(text="08:30 출발 예정", source="timetable")],
        is_last_bus=False,
    )


_MOCK_SNAPSHOT = UnistBoardSnapshot(
    cards=[
        _make_card("513", "삼남 (울산역) 방면"),
        _make_card("513", "덕하 (시내) 방면"),
        _make_card("713", "명촌 (시내) 방면"),
        _make_card("743", "명촌 (시내) 방면"),
        _make_card("753", "명촌 (시내) 방면"),
        _make_card("1115", "꽃바위 (시내) 방면"),
    ],
    bis_error=False,
)


@pytest.fixture
def app(app_config_test):
    return create_app(app_config_test)


@pytest.fixture
def client(app):
    return app.test_client()


# ---------------------------------------------------------------------------
# AC-1 — GET /unist → 200 + 정확히 6개 카드
# ---------------------------------------------------------------------------

def test_six_cards(client):
    """/unist HTML에 정확히 6개 카드(class="bus-card")가 렌더되는지 검증.

    독립 출처: P4 W6 AC-1, F07 §4.4 — 513×2 + UNIST 출발 4개 = 6카드.
    """
    with patch(
        "bushexa.web.routes.unist_board.get_unist_board_data",
        return_value=_MOCK_SNAPSHOT,
    ):
        resp = client.get("/unist")

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    html = resp.data.decode("utf-8")
    import re
    # Match <div class="bus-card"> or <div class="bus-card last-bus"> exactly (not bus-card-*)
    card_count = len(re.findall(r'<div\s+class="bus-card(?:\s[^"]*)?"\s*>', html))
    assert card_count == 6, (
        f"Expected exactly 6 bus-card elements, found {card_count}"
    )


# ---------------------------------------------------------------------------
# AC-2 — GET /partial/unist → id="unist-grid" 조각만 (전체 페이지 아님)
# ---------------------------------------------------------------------------

def test_partial(client):
    """/partial/unist가 id="unist-grid" 조각만 반환하는지(전체 페이지 아님) 검증.

    독립 출처: P4 W6 AC-2, TP-004 §8 — partial은 <html> 없는 조각.
    """
    with patch(
        "bushexa.web.routes.unist_board.get_unist_board_data",
        return_value=_MOCK_SNAPSHOT,
    ):
        resp = client.get("/partial/unist")

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    html = resp.data.decode("utf-8")

    # 조각이므로 <html> 태그가 없어야 한다
    assert "<html" not in html.lower(), (
        "Partial response must not contain <html> tag — it is a fragment only"
    )
    # id="unist-grid" 가 있어야 한다
    assert 'id="unist-grid"' in html, (
        'id="unist-grid" not found in /partial/unist response'
    )


def test_unist_cards_english_entries(client):
    """?lang=en 이면 카드의 실시간·시간표 항목과 빈 카드 문구가 영문으로 렌더된다."""
    snap = UnistBoardSnapshot(
        cards=[
            BusCard("513", "덕하 (시내) 방면", [
                CardEntry(text="천상 (시내) 3분5초", source="live", stop="천상 (시내)", seconds=185),
                CardEntry(text="08:30 출발 예정", source="timetable", time="08:30"),
            ], False),
            BusCard("713", "명촌 (시내) 방면", [], True),
        ],
        bis_error=False,
    )
    with patch("bushexa.web.routes.unist_board.get_unist_board_data", return_value=snap):
        body = client.get("/unist?lang=en").get_data(as_text=True)
    assert "3m 5s" in body
    assert "Departs 08:30" in body
    assert "Service ended or no info" in body
    assert "출발 예정" not in body
