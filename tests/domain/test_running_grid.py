"""W5b tests: build_running_grid.

P-11 test case intents:
- test_uniform_rows: 통과 정류장 수가 다른 두 run을 그리드로 만들 때 모든 열이 stops_order 길이.
- test_missing_cell_marker: run이 특정 정류장을 통과하지 않았을 때 셀이 일관된 마커로 채워짐.
"""
from __future__ import annotations

from bushexa.domain.running import VehicleRun, RunningGrid, build_running_grid

# ---------------------------------------------------------------------------
# Test data (independent: hand-constructed, known answer)
# ---------------------------------------------------------------------------

ROUTE_ID = "195000178"

STOPS_ORDER = ["STOP_A", "STOP_B", "STOP_C", "STOP_D"]  # 4 stops

# Run 1: passes all 4 stops
RUN_1 = VehicleRun(
    vehicle_no="A001",
    route_id=ROUTE_ID,
    stops={
        "STOP_A": "08:00",
        "STOP_B": "08:05",
        "STOP_C": "08:10",
        "STOP_D": "08:15",
    },
)

# Run 2: only passes 2 of 4 stops (missing STOP_B and STOP_D)
RUN_2 = VehicleRun(
    vehicle_no="A002",
    route_id=ROUTE_ID,
    stops={
        "STOP_A": "09:00",
        "STOP_C": "09:10",
    },
)


# ---------------------------------------------------------------------------
# AC tests (spec P-11)
# ---------------------------------------------------------------------------

def test_uniform_rows():
    """P-11: 통과 정류장 수가 다른 두 run을 그리드로 만들 때 모든 열이 stops_order 길이.

    F05 "key-value 길이 불일치" 결함 회귀:
    Old: pd.DataFrame would fail if columns had different lengths.
    Fix: build_running_grid pads missing stops with marker.

    Fixture:
      STOPS_ORDER = 4 stops
      Run1 passes all 4 → 4 entries
      Run2 passes only 2 → should be padded to 4 with marker

    Expected: all runs in grid have exactly 4 stop entries.
    """
    grid = build_running_grid([RUN_1, RUN_2], STOPS_ORDER)

    assert isinstance(grid, RunningGrid)
    assert len(grid.runs) == 2, "Grid should have 2 runs"

    for i, run_row in enumerate(grid.runs):
        assert len(run_row) == len(STOPS_ORDER), (
            f"Run {i} has {len(run_row)} entries, expected {len(STOPS_ORDER)} "
            f"(F05 길이 불일치 regression)"
        )


def test_missing_cell_marker():
    """P-11: run이 특정 정류장을 통과하지 않았을 때 셀이 일관된 마커로 채워짐.

    Fixture: Run 2 is missing STOP_B and STOP_D.
    Expected: grid.runs[1]["STOP_B"] == "レ" (or configured marker).
    """
    marker = "レ"
    grid = build_running_grid([RUN_1, RUN_2], STOPS_ORDER, missing_marker=marker)

    run2 = grid.runs[1]
    # Run 2 doesn't pass STOP_B → should be filled with marker
    assert run2["STOP_B"] == marker, (
        f"Missing stop STOP_B should be filled with marker {marker!r}, "
        f"got {run2['STOP_B']!r}"
    )
    assert run2["STOP_D"] == marker, (
        f"Missing stop STOP_D should be filled with marker {marker!r}, "
        f"got {run2['STOP_D']!r}"
    )
    # Run 2's present stops should retain their time values
    assert run2["STOP_A"] == "09:00", "STOP_A should have actual time"
    assert run2["STOP_C"] == "09:10", "STOP_C should have actual time"
