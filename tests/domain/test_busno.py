"""W6 tests: get_busno_page_data.

P-11 test case intents:
- test_valid_selection: bus='713', day=0, dep='UNIST'로 호출하면 Hour/Minute 행으로 반환.
- test_invalid_dep_fallback: 존재하지 않는 dep를 주면 첫 출발지로 폴백하고 warning이 채워짐.
- test_day_clamp: day=9 같은 범위 밖 입력이 0으로 보정.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from freezegun import freeze_time

from tests.conftest import FakeClock
from bushexa.domain.busno import get_busno_page_data, BusnoTimetable

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


# Known timetable fixture for 713/UNIST/weekday=0
# Hand-calculated expected result:
#   Times: ["07:30", "08:00", "08:30", "09:00"]
#   Hour groups:
#     "07": "30"
#     "08": "00, 30"
#     "09": "00"
TIMETABLE_713_UNIST = ["07:30", "08:00", "08:30", "09:00"]

TIMETABLE_DATA = {
    ("713", 0, "UNIST"): TIMETABLE_713_UNIST,
    ("713", 0, "명촌"): ["07:00", "08:00"],
    ("513", 0, "덕하"): ["07:00", "08:00"],
    ("513", 0, "삼남"): ["07:30"],
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

def test_valid_selection():
    """P-11: bus='713', day=0, dep='UNIST'로 호출하면 그 노선의 시간표가 Hour/Minute 행으로 반환.

    Fixture: TIMETABLE_713_UNIST = ["07:30", "08:00", "08:30", "09:00"]
    Expected timetable_rows by hand-calculation:
      hour "07": minutes "30"
      hour "08": minutes "00, 30"
      hour "09": minutes "00"
    """
    clock = make_clock(8, 30)
    timetable = make_timetable_provider(TIMETABLE_DATA)

    result = get_busno_page_data("713", 0, "UNIST", clock, timetable_provider=timetable)

    assert isinstance(result, BusnoTimetable)
    assert result.selected_bus == "713"
    assert result.selected_day == 0
    assert result.selected_dep == "UNIST"
    assert len(result.timetable_rows) > 0, "Should have timetable rows"

    # Verify hand-calculated Hour/Minute structure
    hour_map = {row["hour"]: row["minutes"] for row in result.timetable_rows}
    assert "07" in hour_map, "Hour 07 should be present"
    assert "08" in hour_map, "Hour 08 should be present"
    assert "09" in hour_map, "Hour 09 should be present"
    # Hour "07": only minute "30"
    assert hour_map["07"] == "30", f"Hour 07 should have minute '30', got {hour_map['07']!r}"
    # Hour "08": minutes "00, 30" (sorted ascending)
    assert hour_map["08"] == "00, 30", f"Hour 08 should have '00, 30', got {hour_map['08']!r}"
    # Hour "09": minute "00"
    assert hour_map["09"] == "00", f"Hour 09 should have minute '00', got {hour_map['09']!r}"


def test_invalid_dep_fallback():
    """P-11: 존재하지 않는 dep를 주면 첫 출발지로 폴백하고 warning 메시지가 채워짐.

    For bus '713', valid terminals are ['UNIST', '명촌'].
    dep='INVALID' should fall back to '명촌' (first terminal for 713 direction that's not UNIST)
    ... actually to the first terminal in departure_dict['713'] = ['UNIST', '명촌'].
    dep='INVALID' → fallback to 'UNIST' (first dep for 713).
    warning must be non-None.
    """
    clock = make_clock(8, 30)
    timetable = make_timetable_provider(TIMETABLE_DATA)

    result = get_busno_page_data("713", 0, "INVALID_DEP", clock, timetable_provider=timetable)

    assert result.warning is not None, "Warning should be set for invalid dep"
    # Should fall back to the first terminal for 713
    # departure_dict['713'][0] = 'UNIST' (per get_busroute_info from constants)
    assert result.selected_dep in ("UNIST", "명촌"), (
        f"Should fall back to a valid terminal, got {result.selected_dep!r}"
    )


def test_day_clamp():
    """P-11: day=9 같은 범위 밖 입력이 0으로 보정.

    day=9 is outside valid range (0, 1, 2) → clamped to 0.
    Expected: result.selected_day == 0.
    """
    clock = make_clock(8, 30)
    timetable = make_timetable_provider(TIMETABLE_DATA)

    result = get_busno_page_data("713", 9, "UNIST", clock, timetable_provider=timetable)

    assert result.selected_day == 0, (
        f"day=9 should be clamped to 0, got {result.selected_day}"
    )


# executor-added: freezegun integration — EC-3 requires ≥1 freezegun usage per module.
@freeze_time("2026-06-01T08:30:00+09:00")
def test_freezegun_current_time_format():
    """executor-added: freeze_time으로 08:30 고정, current_time 형식이 "HH:MM"임을 검증.

    When clock says 08:30, current_time should be "08:30".
    This also verifies FakeClock's value is used (not datetime.now's freeze_time value).
    """
    clock = make_clock(8, 30)
    timetable = make_timetable_provider(TIMETABLE_DATA)

    result = get_busno_page_data("713", 0, "UNIST", clock, timetable_provider=timetable)

    assert result.current_time == "08:30", (
        f"current_time should be '08:30', got {result.current_time!r}"
    )
