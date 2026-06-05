"""recorder/daemon 단위테스트용 대역(fake) 모음. (``_`` 접두사 → pytest가 수집하지 않음)

기대값은 여기서 만든 입력에서 직접 도출되므로 구현과 독립적이다(E-13).
"""
from __future__ import annotations

from bushexa.api_clients.tago import BusLocation, TagoResponse
from bushexa.crawler.state import VehicleTimeline


def make_response(items, result_code="00"):
    """(node_id, node_name, vehicle_no) 튜플 목록 → TagoResponse."""
    locs = [BusLocation(node_id=n, node_name=nm, vehicle_no=v) for n, nm, v in items]
    return TagoResponse(result_code=result_code, total_count=len(locs), items=locs)


class FakeTagoClient:
    """고정 응답(또는 매 호출 예외)을 돌려주는 TagoClient 대역."""

    def __init__(self, by_route=None, raise_exc=None):
        self.by_route = dict(by_route or {})
        self.raise_exc = raise_exc
        self.calls: list[str] = []

    def fetch_bus_locations(self, route_id, *, page=1, rows=70):
        self.calls.append(route_id)
        if self.raise_exc is not None:
            raise self.raise_exc
        return self.by_route.get(route_id, TagoResponse("00", 0, []))


class SequenceTagoClient:
    """호출마다 미리 정해진 응답/예외를 순서대로 돌려주는 대역(사이클 시퀀스 검증용)."""

    def __init__(self, sequence):
        # sequence: list of (TagoResponse | Exception)
        self._seq = list(sequence)
        self._i = 0
        self.calls: list[str] = []

    def fetch_bus_locations(self, route_id, *, page=1, rows=70):
        self.calls.append(route_id)
        item = self._seq[min(self._i, len(self._seq) - 1)]
        self._i += 1
        if isinstance(item, Exception):
            raise item
        return item


class FaultyState:
    """특정 vehicle_no에서 record가 예외를 던지는 state 대역(H4 격리 검증).

    그 외 차량은 실제 VehicleTimeline에 위임하므로, '한 차량 실패가 다른 차량을 막지 않음'을
    정직하게 검증한다(try/except 제거 시 예외가 전파되어 테스트가 실패).
    """

    def __init__(self, fail_vehicle, inner=None):
        self.fail_vehicle = fail_vehicle
        self.inner = inner or VehicleTimeline()

    def record(self, route_id, vehicle_no, node_id, ts):
        if vehicle_no == self.fail_vehicle:
            raise RuntimeError(f"injected fault for {vehicle_no}")
        return self.inner.record(route_id, vehicle_no, node_id, ts)

    def last_node(self, route_id, vehicle_no):
        return self.inner.last_node(route_id, vehicle_no)

    def warm_from_repo(self, repo, since):
        return self.inner.warm_from_repo(repo, since)

    def persist(self):
        self.inner.persist()
