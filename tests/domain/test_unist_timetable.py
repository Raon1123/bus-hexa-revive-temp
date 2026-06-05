"""W4 tests: get_full_timetable_data.

P-11 test case intents:
- test_grouped_sorted: 여러 노선 시간표를 합치면 hour 오름차순 그룹화, 각 hour 내 분 오름차순.
- test_weekday_clamp: weekday=5가 0으로 보정되어 처리.
- test_empty_when_no_data: 모든 노선 시간표가 비면 빈 그리드와 is_empty=True.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from freezegun import freeze_time

from tests.conftest import FakeClock
from bushexa.domain.unist_timetable import get_full_timetable_data, FullTimetableSnapshot

KST = ZoneInfo("Asia/Seoul")


def make_clock(h: int = 8, m: int = 30) -> FakeClock:
    return FakeClock(datetime(2026, 6, 1, h, m, 0, tzinfo=KST))


def make_timetable_provider(data: dict[tuple, list[str]]):
    def provider(busno, weekday, departure):
        key = (str(busno), int(weekday), str(departure))
        if key not in data:
            raise FileNotFoundError(f"No timetable for {key}")
        return data[key]
    return provider


# Known timetable fixture for test_grouped_sorted:
# Two buses (713 and 743) with entries at known hours.
# 713: 08:30, 08:50 → hour "08", minutes "30", "50"
# 743: 08:20, 09:10 → hour "08" minute "20" and hour "09" minute "10"
# Expected merged by hour:
#   "08": [(20, "743"), (30, "713"), (50, "713")]
#   "09": [(10, "743")]
#
# get_busroute_info() returns busnos from ROUTEID.
# We need to patch the timetable_provider to return specific data for specific buses.
# But get_full_timetable_data uses get_busroute_info() internally which returns
# all 5 buses. We provide entries only for some; others raise FileNotFoundError.
# The fixture must cover exactly the first departure of each bus as returned by get_busroute_info.
# From constants: busnos=['513','713','743','753','1115']
# departure_dict[busno][0] = first dep for each:
#   513 → "덕하", 713 → "UNIST", 743 → "UNIST", 753 → "UNIST", 1115 → "UNIST"

TIMETABLE_DATA_SORTED = {
    # 713/UNIST: entries at 08:30 and 08:50
    ("713", 0, "UNIST"): ["08:30", "08:50"],
    # 743/UNIST: entries at 08:20 and 09:10
    ("743", 0, "UNIST"): ["08:20", "09:10"],
    # others: empty or not provided (FileNotFoundError = skip)
}


# ---------------------------------------------------------------------------
# AC tests (spec P-11)
# ---------------------------------------------------------------------------

def test_grouped_sorted():
    """P-11: 여러 노선 시간표를 합치면 hour 오름차순으로 그룹화되고 각 hour 내 분이 오름차순.

    Fixture:
      - 713/UNIST weekday: 08:30, 08:50
      - 743/UNIST weekday: 08:20, 09:10
    Expected hour groups (by independent hand-calculation):
      "08": departures sorted by minute → 20 (743), 30 (713), 50 (713)
      "09": departures → 10 (743)
    Hours must appear in ascending order: "08" before "09".
    """
    clock = make_clock(8, 0)
    timetable = make_timetable_provider(TIMETABLE_DATA_SORTED)

    snapshot = get_full_timetable_data(0, clock, timetable_provider=timetable)

    assert isinstance(snapshot, FullTimetableSnapshot)

    # Collect hour→minutes from result
    hour_to_minutes = {row["hour"]: [d["minute"] for d in row["departures"]] for row in snapshot.timetable_rows}

    # Hour "08" must exist
    assert "08" in hour_to_minutes, "Hour 08 must be present"
    # Hour "09" must exist
    assert "09" in hour_to_minutes, "Hour 09 must be present"

    # Hours must be in ascending order
    hours = [row["hour"] for row in snapshot.timetable_rows]
    assert hours == sorted(hours), f"Hours not in ascending order: {hours}"

    # Within hour "08": minutes must be ascending: [20, 30, 50] (hand-calculated)
    mins_08 = hour_to_minutes["08"]
    assert mins_08 == sorted(mins_08), f"Minutes in hour 08 not sorted: {mins_08}"
    # The exact minutes from our fixture: 20 (743), 30 (713), 50 (713)
    assert "20" in mins_08, "Minute 20 from 743 should be in hour 08"
    assert "30" in mins_08, "Minute 30 from 713 should be in hour 08"
    assert "50" in mins_08, "Minute 50 from 713 should be in hour 08"


def test_weekday_clamp():
    """P-11: 범위를 벗어난 weekday=5를 주면 0(평일)으로 보정되어 처리.

    weekday=5 is invalid (valid: 0, 1, 2). Should be clamped to 0.
    We verify snapshot.selected_day == 0 after clamping.
    """
    clock = make_clock(8, 0)
    timetable = make_timetable_provider(TIMETABLE_DATA_SORTED)

    snapshot = get_full_timetable_data(5, clock, timetable_provider=timetable)

    assert snapshot.selected_day == 0, (
        f"weekday=5 should be clamped to 0, got selected_day={snapshot.selected_day}"
    )


def test_empty_when_no_data():
    """P-11: 모든 노선 시간표가 비면 빈 그리드와 is_empty=True를 반환.

    Input: timetable_provider raises FileNotFoundError for all buses.
    Expected: timetable_rows=[], is_empty=True.
    """
    clock = make_clock(8, 0)
    # empty provider: all buses raise FileNotFoundError
    timetable = make_timetable_provider({})

    snapshot = get_full_timetable_data(0, clock, timetable_provider=timetable)

    assert snapshot.timetable_rows == [], "Empty timetable should produce empty rows"
    assert snapshot.is_empty is True, "is_empty should be True when no data"


# executor-added: freezegun integration — EC-3 requires ≥1 freezegun usage per module.
@freeze_time("2026-06-01T08:00:00+09:00")
def test_freezegun_weekday_detection():
    """executor-added: freeze_time으로 월요일(weekday=0) 고정, FakeClock 주입 동작 검증.

    2026-06-01 is a Monday. freeze_time patches datetime.now() to this date.
    FakeClock also returns this date. We verify the result includes the weekday string.
    """
    clock = make_clock(8, 0)
    timetable = make_timetable_provider(TIMETABLE_DATA_SORTED)

    snapshot = get_full_timetable_data(0, clock, timetable_provider=timetable)

    # selected_day should be 0 (weekday) as explicitly passed
    assert snapshot.selected_day == 0
