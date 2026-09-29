"""노선도(route_diagram) 테스트 — 노선별 세로 정류장 목록.

테스트 의도:
  test_five_lines          — 5개 노선 카드·색
  test_termini             — 종점(명촌/덕하/꽃바위)이 timetable 종점 키와 일치
  test_unist_links_timetable — UNIST 정류장은 /busno?bus=<노선> 링크
  test_stop_links_valid    — 도착 링크 stop_id는 모두 SERACH_STOPS 안
  test_743_beomseo_upcoming — 10/3 이전 743 범서중은 "10/3부터" 예고, 이후 제거
  test_info_page_renders   — /info가 카드·링크를 렌더
  test_stops_preselect     — /stops?stop_id=가 정류소를 미리 선택
"""

from __future__ import annotations

from datetime import date

import pytest

from bushexa.data.constants import SERACH_STOPS
from bushexa.web.app import create_app
from bushexa.web.route_diagram import (
    COLORS,
    LINE_ORDER,
    LINE_STOPS,
    STOP_LABEL,
    STOP_LINK,
    build_route_lines,
)


def test_five_lines():
    lines = build_route_lines()
    assert [ln.line for ln in lines] == LINE_ORDER == ["513", "713", "743", "753", "1115"]
    assert {ln.line: ln.color for ln in lines} == COLORS


def test_termini():
    for line in ("713", "743", "753"):
        assert LINE_STOPS[line][-1] == "명촌"
    assert LINE_STOPS["513"][-1] == "덕하"
    assert LINE_STOPS["1115"][-1] == "꽃바위"


def test_unist_links_timetable():
    for ln in build_route_lines():
        unist = [s for s in ln.stops if s.is_unist]
        assert len(unist) == 1
        assert unist[0].href == f"/busno?bus={ln.line}"


def test_stop_links_valid():
    assert STOP_LINK, "링크 대상이 하나도 없음"
    for name, sid in STOP_LINK.items():
        assert sid in SERACH_STOPS, f"{name}: {sid}가 SERACH_STOPS에 없음"
        assert any(name in stops for stops in LINE_STOPS.values()), f"{name}이 어떤 노선에도 없음"


def test_beomseo_split():
    """구영리: 513·743은 범서중, 713·753·1115는 구영 — 서로 다른 정류장."""
    for line in ("513", "743"):
        assert "범서중" in LINE_STOPS[line] and "구영" not in LINE_STOPS[line]
    for line in ("713", "753", "1115"):
        assert "구영" in LINE_STOPS[line] and "범서중" not in LINE_STOPS[line]
    assert STOP_LABEL["범서중"] != STOP_LABEL["구영"]


def test_743_beomseo_upcoming():
    def notes(today):
        ln = next(x for x in build_route_lines(today) if x.line == "743")
        return [s.note for s in ln.stops if s.label == STOP_LABEL["범서중"]]

    assert notes(date(2026, 10, 2)) == ["10/3부터"]
    assert notes(date(2026, 10, 3)) == [None]


@pytest.fixture
def client(app_config_test):
    return create_app(app_config_test).test_client()


def test_info_page_renders(client):
    html = client.get("/info").get_data(as_text=True)
    assert html.count('<section class="route-card') == 5
    assert 'href="/busno?bus=743"' in html
    assert f'href="/stops?stop_id={STOP_LINK["천상"]}"' in html
    assert "<svg" not in html


def test_stops_preselect(client):
    sid = STOP_LINK["천상"]
    html = client.get(f"/stops?stop_id={sid}").get_data(as_text=True)
    assert f'value="{sid}" selected' in html
    assert f'hx-get="/partial/stops?stop_id={sid}"' in html
    bad = client.get("/stops?stop_id=nope").get_data(as_text=True)
    assert "hx-trigger=\"load\"" not in bad
