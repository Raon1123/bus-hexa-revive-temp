"""TAGO(국토부) 위치조회 + 울산 BIS 도착정보 혼용 위치 소스.

govtrack 데몬은 노선별 차량 위치를 TagoClient로 조회한다. TAGO가 장애·키 미등록·
쿼터초과로 실패하면(빈/XML 응답 → TagoError) 데몬이 해당 노선을 통째로 건너뛴다.

CompositeLocationClient는 TagoClient 인터페이스(`fetch_bus_locations`)를 그대로 노출하되,
TAGO 실패 시 **울산 BIS 도착정보(present_stop)** 로부터 위치를 보완해 govtrack이 계속
수집하도록 한다(사용자 요청: "TAGO 위치조회와 울산버스 API를 적절히 혼용").

한계: 울산 도착정보의 present_stop은 정류장 '이름'이라 STOP_IDS(이름→node_id) 역매핑이
필요하다. 이름이 매칭되지 않으면(노선 외/표기 상이) 해당 항목은 건너뛴다. 즉 fallback은
best-effort 이며 TAGO 정상 동작이 1순위다.

NOTE(감사 2-2): present_stop 의미 불확실성 — 울산 BIS ``presentstopnm`` 필드가
"현재 위치 정류소"인지 "다음 도착 정류소"인지 API 문서로 확인되지 않았다. 의미가 다르면
통과 기록이 항상 1정류소 앞서거나 뒤처진다. 이 불확실성은 본 코드에서 해소할 수 없으며
API 문서 확인 시 주석 갱신 필요.
"""
from __future__ import annotations

import logging
import time
from collections import Counter, defaultdict

import requests

from bushexa.api_clients.errors import TagoError
from bushexa.api_clients.tago import BusLocation, TagoResponse
from bushexa.data.constants import ROUTEID, STOP_IDS, clean_stop_name as _clean

logger = logging.getLogger("bushexa.api_clients.composite_location")


def _build_name_index() -> tuple[dict[str, str], dict[str, str]]:
    """STOP_IDS(node_id→name)로부터 이름→node_id 역인덱스 2종을 만든다.

    - exact: 원문 이름 → node_id (먼저 본 것 우선)
    - clean: 괄호 제거 이름 → node_id (괄호 제거 후 유일한 경우만; 모호하면 제외)

    이 전역 인덱스는 동명 정류소를 해결하지 못한다(감사 2-2). 노선 인지형 인덱스
    ``_build_route_name_index``를 우선하고 여기를 폴백으로 사용한다.
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


def _build_route_name_index() -> dict[str, dict[str, list[str]]]:
    """노선별 이름→node_id 인덱스를 만든다(감사 2-2).

    반환: {route_id: {stop_name: [node_id, ...]}}
    노선의 tracked stop_ids(ROUTEID[rid][3])와 STOP_IDS를 교집합해 노선에 속한 정류소만 포함.
    """
    # STOP_IDS는 node_id→name. 역인덱스 먼저 구축: name → [node_id, ...]
    name_to_nodes: dict[str, list[str]] = defaultdict(list)
    for nid, nm in STOP_IDS.items():
        name_to_nodes[nm].append(nid)

    route_idx: dict[str, dict[str, list[str]]] = {}
    for rid, meta in ROUTEID.items():
        stop_ids_for_route: list[str] = meta[3]
        idx: dict[str, list[str]] = defaultdict(list)
        for nid in stop_ids_for_route:
            nm = STOP_IDS.get(nid)
            if nm:
                idx[nm].append(nid)
        route_idx[rid] = dict(idx)
    return route_idx


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
        # 감사 2-2: 노선 인지형 이름→node_id 인덱스. route_id → {name → [node_id, ...]}
        self._route_name_idx = _build_route_name_index()
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

    def _resolve_node(self, present_stop: str, route_id: str) -> str | None:
        """present_stop 이름 → node_id 역매핑(감사 2-2: 노선 인지형 우선).

        1. 노선별 인덱스에서 해당 route_id의 정류소와 교집합 시도.
           - 유일하게 매핑되면 그 node_id 반환.
           - 동명이 여럿이면 오기록보다 누락이 낫다(감사 2-2 결론): warning 로그 후 None 반환.
        2. 노선별 인덱스에 없으면 전역 exact/clean 인덱스로 폴백.

        NOTE(감사 2-2): present_stop이 "현재 정류소"인지 "다음 정류소"인지 불확실.
        API 문서 확인 전에는 1정류소 오프셋 가능성 존재.
        """
        route_idx = self._route_name_idx.get(route_id, {})
        candidates = route_idx.get(present_stop)
        if candidates:
            if len(candidates) == 1:
                return candidates[0]
            else:
                # 같은 노선 내 동명 정류소 — 오기록 방지를 위해 skip(감사 2-2)
                logger.warning(
                    "울산 BIS fallback: route=%s present_stop=%r 노선 내 동명 정류소 %d개 "
                    "— 오기록 방지를 위해 skip (감사 2-2)",
                    route_id, present_stop, len(candidates),
                )
                return None
        # 전역 인덱스 폴백
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
                node_id = self._resolve_node(arr.present_stop, route_id)
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
