"""W10 parsers 검증(crawler.parsers 재노출 경유). 기대값은 tago fixture 원문에서(E-13)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from bushexa.crawler.parsers import ParseError, parse_busloc, parse_route

FIXTURES = Path(__file__).parents[1] / "fixtures" / "tago"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_parses_normal_response():
    """busloc_normal.json(3 items)을 parse_busloc에 주면 BusLocation 3개를 반환하는지."""
    locs = parse_busloc(_load("busloc_normal.json"))
    assert len(locs) == 3
    assert locs[0].node_name == "울산과학기술원"
    assert locs[0].vehicle_no == "울산70자1234"


def test_handles_total_count_zero():
    """totalCount=0(items="") 응답에서 빈 리스트를 반환하는지."""
    assert parse_busloc(_load("busloc_empty.json")) == []


def test_handles_single_dict_form():
    """totalCount=1이고 items.item이 단일 dict인 응답을 1개 리스트로 정규화하는지(H6)."""
    assert len(parse_busloc(_load("busloc_single_dict.json"))) == 1


def test_handles_single_list_form():
    """totalCount=1이고 items.item이 list인 응답도 1개 리스트로 처리하는지(H6)."""
    assert len(parse_busloc(_load("busloc_single_list.json"))) == 1


def test_strips_usb_prefix():
    """모든 결과 node_id가 'USB'로 시작하지 않는지(접두사 제거)."""
    for name in ("busloc_normal.json", "busloc_single_dict.json", "busloc_single_list.json"):
        for loc in parse_busloc(_load(name)):
            assert not loc.node_id.startswith("USB")


def test_missing_field_raises():
    """vehicleno 필드가 빠진 item에 대해 ParseError가 발생하는지."""
    bad = {"response": {"body": {"totalCount": 1,
           "items": {"item": {"nodeid": "USB1", "nodenm": "X"}}}}}
    with pytest.raises(ParseError):
        parse_busloc(bad)


def test_parse_route_stops():
    """[ADR-011] route_stops.json에서 RouteStop 3개를 node_ord 순으로 파싱하고 USB를 제거하는지."""
    stops = parse_route(_load("route_stops.json"))
    assert len(stops) == 3
    assert stops[0].node_ord == 1
    assert all(not s.node_id.startswith("USB") for s in stops)
