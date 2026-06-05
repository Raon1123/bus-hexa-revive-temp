"""W1 VehicleTimeline 검증. 기대값은 record 호출 순서에서 직접 도출(E-13).

H2(재시작 false-positive) 회귀의 핵심: warm_from_repo 후 같은 위치 record가 False여야 한다.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from bushexa.crawler.state import JSONFileStore, VehicleTimeline

KST = ZoneInfo("Asia/Seoul")
TS = datetime(2026, 6, 1, 8, 0, 0, tzinfo=KST)


class _FakeRepo:
    """latest_node_per_vehicle만 흉내내는 최소 repo (warm 경로 검증용)."""

    def __init__(self, mapping: dict[tuple[str, str], str]) -> None:
        self._m = dict(mapping)

    def latest_node_per_vehicle(self, *, since):
        return dict(self._m)


def test_first_record_is_change():
    """비어 있는 timeline에 차량 A의 첫 위치를 record하면 '변경됨'(True)으로 처리되는지."""
    tl = VehicleTimeline()
    assert tl.record("195000177", "veh-A", "999000149", TS) is True


def test_same_node_no_change():
    """차량 A가 같은 node에 머물러 연속 record되면 두 번째는 False가 되어 중복 INSERT를 막는지."""
    tl = VehicleTimeline()
    tl.record("195000177", "veh-A", "999000149", TS)
    assert tl.record("195000177", "veh-A", "999000149", TS) is False


def test_different_node_change():
    """차량 A가 다른 node로 이동하면 record가 True를 반환해 통과를 기록 후보로 삼는지."""
    tl = VehicleTimeline()
    tl.record("195000177", "veh-A", "999000149", TS)
    assert tl.record("195000177", "veh-A", "193012314", TS) is True


def test_warm_suppresses():
    """warm_from_repo로 DB의 직전 위치를 적재한 직후, 차량이 그 위치 그대로일 때 record가
    False를 반환해 재시작 false-positive(H2)를 억제하는지 검증한다."""
    tl = VehicleTimeline()
    warmed = tl.warm_from_repo(_FakeRepo({("195000177", "veh-A"): "999000149"}), since=TS)
    assert warmed == 1
    # 재시작 후 첫 poll에서 차량이 워밍된 위치 그대로 → 변경 아님 → INSERT 0건
    assert tl.record("195000177", "veh-A", "999000149", TS) is False


def test_warm_does_not_overwrite_existing():
    """이미 알고 있는(영속 파일에서 온) 키는 warm이 덮지 않아 파일 상태가 우선되는지."""
    tl = VehicleTimeline()
    tl.record("195000177", "veh-A", "193012314", TS)  # 파일/메모리가 더 최신
    warmed = tl.warm_from_repo(_FakeRepo({("195000177", "veh-A"): "999000149"}), since=TS)
    assert warmed == 0
    assert tl.last_node("195000177", "veh-A") == "193012314"


def test_persist_roundtrip(tmp_path):
    """persist 후 새 인스턴스가 같은 store에서 load했을 때 직전 상태가 복원되는지 검증한다."""
    path = tmp_path / "state.json"
    tl = VehicleTimeline(JSONFileStore(path))
    tl.record("195000177", "veh-A", "193012314", TS)
    tl.persist()

    tl2 = VehicleTimeline(JSONFileStore(path))
    assert tl2.last_node("195000177", "veh-A") == "193012314"
    assert tl2.record("195000177", "veh-A", "193012314", TS) is False
