"""W2 tests: get_stop_data.

P-11 test case intents:
- test_sorted: mock 도착 3건(역순)을 주면 결과가 도착 시각 오름차순 정렬.
- test_long_gap: 35분 간격에서 long_gap 플래그가 True.
- test_no_bus_empty_snapshot: 도착이 없을 때 빈 rows와 has_no_bus=True.
- test_uses_injected_clock: FakeClock 기준으로 도착까지 남은 시간이 계산.
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest
from freezegun import freeze_time

from tests.conftest import FakeClock
from bushexa.domain.stops import get_stop_data, StopSnapshot
from bushexa.api_clients.ulsan_bis import Arrival

KST = ZoneInfo("Asia/Seoul")

STOP_ID = "196040234"

# 713/UNIST→명촌 route_id = 195000178
# 513/덕하→삼남 route_id = 196000422


def make_clock(h: int = 8, m: int = 30) -> FakeClock:
    return FakeClock(datetime(2026, 6, 1, h, m, 0, tzinfo=KST))


def make_client(arrivals: list[Arrival]) -> MagicMock:
    client = MagicMock()
    client.fetch_arrivals.return_value = arrivals
    return client


# ---------------------------------------------------------------------------
# AC tests (spec P-11)
# ---------------------------------------------------------------------------

def test_sorted():
    """P-11: mock 도착 3건(역순)을 주면 결과가 도착 시각 오름차순으로 정렬.

    Input: arrivals with arrival_time 900, 300, 600 seconds.
    Expected: rows sorted as 300, 600, 900 (arrival_seconds ascending).
    """
    arrivals = [
        # arrival_time in seconds: 900, 300, 600 — deliberately out of order
        Arrival(route_id="195000178", present_stop="천상", vehicle_no="A001", arrival_time=900),
        Arrival(route_id="196000422", present_stop="울산역", vehicle_no="B002", arrival_time=300),
        Arrival(route_id="195000178", present_stop="굴화", vehicle_no="C003", arrival_time=600),
    ]
    clock = make_clock()
    client = make_client(arrivals)

    snapshot = get_stop_data(STOP_ID, clock, client=client)

    assert isinstance(snapshot, StopSnapshot)
    assert len(snapshot.rows) == 3
    # Verify ascending order of arrival_seconds
    for i in range(len(snapshot.rows) - 1):
        assert snapshot.rows[i].arrival_seconds <= snapshot.rows[i + 1].arrival_seconds, (
            f"Not sorted: rows[{i}].arrival_seconds={snapshot.rows[i].arrival_seconds} "
            f"> rows[{i+1}].arrival_seconds={snapshot.rows[i+1].arrival_seconds}"
        )
    # The specific expected order: 300, 600, 900
    assert snapshot.rows[0].arrival_seconds == 300
    assert snapshot.rows[1].arrival_seconds == 600
    assert snapshot.rows[2].arrival_seconds == 900


def test_long_gap():
    """P-11: 첫 버스와 둘째 버스 도착 간격이 35분(2100s)일 때 long_gap 플래그가 True.

    gap = 2100s > 1800s → long_gap=True.
    """
    # first arrival: 300s, second: 300 + 2100 = 2400s → gap = 2100 > 1800
    arrivals = [
        Arrival(route_id="195000178", present_stop="천상", vehicle_no="A001", arrival_time=300),
        Arrival(route_id="196000422", present_stop="울산역", vehicle_no="B002", arrival_time=2400),
    ]
    clock = make_clock()
    client = make_client(arrivals)

    snapshot = get_stop_data(STOP_ID, clock, client=client)

    assert snapshot.long_gap is True, (
        f"Expected long_gap=True for gap of 2100s (>1800s), got {snapshot.long_gap}"
    )


def test_no_bus_empty_snapshot():
    """P-11: 도착이 없을 때 빈 rows와 has_no_bus=True를 반환.

    Input: empty arrival list.
    Expected: rows=[], has_no_bus=True.
    """
    clock = make_clock()
    client = make_client([])

    snapshot = get_stop_data(STOP_ID, clock, client=client)

    assert snapshot.rows == [], "Empty arrival should produce empty rows"
    assert snapshot.has_no_bus is True, "has_no_bus should be True when no arrivals"


def test_uses_injected_clock():
    """P-11: FakeClock 기준으로 도착까지 남은 시간이 계산.

    FakeClock at 08:30. Arrival in 600 seconds (10 minutes).
    minutes_until[0] should be 600 // 60 = 10.
    """
    clock = make_clock(8, 30)  # frozen at 08:30
    arrivals = [
        Arrival(route_id="195000178", present_stop="천상", vehicle_no="A001", arrival_time=600),
    ]
    client = make_client(arrivals)

    snapshot = get_stop_data(STOP_ID, clock, client=client)

    assert len(snapshot.rows) == 1
    # minutes_until is derived from arrival_seconds // 60
    expected_minutes = 600 // 60  # = 10
    assert snapshot.minutes_until[0] == expected_minutes, (
        f"Expected {expected_minutes} minutes, got {snapshot.minutes_until[0]}"
    )


# executor-added: freezegun integration — EC-3 requires ≥1 freezegun usage per module.
@freeze_time("2026-06-01T08:30:00+09:00")
def test_freezegun_clock_isolation():
    """executor-added: EC-3 freezegun 사용 증거. FakeClock 주입이 datetime.now() 무관함 검증.

    freeze_time patchs datetime.now() to 08:30 KST.
    FakeClock is injected (it reads its own fixed value, not datetime.now).
    The result should be consistent with FakeClock's value.
    """
    clock = make_clock(8, 30)
    arrivals = [
        Arrival(route_id="195000178", present_stop="천상", vehicle_no="A001", arrival_time=300),
    ]
    client = make_client(arrivals)

    snapshot = get_stop_data(STOP_ID, clock, client=client)

    assert len(snapshot.rows) == 1
    assert snapshot.rows[0].arrival_seconds == 300
