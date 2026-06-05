"""TAGO(국토부) 위치조회 + 울산 BIS 도착정보 혼용 위치 소스.

govtrack 데몬은 노선별 차량 위치를 TagoClient로 조회한다. TAGO가 장애·키 미등록·
쿼터초과로 실패하면(빈/XML 응답 → TagoError) 데몬이 해당 노선을 통째로 건너뛴다.

CompositeLocationClient는 TagoClient 인터페이스(`fetch_bus_locations`)를 그대로 노출하되,
TAGO 실패 시 **울산 BIS 도착정보(present_stop)** 로부터 위치를 보완해 govtrack이 계속
수집하도록 한다(사용자 요청: "TAGO 위치조회와 울산버스 API를 적절히 혼용").

한계: 울산 도착정보의 present_stop은 정류장 '이름'이라 STOP_IDS(이름→node_id) 역매핑이
필요하다. 이름이 매칭되지 않으면(노선 외/표기 상이) 해당 항목은 건너뛴다. 즉 fallback은
best-effort 이며 TAGO 정상 동작이 1순위다.
"""
from __future__ import annotations

import logging
import re
import time
from collections import Counter

import requests

from bushexa.api_clients.errors import TagoError
from bushexa.api_clients.tago import BusLocation, TagoResponse
from bushexa.data.constants import ROUTEID, STOP_IDS

logger = logging.getLogger("bushexa.api_clients.composite_location")

_PAREN_RE = re.compile(r"\s*\([^)]*\)")


def _clean(name: str) -> str:
    return _PAREN_RE.sub("", name or "").strip()


def _build_name_index() -> tuple[dict[str, str], dict[str, str]]:
    """STOP_IDS(node_id→name)로부터 이름→node_id 역인덱스 2종을 만든다.

    - exact: 원문 이름 → node_id (먼저 본 것 우선)
    - clean: 괄호 제거 이름 → node_id (괄호 제거 후 유일한 경우만; 모호하면 제외)
    """
    exact: dict[str, str] = {}
    for nid, nm in STOP_IDS.items():
        exact.setdefault(nm, nid)
    clean_counts = Counter(_clean(nm) for nm in STOP_IDS.values())
    clean: dict[str, str] = {}
    for nid, nm in STOP_IDS.items():
        c = _clean(nm)
        if c and clean_counts[c] == 1:
            clean.setdefault(c, nid)
    return exact, clean


class CompositeLocationClient:
    """TAGO 우선 + 울산 BIS fallback 위치 소스. TagoClient와 동일한 호출부 인터페이스."""

    def __init__(self, tago, ulsan, *, cache_ttl: float = 8.0):
        """``tago``: TagoClient(또는 호환). ``ulsan``: UlsanBisClient(또는 호환).

        ``cache_ttl``: 한 폴링 사이클 내 여러 노선이 같은 정류장을 조회할 때 울산 호출을
        중복하지 않도록 stop_id별 도착정보를 짧게 캐시(초).
        """
        self.tago = tago
        self.ulsan = ulsan
        self.cache_ttl = cache_ttl
        self._exact, self._clean = _build_name_index()
        self._cache: dict[str, tuple[float, list]] = {}

    # -- public (TagoClient 호환) -------------------------------------------
    def fetch_bus_locations(self, route_id: str, *, page: int = 1, rows: int = 70) -> TagoResponse:
        try:
            return self.tago.fetch_bus_locations(route_id, page=page, rows=rows)
        except (TagoError, requests.exceptions.RequestException) as exc:
            logger.warning(
                "TAGO 위치조회 실패(%s) → 울산 BIS fallback: route=%s", exc, route_id
            )
            return self._ulsan_fallback(route_id)

    def fetch_route_stops(self, route_id: str, *, page: int = 1, rows: int = 70):
        # 경유 정류장 조회는 TAGO 전용(울산 대체 없음). 그대로 위임.
        return self.tago.fetch_route_stops(route_id, page=page, rows=rows)

    # -- fallback -----------------------------------------------------------
    def _arrivals_cached(self, stop_id: str) -> list:
        now = time.monotonic()
        hit = self._cache.get(stop_id)
        if hit is not None and (now - hit[0]) < self.cache_ttl:
            return hit[1]
        arrivals = self.ulsan.fetch_arrivals(stop_id)  # 울산 클라이언트는 오류 시 [] 반환
        self._cache[stop_id] = (now, arrivals)
        return arrivals

    def _resolve_node(self, present_stop: str) -> str | None:
        return self._exact.get(present_stop) or self._clean.get(_clean(present_stop))

    def _ulsan_fallback(self, route_id: str) -> TagoResponse:
        entry = ROUTEID.get(route_id)
        if not entry:
            return TagoResponse(result_code="ULSAN", total_count=0, items=[])
        stop_ids = entry[3]
        by_vehicle: dict[str, BusLocation] = {}
        for sid in stop_ids:
            for arr in self._arrivals_cached(sid):
                if arr.route_id != route_id:
                    continue
                node_id = self._resolve_node(arr.present_stop)
                if node_id is None:
                    continue
                # 차량별 1건(가장 마지막 본 위치로 갱신)
                by_vehicle[arr.vehicle_no] = BusLocation(
                    node_id=node_id, node_name=arr.present_stop, vehicle_no=arr.vehicle_no,
                )
        items = list(by_vehicle.values())
        if items:
            logger.info("울산 fallback: route=%s 차량 %d대 위치 보완", route_id, len(items))
        return TagoResponse(result_code="ULSAN", total_count=len(items), items=items)
