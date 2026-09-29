"""TAGO 열차정보·지하철정보 클라이언트 검증. 네트워크 0건 — 실응답 fixture(키 제거)를 responses 로 mock."""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pytest
import responses

from bushexa.api_clients.errors import ParseError, TagoError
from bushexa.api_clients.tago_rail import (
    SubwayInfoClient,
    TrainInfoClient,
    parse_metro_schedule,
    parse_trains,
)
from bushexa.time_utils import KST

FIXTURES = Path(__file__).parents[1] / "fixtures" / "tago_rail"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_parse_trains_normal():
    """태화강→부전 실응답 23편을 KST aware 시각·정수 운임으로 파싱한다(첫 편 06:52 무궁화호, 운임 "0"은 0)."""
    trains = parse_trains(_load("route_taehwagang_bujeon.json"))
    assert len(trains) == 23
    first = trains[0]
    assert first.train_no == "01896" and first.grade == "무궁화호"
    assert first.dep_at == datetime(2026, 9, 30, 6, 52, tzinfo=KST)
    assert first.arr_at == datetime(2026, 9, 30, 7, 57, tzinfo=KST)
    assert first.adult_charge == 0


def test_parse_trains_bad_time_raises():
    """출발시각이 14자리 숫자가 아니면 조용히 넘기지 않고 ParseError 로 올린다."""
    data = {"response": {"body": {"totalCount": 1, "items": {"item": {
        "trainno": "1", "traingradename": "KTX", "depplacename": "울산", "arrplacename": "부산",
        "depplandtime": "2026093007", "arrplandtime": "20260930075000"}}}}}
    with pytest.raises(ParseError):
        parse_trains(data)


@responses.activate
def test_fetch_trains_dedupes_upstream_duplicate_row():
    """열차정보가 같은 열차를 도착 1분 차이로 두 번 줘도(totalCount 24) 불완전 오류 없이 고유 23편을 돌려준다."""
    client = TrainInfoClient("key")
    responses.add(responses.GET, client.url, json=_load("route_duplicate_row.json"))
    trains = client.fetch_trains("NAT750726", "NAT750046", date(2026, 10, 9))
    assert len(trains) == 23
    assert [t.dep_at for t in trains] == sorted(t.dep_at for t in trains)


@responses.activate
def test_fetch_trains_empty_is_empty_list():
    """약 30일 너머 날짜처럼 결과 0건이면 오류가 아니라 빈 목록이다."""
    client = TrainInfoClient("key")
    responses.add(responses.GET, client.url, json=_load("route_empty.json"))
    assert client.fetch_trains("NATH13717", "NAT014445", date(2026, 10, 31)) == []


@responses.activate
def test_gateway_json_error_raises_with_reason_code():
    """신규 GW 엔드포인트의 JSON 게이트웨이 봉투(HTTP 403, 코드 30)를 TagoError('30')로 올린다."""
    client = TrainInfoClient("key")
    responses.add(responses.GET, client.url, json=_load("error_unregistered_key.json"), status=403)
    with pytest.raises(TagoError) as exc_info:
        client.fetch_trains("NATH13717", "NAT014445", date(2026, 9, 30))
    assert exc_info.value.result_code == "30"


@responses.activate
def test_fetch_trains_incomplete_raises():
    """페이지를 무시하는 응답이 totalCount 보다 적은 행만 주면 부분 결과 대신 ParseError."""
    data = _load("route_taehwagang_bujeon.json")
    data["response"]["body"]["totalCount"] = 30
    client = TrainInfoClient("key")
    responses.add(responses.GET, client.url, json=data)
    with pytest.raises(ParseError):
        client.fetch_trains("NAT750726", "NAT750046", date(2026, 9, 30))


def test_parse_metro_schedule_normal():
    """동해선 태화강 평일 상행 45건: 기점이라 도착은 None, 출발은 HH:MM:SS, 종착역 부전/망양."""
    rows = parse_metro_schedule(_load("subway_taehwagang_01U.json"))
    assert len(rows) == 45
    assert rows[0].dep_time == "05:36:00" and rows[0].arr_time is None
    assert rows[0].day_type == "01" and rows[0].direction == "U"
    assert {r.end_station_name for r in rows} == {"부전", "망양"}


def test_parse_metro_empty_saturday():
    """토요일(02) 시간표는 실제로 비어 있다 — 빈 목록으로 파싱된다."""
    assert parse_metro_schedule(_load("subway_taehwagang_02U_empty.json")) == []


@responses.activate
def test_fetch_station_schedule_follows_pages():
    """페이지를 지키는 지하철 응답은 totalCount 에 닿을 때까지 다음 페이지를 받는다."""
    full = _load("subway_taehwagang_01U.json")
    items = full["response"]["body"]["items"]["item"]
    client = SubwayInfoClient("key")
    for chunk in (items[:30], items[30:]):
        page = json.loads(json.dumps(full))
        page["response"]["body"]["items"]["item"] = chunk
        responses.add(responses.GET, client.url, json=page)
    rows = client.fetch_station_schedule("MTRKRK6K132", "01", "U")
    assert len(rows) == 45
    assert len(responses.calls) == 2
