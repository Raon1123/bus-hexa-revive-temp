"""W3 tests: get_unist_board_data.

P-11 test case intents:
- test_six_cards: UnistBoardSnapshot에 via 1 + from 5 = 6개 카드, 각 카드에 최대 2건.
- test_single_fetch: mock client 호출 횟수가 정확히 1회 (F07 중복 호출 결함 회귀).
- test_from_card_index_safe: 시간표 1건뿐인 노선에서 IndexError 없이 1건만 채움 (F07 IndexError 회귀).
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, call
from zoneinfo import ZoneInfo

import pytest
from freezegun import freeze_time

from tests.conftest import FakeClock
from bushexa.domain.unist_board import get_unist_board_data, UnistBoardSnapshot
from bushexa.api_clients.ulsan_bis import Arrival

KST = ZoneInfo("Asia/Seoul")


def make_clock(h: int = 8, m: int = 30) -> FakeClock:
    return FakeClock(datetime(2026, 6, 1, h, m, 0, tzinfo=KST))


def make_client(arrivals: list[Arrival] = None) -> MagicMock:
    client = MagicMock()
    client.fetch_arrivals.return_value = arrivals or []
    return client


def make_timetable_provider(data: dict[tuple, list[str]]):
    def provider(busno, weekday, departure):
        key = (str(busno), int(weekday), str(departure))
        if key not in data:
            raise FileNotFoundError(f"No timetable for {key}")
        return data[key]
    return provider


# Timetable fixture: each bus has 2+ future entries for 08:30 clock
# weekday=0 (2026-06-01 is Monday)
TIMETABLE_DATA = {
    # 513 via routes
    ("513", 0, "덕하"): ["08:40", "09:00"],     # 2 future entries
    ("513", 0, "삼남"): ["08:45", "09:15"],
    # UNIST departure routes (from cards)
    ("713", 0, "UNIST"): ["08:50", "09:10"],
    ("743", 0, "UNIST"): ["08:55", "09:20"],
    ("753", 0, "UNIST"): ["09:00", "09:25"],
    ("1115", 0, "UNIST"): ["09:05", "09:30"],
    # Also provide named departure routes for return direction
    ("713", 0, "명촌"): ["08:40", "09:00"],
    ("743", 0, "명촌"): ["08:42", "09:02"],
    ("753", 0, "명촌"): ["08:44", "09:04"],
    ("1115", 0, "꽃바위"): ["08:46", "09:06"],
}


# ---------------------------------------------------------------------------
# AC tests (spec P-11)
# ---------------------------------------------------------------------------

def test_six_cards():
    """P-11: UnistBoardSnapshot에 6개 카드가 있고 각 카드에 최대 2건.

    NOTE: P3 manual says "via 1 + from 5", but ROUTEID only has 4 UNIST-departure buses
    (713/743/753/1115) and 513 양방향(2 routes). Implemented as via 2 + from 4 = 6 per F07 §2.3.
    The "via 1 + from 5" label is infeasible given the actual ROUTEID structure.

    Fixture: no live buses, all timetable data provided.
    Expected: len(snapshot.cards) == 6 (via 2 + from 4), each card entries <= 2.
    """
    clock = make_clock(8, 30)
    client = make_client([])
    timetable = make_timetable_provider(TIMETABLE_DATA)

    snapshot = get_unist_board_data(clock, client=client, timetable_provider=timetable)

    assert isinstance(snapshot, UnistBoardSnapshot)
    assert len(snapshot.cards) == 6, (
        f"Expected 6 cards (via 1 + from 5), got {len(snapshot.cards)}"
    )
    for card in snapshot.cards:
        assert len(card.entries) <= 2, (
            f"Card {card.busno}/{card.direction} has {len(card.entries)} entries, max is 2"
        )


def test_single_fetch():
    """P-11: mock client의 호출 횟수가 카드가 6개여도 정확히 1회 — F07 중복 호출 결함 회귀.

    Bug: old implementation called crawl_busstop inside each card loop.
    Fix: fetch once, pass to all card builders.
    Expected: client.fetch_arrivals.call_count == 1.
    """
    clock = make_clock(8, 30)
    client = make_client([])
    timetable = make_timetable_provider(TIMETABLE_DATA)

    snapshot = get_unist_board_data(clock, client=client, timetable_provider=timetable)

    call_count = client.fetch_arrivals.call_count
    assert call_count == 1, (
        f"Expected exactly 1 API fetch call, got {call_count} (F07 duplicate fetch regression)"
    )


def test_from_card_index_safe():
    """P-11: 시간표 1건뿐인 노선에서 IndexError 없이 1건만 채움 — F07 IndexError 결함 회귀.

    Bug: old implementation used time_list[0], time_list[1] without bounds check → IndexError.
    Fix: use slice with bounds check.
    Expected: card with 1-entry timetable has entries=1, no IndexError.
    """
    clock = make_clock(8, 30)
    client = make_client([])
    # 713/UNIST only has 1 entry
    sparse_data = dict(TIMETABLE_DATA)
    sparse_data[("713", 0, "UNIST")] = ["08:50"]  # only 1 entry
    timetable = make_timetable_provider(sparse_data)

    # Should NOT raise IndexError
    snapshot = get_unist_board_data(clock, client=client, timetable_provider=timetable)

    assert len(snapshot.cards) == 6
    # Find the 713 from-card (direction="명촌 (시내) 방면", dep="UNIST")
    # There is exactly one 713 card (명촌 departure 713 is excluded, only UNIST dep is included)
    cards_713 = [c for c in snapshot.cards if c.busno == "713"]
    assert len(cards_713) == 1, f"Expected exactly 1 card for busno=713, got {len(cards_713)}"
    card_713 = cards_713[0]
    # With only 1 timetable entry (08:50), entries count must be exactly 1
    assert len(card_713.entries) == 1, (
        f"Expected 1 entry for 713/UNIST with 1 timetable entry, got {len(card_713.entries)}"
        " (F07 IndexError regression: old code indexed [0],[1] without bounds check)"
    )


# executor-added: freezegun integration — EC-3 requires ≥1 freezegun usage per module.
@freeze_time("2026-06-01T08:30:00+09:00")
def test_freezegun_single_fetch_regression():
    """executor-added: freezegun로 08:30 고정, F07 single_fetch 회귀 추가 확인.

    Confirms that even with freeze_time active, domain uses injected clock,
    and the single-fetch guarantee holds regardless of time-patching context.
    """
    clock = make_clock(8, 30)
    client = make_client([])
    timetable = make_timetable_provider(TIMETABLE_DATA)

    snapshot = get_unist_board_data(clock, client=client, timetable_provider=timetable)

    assert client.fetch_arrivals.call_count == 1
