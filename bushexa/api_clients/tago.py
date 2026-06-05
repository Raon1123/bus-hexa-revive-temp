"""국토부(TAGO) 버스 위치·노선 경유정류장 API 클라이언트 + 순수 파서.

- ``BusLcInfoInqireService/getRouteAcctoBusLcList``  : 실시간 차량 위치 (govtrack 입력)
- ``BusRouteInfoInqireService/getRouteAcctoThrghSttnList`` : 노선 경유 정류장 (ADR-011 stop 메타데이터 완화)

파서(`parse_busloc`/`parse_route`)는 네트워크와 무관한 순수 함수다. crawler/parsers.py(W10)가
이들을 재노출해 crawler 계층에서 사용한다. resultCode != '00'은 TagoError(ADR-013: 오류는
빈 결과와 구분해 신호).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from urllib.parse import unquote

import requests

from bushexa.api_clients.errors import ParseError, TagoError
from bushexa.data.constants import ULSAN_CITYCODE, ULSAN_PREFIX

logger = logging.getLogger("bushexa.api_clients.tago")

_BUSLOC_URL = "http://apis.data.go.kr/1613000/BusLcInfoInqireService/getRouteAcctoBusLcList"
_ROUTE_URL = "http://apis.data.go.kr/1613000/BusRouteInfoInqireService/getRouteAcctoThrghSttnList"


def _xml_tag(text: str, *tags: str) -> str:
    """XML 본문에서 주어진 태그 중 처음 매칭되는 내용을 반환(없으면 "")."""
    for tag in tags:
        m = re.search(rf"<{tag}>(.*?)</{tag}>", text, re.IGNORECASE | re.DOTALL)
        if m:
            return m.group(1).strip()
    return ""


def _xml_reason_code(text: str) -> str:
    """TAGO XML 오류 본문에서 사유 코드 추출(returnReasonCode/resultCode)."""
    return _xml_tag(text, "returnReasonCode", "resultCode") or "XML_ERROR"


def _xml_reason_msg(text: str) -> str:
    """TAGO XML 오류 본문에서 사람이 읽을 사유 메시지 추출."""
    return _xml_tag(text, "returnAuthMsg", "errMsg", "resultMsg") or text[:120].strip()


@dataclass(frozen=True)
class BusLocation:
    node_id: str  # USB prefix 제거됨
    node_name: str
    vehicle_no: str
    node_ord: int | None = None


@dataclass(frozen=True)
class RouteStop:
    node_ord: int
    node_id: str  # USB prefix 제거됨
    node_name: str
    route_id: str | None = None


@dataclass(frozen=True)
class TagoResponse:
    result_code: str
    total_count: int
    items: list[BusLocation]


def _items_as_list(body: dict) -> list[dict]:
    """``body.items.item``을 totalCount 0/1/N·dict/list 형태와 무관하게 list로 정규화.

    국토부 API는 단건일 때 item을 dict로, 다건일 때 list로 주는 가변성이 있다(F09 H6).
    totalCount==0이거나 items가 빈 문자열이면 빈 list.
    """
    total = int(body.get("totalCount", 0) or 0)
    if total == 0:
        return []
    items = body.get("items")
    if not items:  # "" 또는 None
        return []
    item = items.get("item")
    if item is None:
        return []
    return item if isinstance(item, list) else [item]


def parse_busloc(resp_json: dict) -> list[BusLocation]:
    """위치 응답 JSON → BusLocation 목록. nodeid의 USB prefix 제거. 필수 필드 누락 시 ParseError."""
    body = resp_json["response"]["body"]
    out: list[BusLocation] = []
    for item in _items_as_list(body):
        try:
            node_id = str(item["nodeid"]).removeprefix(ULSAN_PREFIX)
            node_name = item["nodenm"]
            vehicle_no = item["vehicleno"]
        except KeyError as exc:
            raise ParseError(f"busloc item에 필수 필드 누락: {exc}") from exc
        node_ord = item.get("nodeord")
        out.append(BusLocation(
            node_id=node_id, node_name=node_name, vehicle_no=vehicle_no,
            node_ord=int(node_ord) if node_ord is not None else None,
        ))
    return out


def parse_route(resp_json: dict) -> list[RouteStop]:
    """노선 경유 정류장 응답 JSON → RouteStop 목록 (ADR-011 완화 경로). nodeid의 USB prefix 제거."""
    body = resp_json["response"]["body"]
    out: list[RouteStop] = []
    for item in _items_as_list(body):
        try:
            node_ord = int(item["nodeord"])
            node_id = str(item["nodeid"]).removeprefix(ULSAN_PREFIX)
            node_name = item["nodenm"]
        except KeyError as exc:
            raise ParseError(f"route item에 필수 필드 누락: {exc}") from exc
        out.append(RouteStop(node_ord=node_ord, node_id=node_id, node_name=node_name,
                             route_id=item.get("routeid")))
    return out


class TagoClient:
    def __init__(self, api_key: str, *, base_url: str = _BUSLOC_URL,
                 route_base_url: str = _ROUTE_URL, city_code: int = ULSAN_CITYCODE,
                 timeout: float = 10.0):
        self.api_key = api_key
        self.base_url = base_url
        self.route_base_url = route_base_url
        self.city_code = city_code
        self.timeout = timeout

    def _params(self, route_id: str, page: int, rows: int) -> dict:
        # data.go.kr 서비스키 이중 인코딩 방지(레거시 crawl_loc와 동일 결과):
        # secret/key.txt가 'Encoding 키'(%2B 등 %-인코딩 포함)면 requests가 다시 인코딩해
        # %25..가 되어 SERVICE_KEY_IS_NOT_REGISTERED_ERROR가 난다. unquote로 먼저 디코딩하면
        # Encoding/Decoding 키 양쪽 모두 requests가 1회만 인코딩해 올바른 키가 전송된다.
        return {
            "serviceKey": unquote(self.api_key), "pageNo": page, "numOfRows": rows,
            "_type": "json", "cityCode": self.city_code,
            "routeId": ULSAN_PREFIX + route_id,
        }

    def _get_json(self, url: str, params: dict) -> dict:
        resp = requests.get(url, params=params, timeout=self.timeout)
        text = resp.text or ""
        stripped = text.lstrip()

        # TAGO 장애·키오류·쿼터초과는 흔히 본문이 비거나 XML(OpenAPI_ServiceResponse)로 온다.
        # 그대로 resp.json()하면 "Expecting value: line 1 column 1 (char 0)"라는 불투명한
        # JSONDecodeError가 나므로, 파싱 전에 감지해 원인이 담긴 TagoError로 변환한다.
        if not stripped:
            raise TagoError("EMPTY", f"빈 응답 (HTTP {resp.status_code})")
        if stripped[0] == "<":
            raise TagoError(
                _xml_reason_code(text),
                f"비정상 XML 응답 (HTTP {resp.status_code}): {_xml_reason_msg(text)}",
            )
        try:
            data = resp.json()
        except ValueError as exc:
            raise TagoError(
                "NON_JSON",
                f"JSON 파싱 실패 (HTTP {resp.status_code}): {text[:120]!r}",
            ) from exc

        try:
            header = data["response"]["header"]
            result_code = header["resultCode"]
        except (KeyError, TypeError) as exc:
            raise TagoError("NO_HEADER", f"응답에 header 없음: {text[:120]!r}") from exc
        if result_code != "00":
            raise TagoError(result_code, f"{result_code} {header.get('resultMsg', '')}".strip())
        return data

    def fetch_bus_locations(self, route_id: str, *, page: int = 1, rows: int = 70) -> TagoResponse:
        data = self._get_json(self.base_url, self._params(route_id, page, rows))
        body = data["response"]["body"]
        return TagoResponse(
            result_code=data["response"]["header"]["resultCode"],
            total_count=int(body.get("totalCount", 0) or 0),
            items=parse_busloc(data),
        )

    def fetch_route_stops(self, route_id: str, *, page: int = 1, rows: int = 70) -> list[RouteStop]:
        data = self._get_json(self.route_base_url, self._params(route_id, page, rows))
        return parse_route(data)
