"""W8 UlsanBisClient 검증. 기대값은 fixture XML 원문에서 직접 도출(E-13)."""
from __future__ import annotations

import logging
from pathlib import Path

import pytest
import responses

from bushexa.api_clients.errors import UlsanBisError
from bushexa.api_clients.ulsan_bis import UlsanBisClient, parse_timetable

FIXTURES = Path(__file__).parents[1] / "fixtures" / "ulsan"


@responses.activate
def test_parse_arrivals():
    """arrival_normal.xml mock에서 <row> 개수(2)만큼 Arrival을 파싱하고 각 필드가 원문과 일치하는지."""
    client = UlsanBisClient("key")
    xml = (FIXTURES / "arrival_normal.xml").read_bytes()
    responses.add(responses.GET, client.arrival_url, body=xml, content_type="text/xml")

    arrivals = client.fetch_arrivals("196040234")
    assert len(arrivals) == 2
    first = arrivals[0]
    assert first.route_id == "30300012"
    assert first.present_stop == "다운동"
    assert first.vehicle_no == "울산70바1234"
    assert first.arrival_time == 180  # 초


@responses.activate
def test_service_key_not_double_encoded():
    """울산 BIS도 serviceKey가 이중 인코딩되지 않는지(레거시 crawl_busstop 문자열 concat과 동일 결과).

    기대값(단일 인코딩)은 입력 키 'ab%2Bcd'에서 직접 정해짐(E-13).
    """
    client = UlsanBisClient("ab%2Bcd")
    responses.add(responses.GET, client.arrival_url, body=b"<root></root>", content_type="text/xml")
    client.fetch_arrivals("196040234")
    url = responses.calls[0].request.url
    assert "serviceKey=ab%2Bcd" in url, f"단일 인코딩 키여야 함: {url}"
    assert "%252B" not in url, f"serviceKey가 이중 인코딩됨: {url}"


@responses.activate
def test_empty_arrivals():
    """버스 없음 XML(<row> 없음)에서 빈 리스트를 반환하고 예외가 없는지."""
    client = UlsanBisClient("key")
    xml = (FIXTURES / "arrival_no_bus.xml").read_bytes()
    responses.add(responses.GET, client.arrival_url, body=xml, content_type="text/xml")
    assert client.fetch_arrivals("196040234") == []


@responses.activate
def test_network_error_logs_and_returns_empty():
    """[ADR-013] 일시적 네트워크 오류(미등록 URL→ConnectionError) 시 예외를 삼키지 않고 로그한 뒤
    빈 리스트를 반환해 poller 루프가 계속 도는지. (tago는 raise하는 비대칭과 대비)"""
    log = logging.getLogger("bushexa.api_clients.ulsan_bis")
    records: list[logging.LogRecord] = []

    class _H(logging.Handler):
        def emit(self, r):
            records.append(r)

    h = _H()
    log.addHandler(h)
    log.setLevel(logging.ERROR)
    try:
        result = UlsanBisClient("key").fetch_arrivals("S1")  # URL 미등록 → ConnectionError
    finally:
        log.removeHandler(h)

    assert result == []
    assert records, "ADR-013: 오류는 반드시 로그로 남아야 한다(silent swallow 금지)"


def test_parse_timetable_rows():
    """timetable XML에서 time('HHMM'→'HH:MM')과 direction(int)을 가진 TimetableRow 목록을 반환하는지."""
    xml = (FIXTURES / "timetable_normal.xml").read_bytes()
    rows = parse_timetable(xml)
    assert len(rows) == 3
    assert rows[0].time == "05:30"
    assert rows[0].direction == 1
    assert rows[1].time == "06:15"
    assert rows[1].direction == 2

# ── 오류 응답 감지 (2026-06-05 리뷰: 오류 본문≠빈 결과) ─────────────────────

_FAIL_XML = (
    "<tableInfo><pageNo>1</pageNo><numOfRows>10</numOfRows><totalCnt>0</totalCnt>"
    "<resultCode>300</resultCode><resultMsg>FAIL</resultMsg><list/></tableInfo>"
)
_GATEWAY_ERROR_XML = (
    "<OpenAPI_ServiceResponse><cmmMsgHeader>"
    "<returnReasonCode>30</returnReasonCode>"
    "<returnAuthMsg>SERVICE_KEY_IS_NOT_REGISTERED_ERROR</returnAuthMsg>"
    "</cmmMsgHeader></OpenAPI_ServiceResponse>"
)


@responses.activate
def test_timetable_fail_result_code_raises():
    """resultCode 300(FAIL) 본문을 빈 시간표로 파싱하지 않고 UlsanBisError로 raise —
    빈 데이터가 기존 {busno}.json을 덮어쓰는 사고 방지(2026-06-05 리뷰)."""
    client = UlsanBisClient("key")
    responses.add(responses.GET, client.timetable_url, body=_FAIL_XML, content_type="text/xml")
    with pytest.raises(UlsanBisError) as exc_info:
        client.fetch_timetable_page("713", 0)
    assert exc_info.value.result_code == "300"


@responses.activate
def test_timetable_gateway_error_raises():
    """키/쿼터 게이트웨이 오류 XML(HTTP 200)도 UlsanBisError로 raise."""
    client = UlsanBisClient("key")
    responses.add(responses.GET, client.timetable_url, body=_GATEWAY_ERROR_XML,
                  content_type="text/xml")
    with pytest.raises(UlsanBisError) as exc_info:
        client.fetch_timetable("713", 0)
    assert exc_info.value.result_code == "30"


@responses.activate
def test_timetable_http_error_raises():
    """비-200 HTTP 응답은 본문과 무관하게 UlsanBisError로 raise."""
    client = UlsanBisClient("key")
    responses.add(responses.GET, client.timetable_url, body="oops", status=500)
    with pytest.raises(UlsanBisError) as exc_info:
        client.fetch_timetable_page("713", 0)
    assert exc_info.value.result_code == "500"


@responses.activate
def test_arrival_error_body_logs_and_returns_empty():
    """[ADR-013 비대칭] poller 경로(fetch_arrivals)는 오류 본문도 루프를 죽이지 않고
    로그 후 빈 리스트로 강등하되, 침묵하지 않는다."""
    log = logging.getLogger("bushexa.api_clients.ulsan_bis")
    records: list[logging.LogRecord] = []

    class _H(logging.Handler):
        def emit(self, r):
            records.append(r)

    h = _H()
    log.addHandler(h)
    log.setLevel(logging.ERROR)
    try:
        client = UlsanBisClient("key")
        responses.add(responses.GET, client.arrival_url, body=_GATEWAY_ERROR_XML,
                      content_type="text/xml")
        result = client.fetch_arrivals("196040234")
    finally:
        log.removeHandler(h)

    assert result == []
    assert records, "오류 응답은 로그로 남아야 한다(silent swallow 금지)"
