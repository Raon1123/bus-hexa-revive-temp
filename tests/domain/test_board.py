"""W1a tests: get_board_data.

P-11 test case intents:
- test_rows_sorted: 라이브 2건·시간표 3건을 합성하면 결과 rows가 도착 시각 오름차순.
- test_uses_injected_clock: FakeClock(08:30)을 주입하면 그 시각 이전 시간표 항목은 제외.
- test_live_overrides_timetable: 같은 버스에 라이브 도착이 있으면 source="live"로 표시.
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest
from freezegun import freeze_time

from tests.conftest import FakeClock
from bushexa.domain.board import get_board_data, BoardSnapshot, BoardRow
from bushexa.api_clients.ulsan_bis import Arrival

KST = ZoneInfo("Asia/Seoul")

# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

STOP_ID = "196040234"


def make_clock(h: int, m: int) -> FakeClock:
    return FakeClock(datetime(2026, 6, 1, h, m, 0, tzinfo=KST))


def make_client(arrivals: list[Arrival]) -> MagicMock:
    client = MagicMock()
    client.fetch_arrivals.return_value = arrivals
    return client


def make_timetable_provider(data: dict[tuple, list[str]]):
    """Returns a timetable_provider callable backed by a dict keyed by (busno, weekday, dep)."""
    def provider(busno, weekday, departure):
        key = (str(busno), int(weekday), str(departure))
        if key not in data:
            raise FileNotFoundError(f"No timetable for {key}")
        return data[key]
    return provider


# Known test data (independent of implementation):
# FakeClock is 2026-06-01 08:30 KST = weekday=0 (Monday)
# route_id 195000178 = ("713", "명촌 (시내) 방면", "UNIST", [...])
# route_id 196000421 = ("513", "삼남 (울산역) 방면", "덕하", [...])

# Timetable: 3 future entries for 713/UNIST on weekday
TIMETABLE_DATA = {
    ("713", 0, "UNIST"): ["08:40", "09:00", "09:30"],   # all after 08:30
    ("513", 0, "덕하"): ["08:20", "09:10"],             # 08:20 is past, 09:10 is future
    ("713", 0, "명촌"): ["08:00", "08:50"],
    ("513", 0, "삼남"): ["09:00"],
    ("743", 0, "UNIST"): [],
    ("753", 0, "UNIST"): [],
    ("1115", 0, "UNIST"): [],
    ("743", 0, "명촌"): [],
    ("753", 0, "명촌"): [],
    ("1115", 0, "꽃바위"): [],
}


# ---------------------------------------------------------------------------
# AC tests (spec P-11)
# ---------------------------------------------------------------------------

def test_rows_sorted():
    """P-11: 라이브 2건·시간표 3건을 합성하면 결과 rows가 도착 시각 오름차순으로 정렬.

    Fixture:
      - live arrivals: route_id=195000178 (713/UNIST) arriving in 900s (15min),
                       route_id=196000421 (513/덕하) arriving in 300s (5min)
      - timetable: 713/UNIST: 08:40, 09:00, 09:30 → 10, 30, 60 min ahead
                   513/덕하: 09:10 → 40 min ahead (08:20 is past)
    Expected: rows sorted by arrival_minutes ascending.
    """
    clock = make_clock(8, 30)  # 08:30
    # Live: 713 arrives in 900s (15min), 513 arrives in 300s (5min)
    arrivals = [
        Arrival(route_id="195000178", present_stop="천상", vehicle_no="A001", arrival_time=900),
        Arrival(route_id="196000421", present_stop="굴화", vehicle_no="B002", arrival_time=300),
    ]
    client = make_client(arrivals)

    snapshot = get_board_data(STOP_ID, clock, client=client, timetable_provider=make_timetable_provider(TIMETABLE_DATA))

    assert isinstance(snapshot, BoardSnapshot)
    assert len(snapshot.rows) > 1
    # Verify ascending order
    for i in range(len(snapshot.rows) - 1):
        assert snapshot.rows[i].arrival_minutes <= snapshot.rows[i + 1].arrival_minutes, (
            f"Not sorted: rows[{i}].arrival_minutes={snapshot.rows[i].arrival_minutes} "
            f"> rows[{i+1}].arrival_minutes={snapshot.rows[i+1].arrival_minutes}"
        )


def test_uses_injected_clock():
    """P-11: FakeClock(08:30)을 주입하면 08:30 이전 시간표 항목은 제외되고 이후만 남음.

    Specifically, timetable 513/덕하 has "08:20" (before 08:30) and "09:10" (after).
    Only "09:10" should appear in timetable rows for 513/덕하.
    """
    clock = make_clock(8, 30)
    client = make_client([])  # no live data

    snapshot = get_board_data(STOP_ID, clock, client=client, timetable_provider=make_timetable_provider(TIMETABLE_DATA))

    # 08:20 was before 08:30 so should NOT appear
    all_times = [r.arrival_time for r in snapshot.rows]
    assert "08:20" not in all_times, "Past timetable entry 08:20 should be excluded at 08:30"
    # 08:40 is future and should appear
    assert "08:40" in all_times, "Future timetable entry 08:40 should be included at 08:30"


def test_live_overrides_timetable():
    """P-11: 같은 버스에 라이브 도착이 있으면 시간표 추정 대신 라이브 값을 source='live'로 표시.

    F01 §6.1: "동일 (bus_number, terminal) 조합의 시간표 행을 제거하고 live 행으로 대체."

    Fixture:
      - route_id 195000178 = 713/명촌(시내)방면/departure=UNIST
      - Live: 713/명촌방면 arriving in 600s (10min) → 1 live row
      - Timetable: 713/UNIST has 08:40, 09:00, 09:30 future entries
    Expected after dedup by (bus_number, terminal="명촌 (시내) 방면"):
      - 713/명촌방면 timetable entries are REMOVED (replaced by live)
      - Only source="live" row for 713/명촌방면 remains
      - No duplicate 713/명촌방면 entries
    """
    clock = make_clock(8, 30)
    arrivals = [
        Arrival(route_id="195000178", present_stop="천상", vehicle_no="A001", arrival_time=600),
    ]
    client = make_client(arrivals)

    snapshot = get_board_data(STOP_ID, clock, client=client, timetable_provider=make_timetable_provider(TIMETABLE_DATA))

    # There must be at least one live row
    live_rows = [r for r in snapshot.rows if r.source == "live"]
    assert len(live_rows) >= 1, "Expected at least one live row"

    # The live 713 row
    live_713 = [r for r in live_rows if r.bus_number == "713"]
    assert len(live_713) >= 1, "Live 713 entry should have source='live'"
    assert live_713[0].source == "live"

    # OVERRIDE check: timetable 713/명촌방면 entries should be REMOVED (deduped)
    # F01 §6.1 spec: same (bus_number, terminal) timetable rows are replaced by live rows
    # route 195000178 has terminal="명촌 (시내) 방면"
    timetable_713_명촌_rows = [
        r for r in snapshot.rows
        if r.bus_number == "713" and r.source == "timetable" and r.terminal == "명촌 (시내) 방면"
    ]
    assert len(timetable_713_명촌_rows) == 0, (
        f"Timetable 713/명촌방면 rows should be removed when live data present, "
        f"got {len(timetable_713_명촌_rows)} (F01 §6.1 override not working)"
    )


def test_only_unist_departures_shown():
    """UNIST '출발' 게시판: UNIST를 종점으로 갖는 노선(713/743/753/1115)은 UNIST에서
    출발하는 방향만, UNIST로 들어오는 방향("UNIST 방면")은 제외. UNIST를 경유만 하는
    513은 양방향 모두 표시(레거시 departure_board.py 동작과 일치).
    """
    clock = make_clock(8, 30)
    client = make_client([])  # 시간표만

    snapshot = get_board_data(STOP_ID, clock, client=client, timetable_provider=make_timetable_provider(TIMETABLE_DATA))
    terminals = {r.terminal for r in snapshot.rows}

    # UNIST로 들어오는 방향은 절대 나오면 안 됨
    assert "UNIST 방면" not in terminals, "UNIST 도착(=UNIST 방면) 방향은 출발 게시판에서 제외돼야 함"
    # 713/UNIST(=명촌행) 출발편은 표시 (TIMETABLE_DATA에 미래편 존재)
    assert "명촌 (시내) 방면" in terminals, "UNIST에서 출발하는 713/명촌행은 표시돼야 함"
    # 513은 UNIST를 경유 → 양방향 모두 허용 (미래편이 있는 09:10 덕하행이 존재)
    assert "덕하 (시내) 방면" in terminals, "UNIST 경유 노선 513은 양방향 표시돼야 함"


def test_unist_bound_live_arrival_excluded():
    """라이브 경로에서도 UNIST로 '들어오는' 차량(195000177 = 713/UNIST 방면)은 제외된다.

    조회 정류소에 UNIST-bound 차량이 섞여 들어와도 출발 게시판에는 나타나면 안 된다.
    """
    clock = make_clock(8, 30)
    arrivals = [
        # 713 'UNIST 방면' (명촌→UNIST, departure=명촌) — 출발 게시판에서 제외 대상
        Arrival(route_id="195000177", present_stop="명촌", vehicle_no="X1", arrival_time=300),
    ]
    client = make_client(arrivals)

    snapshot = get_board_data(STOP_ID, clock, client=client, timetable_provider=make_timetable_provider(TIMETABLE_DATA))
    terminals = {r.terminal for r in snapshot.rows}
    assert "UNIST 방면" not in terminals, "라이브 UNIST 방면(도착) 차량은 출발 게시판에서 제외돼야 함"


# executor-added: freezegun integration — EC-3 requires ≥1 freezegun usage per module.
# Uses @freeze_time to freeze the system clock AND injects FakeClock at same time,
# confirming that domain code reads only from injected clock (not datetime.now()).
@freeze_time("2026-06-01T08:30:00+09:00")
def test_clock_injection_not_datetime_now():
    """executor-added: 도메인 코드가 datetime.now()를 직접 호출하지 않고 주입된 clock만 사용함을 검증.

    freeze_time을 08:30으로 걸고 FakeClock을 09:00으로 주입하면,
    domain 함수는 09:00 기준으로 동작해야 함(datetime.now()가 08:30이어도).
    """
    # FakeClock frozen at 09:00 — different from freeze_time's 08:30
    clock_09 = FakeClock(datetime(2026, 6, 1, 9, 0, 0, tzinfo=KST))
    client = make_client([])

    snapshot = get_board_data(STOP_ID, clock_09, client=client, timetable_provider=make_timetable_provider(TIMETABLE_DATA))

    # If code used datetime.now() (08:30), "08:40" would appear.
    # If code uses clock (09:00), "08:40" is past and should NOT appear.
    all_times = [r.arrival_time for r in snapshot.rows]
    assert "08:40" not in all_times, (
        "08:40 should not appear when clock says 09:00 — proves clock injection not datetime.now()"
    )
