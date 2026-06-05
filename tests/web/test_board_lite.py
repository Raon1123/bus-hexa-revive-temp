"""FASTER 모드 /lite 페이지 검증.

의도:
  test_lite_ok            — GET /lite → 200, 평문 HTML 표에 도착 행이 반영됨
  test_lite_is_barebones  — 무거운 웹폰트/htmx/JS/외부 자산을 로드하지 않음(즉시 렌더)
  test_lite_auto_refresh  — JS 없이 <meta http-equiv="refresh">로 갱신

독립 출처: 사용자 요구(디자인 사치 금지·阿部寛 페이지급 즉시 렌더) + ADR-010(cache 기반).
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from bushexa.domain.board import BoardRow, BoardSnapshot
from bushexa.web.app import create_app

_MOCK_SNAPSHOT = BoardSnapshot(
    current_time="08:30",
    weekday_str="평일",
    rows=[
        BoardRow(
            arrival_time="09:15",
            bus_number="713",
            present="구영리 출발",
            via_string="굴화주공 - 신복로터리",
            source="timetable",
            arrival_minutes=45,
            terminal="UNIST",
            rank="FIRST",
        )
    ],
    error=None,
    is_last_bus=False,
)


@pytest.fixture
def client(app_config_test):
    return create_app(app_config_test).test_client()


def _get_lite(client):
    # _build_snapshot 자체를 mock — DB/도메인 의존 없이 라우트/템플릿만 검증.
    with patch("bushexa.web.routes.board_lite._build_snapshot", return_value=_MOCK_SNAPSHOT), \
         patch("bushexa.web.routes.board_lite._last_fetched_at", return_value="2026-06-01T08:29:50+09:00"):
        return client.get("/lite")


def test_lite_ok(client):
    resp = _get_lite(client)
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    assert "713" in html and "UNIST" in html  # 행 데이터 반영
    assert "<table" in html


def test_lite_is_barebones(client):
    """디자인은 사치 — 웹폰트/htmx/외부 스크립트/스타일시트를 끌어오지 않는다."""
    resp = _get_lite(client)
    html = resp.data.decode("utf-8")
    assert "htmx" not in html
    assert "<script" not in html.lower()
    assert "Pretendard" not in html and "SeoulNamsan" not in html
    assert "<link" not in html.lower()  # 외부 CSS/폰트 링크 없음


def test_lite_auto_refresh(client):
    resp = _get_lite(client)
    html = resp.data.decode("utf-8")
    assert 'http-equiv="refresh"' in html
