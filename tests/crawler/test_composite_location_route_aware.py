"""T3: composite_location 노선 인지형 이름→node_id 역인덱스 검증 (감사 2-2).

기대값은 ROUTEID/STOP_IDS에서 직접 도출한다(E-13). 네트워크 사용 없음.

- T3-a: 동명 정류소에서 노선 인지형 인덱스가 올바른 node_id를 선택하는지
- T3-b: 노선 인지형 인덱스에서 해소 불가(노선 내 동명 2개)이면 warning + None 반환인지
- T3-c: 노선 인지형 인덱스에 없는 이름은 전역 인덱스로 폴백하는지
- T3-d: fallback 경로(TAGO 실패)에서 노선 인지형 인덱스가 사용되는지
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from bushexa.api_clients.composite_location import CompositeLocationClient
from bushexa.api_clients.errors import TagoError

# 감사 2-2 검증용 구체 상수(ROUTEID/STOP_IDS에서 도출)
# route 195000221(753 UNIST 방향): 공업탑 → 193040402
# 전역 인덱스(setdefault)는 공업탑 → 193040401 (먼저 본 것)
ROUTE_753_TO_UNIST = "195000221"
GONGEOPTAP_GLOBAL = "193040401"   # 전역 인덱스의 잘못된 매핑
GONGEOPTAP_CORRECT = "193040402"  # 노선 195000221에 속한 올바른 node_id

# route 195000178(713 명촌 방향): 태화강국가정원 동강병원 → 192021209 (유일)
ROUTE_713_TO_MYEONGCHON = "195000178"
TAEHWA_CORRECT = "192021209"      # 노선에 속한 유일한 node_id


@dataclass
class _FakeArrival:
    """울산 BIS 도착정보 대역 — composite_location이 접근하는 필드만 포함."""
    route_id: str
    present_stop: str
    vehicle_no: str


class _FakeTago:
    """TAGO가 항상 TagoError를 던지는 대역 — fallback 경로 강제."""
    def fetch_bus_locations(self, route_id, *, page=1, rows=70):
        raise TagoError("FORCED", "테스트용 강제 실패")


class _FakeUlsan:
    """고정 도착정보를 반환하는 울산 BIS 대역."""
    def __init__(self, arrivals_by_stop: dict):
        self._arrivals = arrivals_by_stop

    def fetch_arrivals(self, stop_id: str) -> list:
        return self._arrivals.get(stop_id, [])


def _make_client(arrivals_by_stop: dict) -> CompositeLocationClient:
    return CompositeLocationClient(
        _FakeTago(), _FakeUlsan(arrivals_by_stop), cache_ttl=0.0
    )


# ---------------------------------------------------------------------------
# T3-a: 동명 정류소에서 노선 인지형 인덱스가 올바른 node_id를 선택
# ---------------------------------------------------------------------------

def test_T3a_route_aware_picks_correct_node():
    """T3-a: 전역 인덱스는 공업탑→193040401로 오매핑하지만, 노선 195000221의 인지형
    인덱스는 공업탑→193040402로 올바르게 매핑하는지(감사 2-2).

    route 195000221의 공업탑 stop_id는 193040402 (ROUTEID[route][3] 기반).
    전역 인덱스는 193040401 (setdefault — 먼저 본 것 우선).
    노선 인지형 인덱스가 동작하면 193040402를 반환해야 한다.
    """
    # 193040402(공업탑, route 195000221 소속)에 차량이 있는 상황을 시뮬레이션
    arrivals = {
        GONGEOPTAP_CORRECT: [
            _FakeArrival(
                route_id=ROUTE_753_TO_UNIST,
                present_stop="공업탑",    # 이름으로만 전달 → 역인덱스로 node_id 결정
                vehicle_no="veh-X",
            )
        ]
    }
    client = _make_client(arrivals)
    result = client.fetch_bus_locations(ROUTE_753_TO_UNIST)

    assert len(result.items) == 1
    # 노선 인지형 인덱스가 동작하면 올바른 193040402가 선택되어야 한다.
    assert result.items[0].node_id == GONGEOPTAP_CORRECT, (
        f"노선 인지형 인덱스 실패: 전역={GONGEOPTAP_GLOBAL} vs 노선={GONGEOPTAP_CORRECT}. "
        f"실제={result.items[0].node_id} (감사 2-2)"
    )


# ---------------------------------------------------------------------------
# T3-b: 노선 내 동명 정류소(미래 시나리오) → warning + skip
# ---------------------------------------------------------------------------

def test_T3b_intra_route_duplicate_skipped(caplog):
    """T3-b: 노선 인지형 인덱스에서 동명 정류소가 2개 이상이면 warning 로그 후 None 반환해
    해당 차량 위치를 기록하지 않는지(감사 2-2: 오기록보다 누락이 낫다).

    실제 데이터에는 노선 내 동명이 없으므로, 인덱스를 직접 패치해서 시나리오를 만든다.
    """
    client = _make_client({})
    # 노선 내 동명을 강제 주입: route_name_idx에 두 개 이상 node_id를 가진 name 추가
    client._route_name_idx["TEST_ROUTE"] = {"공업탑": ["ID_A", "ID_B"]}

    with caplog.at_level(logging.WARNING, logger="bushexa.api_clients.composite_location"):
        result = client._resolve_node("공업탑", "TEST_ROUTE")

    assert result is None, "노선 내 동명 정류소에서 None이 아닌 값 반환 — 오기록 위험"
    assert "동명 정류소" in caplog.text, "경고 로그가 없음"


# ---------------------------------------------------------------------------
# T3-c: 노선 인지형 인덱스에 없는 이름은 전역 인덱스로 폴백
# ---------------------------------------------------------------------------

def test_T3c_fallback_to_global_when_not_in_route():
    """T3-c: 노선 인지형 인덱스에 없는 정류소 이름은 전역 인덱스로 폴백하는지.

    전역 인덱스에만 있는 유일 이름을 resolve_node에 넣으면 전역 node_id를 반환해야 한다.
    """
    client = _make_client({})
    # "명촌 (종점)"은 999000148로 유일 매핑 — 노선 인덱스에는 없는 이름(종점 표기 포함)
    # 전역 인덱스(exact)에 존재하는 이름 사용
    from bushexa.data.constants import STOP_IDS
    # 유일한 이름 찾기: 노선별 인덱스에 없고 전역에만 있는 이름
    from collections import Counter
    name_counts = Counter(STOP_IDS.values())
    unique_name, unique_id = next(
        (nm, nid) for nid, nm in STOP_IDS.items() if name_counts[nm] == 1
    )

    result = client._resolve_node(unique_name, "NON_EXISTENT_ROUTE")
    assert result == unique_id, f"전역 인덱스 폴백 실패: name={unique_name!r} expected={unique_id!r}"


# ---------------------------------------------------------------------------
# T3-d: TAGO 실패 시 fallback 전체 흐름이 노선 인지형 인덱스를 사용
# ---------------------------------------------------------------------------

def test_T3d_ulsan_fallback_uses_route_aware_index():
    """T3-d: TAGO 실패 후 울산 BIS fallback에서 노선 인지형 인덱스가 사용되는지
    end-to-end로 검증한다(감사 2-2).

    route 195000178(713 명촌 방향): 태화강국가정원 동강병원(192021209)이 유일하게 매핑.
    """
    from bushexa.data.constants import ROUTEID
    route_stops = ROUTEID[ROUTE_713_TO_MYEONGCHON][3]
    # TAEHWA_CORRECT(192021209) stop에 차량이 있는 상황
    arrivals = {
        TAEHWA_CORRECT: [
            _FakeArrival(
                route_id=ROUTE_713_TO_MYEONGCHON,
                present_stop="태화강국가정원 동강병원",
                vehicle_no="veh-713",
            )
        ]
    }
    client = _make_client(arrivals)
    result = client.fetch_bus_locations(ROUTE_713_TO_MYEONGCHON)

    assert len(result.items) == 1
    assert result.items[0].node_id == TAEHWA_CORRECT
    assert result.items[0].vehicle_no == "veh-713"
