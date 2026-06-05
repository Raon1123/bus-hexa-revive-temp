"""crawler 계층 파서 집약 (W10).

ADR-007: crawler → api_clients 의존이 허용된다. 파싱 로직의 **정본은 api_clients**
(tago.py / ulsan_bis.py)에 있고, 여기서는 crawler(recorder/poller)가 쓰기 편하도록
같은 순수 함수를 한 이름공간으로 재노출한다. 중복 구현 없음 — 단일 진실 소스.
"""
from __future__ import annotations

from bushexa.api_clients.errors import ParseError
from bushexa.api_clients.tago import (
    BusLocation,
    RouteStop,
    parse_busloc,
    parse_route,
)
from bushexa.api_clients.ulsan_bis import Arrival
from bushexa.api_clients.ulsan_bis import parse_arrivals as parse_busstop

__all__ = [
    "parse_busloc",
    "parse_route",
    "parse_busstop",
    "BusLocation",
    "RouteStop",
    "Arrival",
    "ParseError",
]
