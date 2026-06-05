"""W9 HolidayClient 검증. 기대값은 fixture에서 직접 센 공휴일 수·날짜(E-13).

2026-06-05 리뷰 회귀 테스트 포함: serviceKey 이중 인코딩(tago/ulsan과 동일 unquote),
오류 응답(HTTP 200 XML)을 빈 결과로 삼키지 않고 HolidayError로 raise.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
import responses

from bushexa.api_clients.errors import HolidayError
from bushexa.api_clients.holiday import HolidayClient, parse_holidays

FIXTURES = Path(__file__).parents[1] / "fixtures" / "holiday"

_OK_EMPTY_XML = (
    '<?xml version="1.0"?><response><header><resultCode>00</resultCode>'
    "<resultMsg>NORMAL SERVICE.</resultMsg></header><body><items/></body></response>"
)
_GATEWAY_ERROR_XML = (
    "<OpenAPI_ServiceResponse><cmmMsgHeader>"
    "<returnReasonCode>30</returnReasonCode>"
    "<returnAuthMsg>SERVICE_KEY_IS_NOT_REGISTERED_ERROR</returnAuthMsg>"
    "</cmmMsgHeader></OpenAPI_ServiceResponse>"
)
_RESULT_ERROR_XML = (
    '<?xml version="1.0"?><response><header><resultCode>22</resultCode>'
    "<resultMsg>LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS</resultMsg></header></response>"
)


@responses.activate
def test_parse_holidays():
    """2026.xml mock에서 <locdate> 개수(15)만큼 date를 반환하고 알려진 공휴일이 포함되는지."""
    client = HolidayClient("key")
    xml = (FIXTURES / "2026.xml").read_bytes()
    responses.add(responses.GET, client.base_url, body=xml, content_type="text/xml")

    days = client.fetch(2026, 1)
    assert len(days) == 15
    assert date(2026, 1, 1) in days
    assert date(2026, 6, 6) in days  # 현충일


def test_empty_month_returns_empty():
    """locdate가 없는 응답에서 빈 리스트를 반환하고 예외가 없는지."""
    empty_xml = '<?xml version="1.0"?><response><body><items></items></body></response>'
    assert parse_holidays(empty_xml) == []


@responses.activate
def test_fetch_empty_month_ok():
    """resultCode 00 + locdate 없음(진짜 무공휴일 달)은 정상 빈 리스트."""
    client = HolidayClient("key")
    responses.add(responses.GET, client.base_url, body=_OK_EMPTY_XML, content_type="text/xml")
    assert client.fetch(2026, 4) == []


@responses.activate
def test_service_key_not_double_encoded():
    """공휴일 클라이언트도 serviceKey가 이중 인코딩되지 않는지 — tago/ulsan에는 있던
    unquote가 이 클라이언트에만 빠져 있던 회귀(2026-06-05 리뷰).

    기대값(단일 인코딩)은 입력 키 'ab%2Bcd'에서 직접 정해짐(E-13).
    """
    client = HolidayClient("ab%2Bcd")
    responses.add(responses.GET, client.base_url, body=_OK_EMPTY_XML, content_type="text/xml")
    client.fetch(2026, 6)
    url = responses.calls[0].request.url
    assert "serviceKey=ab%2Bcd" in url, f"단일 인코딩 키여야 함: {url}"
    assert "%252B" not in url, f"serviceKey가 이중 인코딩됨: {url}"


@responses.activate
def test_gateway_error_raises():
    """키/쿼터 오류(HTTP 200 게이트웨이 XML)를 빈 결과로 삼키지 않고 HolidayError로 raise —
    캐시가 빈 값으로 오염되지 않도록(2026-06-05 리뷰)."""
    client = HolidayClient("key")
    responses.add(responses.GET, client.base_url, body=_GATEWAY_ERROR_XML,
                  content_type="text/xml")
    with pytest.raises(HolidayError) as exc_info:
        client.fetch(2026, 6)
    assert exc_info.value.result_code == "30"


@responses.activate
def test_result_code_error_raises():
    """resultCode != 00 서비스 오류도 HolidayError로 raise."""
    client = HolidayClient("key")
    responses.add(responses.GET, client.base_url, body=_RESULT_ERROR_XML,
                  content_type="text/xml")
    with pytest.raises(HolidayError) as exc_info:
        client.fetch(2026, 6)
    assert exc_info.value.result_code == "22"
