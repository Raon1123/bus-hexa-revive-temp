"""CompositeLocationClient 검증: TAGO 우선 + 울산 BIS fallback(혼용).

네트워크 0건 — fake 클라이언트 주입. 기대값은 이 파일이 정의한 알려진 입력에서 정해짐(E-13).
"""
from __future__ import annotations

import pytest

from bushexa.api_clients.composite_location import CompositeLocationClient
from bushexa.api_clients.errors import TagoError
from bushexa.api_clients.tago import BusLocation, TagoResponse
from bushexa.api_clients.ulsan_bis import Arrival
from bushexa.data.constants import ROUTEID, STOP_IDS

# 알려진 노선: 195000178 = 713/명촌(시내)방면. 그 경유 정류장 중 하나를 fallback 대상으로 쓴다.
_ROUTE = "195000178"
_NODE = "196040231"  # STOP_IDS[_NODE] = '울산과학기술원정문 (시내)'
_NODE_NAME = STOP_IDS[_NODE]


class _FakeTago:
    def __init__(self, *, raise_exc=None, response=None):
        self._raise = raise_exc
        self._response = response
        self.calls = 0

    def fetch_bus_locations(self, route_id, *, page=1, rows=70):
        self.calls += 1
        if self._raise is not None:
            raise self._raise
        return self._response


class _FakeUlsan:
    def __init__(self, arrivals_by_stop):
        self._by_stop = arrivals_by_stop
        self.calls: list[str] = []

    def fetch_arrivals(self, stop_id, *, page=1, rows=50):
        self.calls.append(stop_id)
        return self._by_stop.get(stop_id, [])


def test_tago_success_no_fallback():
    """TAGO가 성공하면 그 응답을 그대로 쓰고 울산은 호출하지 않는다."""
    resp = TagoResponse(result_code="00", total_count=1,
                        items=[BusLocation(node_id=_NODE, node_name=_NODE_NAME, vehicle_no="T1")])
    tago = _FakeTago(response=resp)
    ulsan = _FakeUlsan({})
    c = CompositeLocationClient(tago, ulsan)

    out = c.fetch_bus_locations(_ROUTE)

    assert out is resp
    assert ulsan.calls == [], "TAGO 성공 시 울산 fallback이 호출되면 안 됨"


def test_tago_error_falls_back_to_ulsan():
    """TAGO가 TagoError면 울산 도착정보에서 위치를 보완한다(present_stop→node_id 역매핑)."""
    tago = _FakeTago(raise_exc=TagoError("30", "SERVICE_KEY_IS_NOT_REGISTERED_ERROR"))
    ulsan = _FakeUlsan({
        _NODE: [Arrival(route_id=_ROUTE, present_stop=_NODE_NAME, vehicle_no="U1", arrival_time=120)],
    })
    c = CompositeLocationClient(tago, ulsan)

    out = c.fetch_bus_locations(_ROUTE)

    assert [i.vehicle_no for i in out.items] == ["U1"]
    assert out.items[0].node_id == _NODE  # 이름→node_id 역매핑 성공
    assert ulsan.calls, "fallback 시 울산이 호출돼야 함"


def test_fallback_ignores_other_routes_and_unmapped_names():
    """fallback은 다른 노선 도착·매핑 불가 정류장명을 건너뛴다."""
    tago = _FakeTago(raise_exc=TagoError("EMPTY", "빈 응답"))
    ulsan = _FakeUlsan({
        _NODE: [
            Arrival(route_id=_ROUTE, present_stop=_NODE_NAME, vehicle_no="U1", arrival_time=60),
            Arrival(route_id="999999999", present_stop=_NODE_NAME, vehicle_no="OTHER", arrival_time=60),
            Arrival(route_id=_ROUTE, present_stop="존재하지않는정류장", vehicle_no="U2", arrival_time=60),
        ],
    })
    c = CompositeLocationClient(tago, ulsan)

    out = c.fetch_bus_locations(_ROUTE)

    vehicles = {i.vehicle_no for i in out.items}
    assert vehicles == {"U1"}, f"매핑 가능한 해당 노선 차량만 남아야 함, got {vehicles}"


def test_fallback_caches_stop_queries():
    """같은 stop_id를 짧은 TTL 내 두 번 조회하면 울산은 1회만 호출(사이클 내 중복 방지)."""
    tago = _FakeTago(raise_exc=TagoError("EMPTY", "빈 응답"))
    ulsan = _FakeUlsan({_NODE: [Arrival(route_id=_ROUTE, present_stop=_NODE_NAME, vehicle_no="U1", arrival_time=60)]})
    c = CompositeLocationClient(tago, ulsan, cache_ttl=60.0)

    c.fetch_bus_locations(_ROUTE)
    first_calls = len(ulsan.calls)
    c.fetch_bus_locations(_ROUTE)
    # 두 번째 호출은 캐시 사용 → 동일 stop 재조회 없음
    assert len(ulsan.calls) == first_calls, "TTL 내 동일 stop 재조회는 캐시되어야 함"
