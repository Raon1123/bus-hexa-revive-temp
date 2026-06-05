"""W7 테스트: unist_timetable route + timetable.css (F08, TP-005).

테스트 의도:
  test_grid              — GET /timetable?day=0 → 200, 시간표 테이블 있음
  test_css_class_not_inline — 버스 배지에 class="bus-713" 형태 + 인라인 color 없음

E-13 준수: 기대값은 hand-built FullTimetableSnapshot 에서 독립적으로 정해짐.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from bushexa.domain.unist_timetable import (
    DepartureEntry,
    FullTimetableSnapshot,
    TimetableHourRow,
)
from bushexa.web.app import create_app


# ---------------------------------------------------------------------------
# Known test fixture — E-13 독립 출처
# ---------------------------------------------------------------------------

_MOCK_SNAPSHOT = FullTimetableSnapshot(
    current_time="08:30",
    weekday_str="평일 (working day)",
    selected_day=0,
    bus_legend=["513", "713", "743", "753", "1115"],
    timetable_rows=[
        TimetableHourRow(
            hour="07",
            departures=[
                DepartureEntry(minute="20", busno="713"),
                DepartureEntry(minute="45", busno="743"),
            ],
        ),
        TimetableHourRow(
            hour="08",
            departures=[
                DepartureEntry(minute="10", busno="753"),
                DepartureEntry(minute="30", busno="1115"),
            ],
        ),
    ],
    is_empty=False,
)


@pytest.fixture
def app(app_config_test):
    return create_app(app_config_test)


@pytest.fixture
def client(app):
    return app.test_client()


# ---------------------------------------------------------------------------
# AC-1 — GET /timetable?day=0 → 200, 시간표 테이블 있음
# ---------------------------------------------------------------------------

def test_grid(client):
    """/timetable?day=0 HTML에 시간표 테이블과 시간대 행이 있는지 검증.

    독립 출처: P4 W7 AC-1, TP-005 §2 명세.
    """
    with patch(
        "bushexa.web.routes.unist_timetable.get_full_timetable_data",
        return_value=_MOCK_SNAPSHOT,
    ):
        resp = client.get("/timetable?day=0")

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    html = resp.data.decode("utf-8")
    assert "timetable-grid" in html, "timetable-grid class missing from /timetable response"
    assert "07" in html, "Hour '07' from mock timetable not in HTML"
    assert "08" in html, "Hour '08' from mock timetable not in HTML"


# ---------------------------------------------------------------------------
# AC-2 — class="bus-713" 사용 + 인라인 color 없음
# ---------------------------------------------------------------------------

def test_css_class_not_inline(client):
    """버스 색상이 class="bus-713"으로 표현되고 style="color:" 인라인이 없는지 검증.

    독립 출처: P4 W7 AC-2, F08 §4.3 — 인라인 스타일 제거, CSS 클래스 사용.
    """
    with patch(
        "bushexa.web.routes.unist_timetable.get_full_timetable_data",
        return_value=_MOCK_SNAPSHOT,
    ):
        resp = client.get("/timetable?day=0")

    html = resp.data.decode("utf-8")

    # CSS 클래스 형태 확인 (mock에 713, 743, 753, 1115 포함)
    assert 'class="bus-badge bus-713"' in html or 'bus-713' in html, (
        'class="bus-713" not found in /timetable response (CSS class approach expected)'
    )

    # 인라인 style="color:" 없음
    assert 'style="color:' not in html, (
        'Inline style="color:" found in /timetable response — must use CSS class instead'
    )
