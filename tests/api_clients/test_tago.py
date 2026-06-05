"""W7 TagoClient 검증. 실제 네트워크 0건 — responses로 fixture를 mock. 기대값은 fixture 원문에서(E-13)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import requests
import responses

from bushexa.api_clients.errors import TagoError
from bushexa.api_clients.tago import TagoClient

FIXTURES = Path(__file__).parents[1] / "fixtures" / "tago"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_base_url():
    """base_url이 국토부 BusLcInfo 엔드포인트(getRouteAcctoBusLcList)를 가리키는지."""
    assert "getRouteAcctoBusLcList" in TagoClient("dummy").base_url


@responses.activate
def test_parse_normal():
    """busloc_normal.json mock에서 total_count=3, BusLocation 3개, node_id의 USB prefix 제거 확인."""
    client = TagoClient("key")
    responses.add(responses.GET, client.base_url, json=_load("busloc_normal.json"))

    resp = client.fetch_bus_locations("195000178")
    assert resp.total_count == 3
    assert len(resp.items) == 3
    assert all(not b.node_id.startswith("USB") for b in resp.items)
    # fixture 첫 항목: nodeid USB246000123 -> 246000123, vehicleno 울산70자1234
    assert resp.items[0].node_id == "246000123"
    assert resp.items[0].vehicle_no == "울산70자1234"


@responses.activate
def test_error_code_raises():
    """busloc_error_99.json(resultCode=99) mock에서 TagoError가 발생하는지(ADR-013 오류 신호)."""
    client = TagoClient("key")
    responses.add(responses.GET, client.base_url, json=_load("busloc_error_99.json"))
    with pytest.raises(TagoError):
        client.fetch_bus_locations("195000178")


@responses.activate
def test_no_real_network():
    """등록하지 않은 URL을 호출하면 ConnectionError로 가드되는지(테스트 중 실호출 0건 보증)."""
    with pytest.raises(requests.exceptions.ConnectionError):
        TagoClient("key").fetch_bus_locations("195000178")


@responses.activate
def test_service_key_not_double_encoded():
    """data.go.kr 'Encoding 키'(%2B 포함)가 requests로 이중 인코딩되지 않는지(레거시 동작 일치).

    회귀 의도: 이중 인코딩 시 SERVICE_KEY_IS_NOT_REGISTERED_ERROR 발생. 기대값(단일 인코딩)은
    입력 키 'ab%2Bcd'에서 직접 정해짐(E-13).
    """
    client = TagoClient("ab%2Bcd")  # Encoding 키 형태(이미 %-인코딩됨)
    responses.add(responses.GET, client.base_url, json=_load("busloc_normal.json"))
    client.fetch_bus_locations("195000178")
    url = responses.calls[0].request.url
    assert "serviceKey=ab%2Bcd" in url, f"단일 인코딩 키여야 함: {url}"
    assert "%252B" not in url, f"serviceKey가 이중 인코딩됨: {url}"


@responses.activate
def test_empty_body_raises_clear_tago_error():
    """빈 응답 본문을 resp.json()으로 깨뜨리지 않고 명확한 TagoError로 변환하는지.

    회귀 의도: 운영 로그 'Expecting value: line 1 column 1 (char 0)' 불투명 오류 방지.
    기대값(빈 본문→오류)은 이 테스트가 정의한 알려진 입력에서 정해짐(E-13).
    """
    client = TagoClient("key")
    responses.add(responses.GET, client.base_url, body="", status=200)
    with pytest.raises(TagoError) as ei:
        client.fetch_bus_locations("195000222")
    assert "빈 응답" in str(ei.value)


@responses.activate
def test_xml_error_body_extracts_reason():
    """TAGO가 JSON 대신 XML 오류(서비스키 미등록 등)를 줄 때 사유를 추출해 TagoError로 신호.

    기대값(코드 30 / SERVICE_KEY 메시지)은 아래 mock XML 원문에서 직접 옴(E-13).
    """
    client = TagoClient("key")
    xml = (
        "<OpenAPI_ServiceResponse><cmmMsgHeader>"
        "<returnAuthMsg>SERVICE_KEY_IS_NOT_REGISTERED_ERROR</returnAuthMsg>"
        "<returnReasonCode>30</returnReasonCode>"
        "</cmmMsgHeader></OpenAPI_ServiceResponse>"
    )
    responses.add(responses.GET, client.base_url, body=xml, status=200,
                  content_type="application/xml")
    with pytest.raises(TagoError) as ei:
        client.fetch_bus_locations("195000222")
    assert ei.value.result_code == "30"
    assert "SERVICE_KEY_IS_NOT_REGISTERED_ERROR" in str(ei.value)
