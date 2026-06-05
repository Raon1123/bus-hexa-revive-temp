"""W1b tests: merge_live_rows (FIRST/SECOND marking).

P-11 test case intents:
- test_first_second: 도착 시각이 다른 3건 입력에서 가장 이른 것이 FIRST, 두 번째가 SECOND.
- test_edge_counts: 0건이면 빈 리스트, 1건이면 FIRST만.
- test_tie_break_by_busno: 동일 도착 시각 2건에서 버스번호 오름차순으로 FIRST/SECOND.
"""
from __future__ import annotations

from bushexa.domain.board import BoardRow, merge_live_rows


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_row(arrival_time: str, bus_number: str, arrival_minutes: int) -> BoardRow:
    return BoardRow(
        arrival_time=arrival_time,
        bus_number=bus_number,
        present="테스트",
        via_string="",
        source="timetable",
        arrival_minutes=arrival_minutes,
        rank="",
    )


# ---------------------------------------------------------------------------
# AC tests (spec P-11)
# ---------------------------------------------------------------------------

def test_first_second():
    """P-11: 도착 시각이 다른 3건 입력에서 가장 이른 것이 FIRST, 두 번째가 SECOND, 나머지는 무표시.

    Input (by arrival_minutes): 20, 10, 30 → after sort: 10, 20, 30
    Expected: rank=FIRST at 10min, rank=SECOND at 20min, rank='' at 30min.
    """
    rows = [
        make_row("08:50", "713", 20),
        make_row("08:40", "513", 10),
        make_row("09:00", "743", 30),
    ]
    result = merge_live_rows(rows)

    assert len(result) == 3
    # Find the one with arrival_minutes=10 → FIRST
    ranks_by_minutes = {r.arrival_minutes: r.rank for r in result}
    assert ranks_by_minutes[10] == "FIRST"
    assert ranks_by_minutes[20] == "SECOND"
    assert ranks_by_minutes[30] == ""


def test_edge_counts():
    """P-11: 0건이면 빈 리스트, 1건이면 FIRST만 표시되고 SECOND가 없음."""
    # 0건
    result_empty = merge_live_rows([])
    assert result_empty == []

    # 1건
    single = [make_row("09:00", "713", 30)]
    result_single = merge_live_rows(single)
    assert len(result_single) == 1
    assert result_single[0].rank == "FIRST"
    second_count = sum(1 for r in result_single if r.rank == "SECOND")
    assert second_count == 0, "1-row input should have no SECOND"


def test_same_time_shares_first():
    """동시(같은 시각) 출발 버스는 모두 함께 FIRST (사용자 사양: 동시 출발=동시 FIRST).

    Input: 두 버스 모두 08:50. Expected: 둘 다 FIRST, SECOND 없음.
    """
    rows = [
        make_row("08:50", "713", 20),
        make_row("08:50", "513", 20),
    ]
    result = merge_live_rows(rows)

    assert len(result) == 2
    ranks_by_busno = {r.bus_number: r.rank for r in result}
    assert ranks_by_busno["513"] == "FIRST"
    assert ranks_by_busno["713"] == "FIRST", "같은 시각 출발은 둘 다 FIRST여야 함"
    assert all(r.rank != "SECOND" for r in result), "distinct 시각이 1개면 SECOND 없음"


def test_second_group_shares_rank():
    """두 번째로 이른 시각의 버스가 여럿이면 모두 SECOND를 공유한다.

    Input: 08:40(1대), 08:50(2대). Expected: 08:40=FIRST, 08:50 둘 다 SECOND.
    """
    rows = [
        make_row("08:40", "513", 10),
        make_row("08:50", "713", 20),
        make_row("08:50", "743", 20),
    ]
    result = merge_live_rows(rows)
    rank_by_busno = {r.bus_number: r.rank for r in result}
    assert rank_by_busno["513"] == "FIRST"
    assert rank_by_busno["713"] == "SECOND"
    assert rank_by_busno["743"] == "SECOND"
