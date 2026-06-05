"""W3 테스트: busno route (F02, TP-002).

테스트 의도:
  test_valid         — GET /busno?bus=713&day=0&dep=UNIST → 200, class="timetable" 포함
  test_invalid_bus_warns — ?bus=999 → 200 + 경고 배너 (500 아님)

E-13 준수: 기대값은 hand-built BusnoTimetable (알려진 입력) 에서 독립적으로 정해짐.
도메인 실제 구현값을 읽어 기대값을 세우는 tautology 없음.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from bushexa.domain.busno import BusnoTimetable, TimetableHourRow
from bushexa.web.app import create_app

# ---------------------------------------------------------------------------
# Known test fixture — independent from domain implementation (E-13)
# ---------------------------------------------------------------------------

_KNOWN_TIMETABLE = BusnoTimetable(
    current_time="08:30",
    weekday_str="평일 (working day)",
    busnos=["513", "713", "743", "753", "1115"],
    selected_bus="713",
    day_options=["Weekday", "Saturday", "Sunday/Holiday"],
    selected_day=0,
    terminals=["UNIST", "명촌"],
    selected_dep="UNIST",
    timetable_rows=[
        TimetableHourRow(hour="07", minutes="20, 40"),
        TimetableHourRow(hour="08", minutes="10, 30"),
    ],
    warning=None,
)

_WARN_TIMETABLE = BusnoTimetable(
    current_time="08:30",
    weekday_str="평일 (working day)",
    busnos=["513", "713", "743", "753", "1115"],
    selected_bus="513",  # fallback to first bus
    day_options=["Weekday", "Saturday", "Sunday/Holiday"],
    selected_day=0,
    terminals=["덕하", "삼남"],
    selected_dep="덕하",
    timetable_rows=[],
    warning="유효하지 않은 버스번호: '999'.",
)


@pytest.fixture
def app(app_config_test):
    return create_app(app_config_test)


@pytest.fixture
def client(app):
    return app.test_client()


# ---------------------------------------------------------------------------
# AC-1 — GET /busno?bus=713&day=0&dep=UNIST → 200 + class="timetable"
# ---------------------------------------------------------------------------

def test_valid(client):
    """유효한 쿼리로 /busno가 200이고 시간표 테이블(class="timetable")이 있는지 검증.

    독립 출처: P4 W3 AC-1, TP-002, F02 §4.2.
    """
    with patch(
        "bushexa.web.routes.busno.get_busno_page_data",
        return_value=_KNOWN_TIMETABLE,
    ):
        resp = client.get("/busno?bus=713&day=0&dep=UNIST")

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    html = resp.data.decode("utf-8")
    assert 'class="timetable"' in html, 'class="timetable" table missing from /busno response'
    # 알려진 행이 렌더됐는지 확인
    assert "07" in html, "Hour '07' from mock timetable not in HTML"
    assert "20, 40" in html, "Minutes '20, 40' from mock row not in HTML"


# ---------------------------------------------------------------------------
# AC-2 — ?bus=999 → 200 + 경고 배너 (500 아님)
# ---------------------------------------------------------------------------

def test_invalid_bus_warns(client):
    """존재하지 않는 버스번호를 주면 500이 아니라 200 + 경고 메시지.

    독립 출처: P4 W3 AC-2, TP-002 §6 — 잘못된 파라미터는 경고 배너.
    """
    with patch(
        "bushexa.web.routes.busno.get_busno_page_data",
        return_value=_WARN_TIMETABLE,
    ):
        resp = client.get("/busno?bus=999")

    assert resp.status_code == 200, f"Expected 200 not 500, got {resp.status_code}"
    html = resp.data.decode("utf-8")
    assert "warning-banner" in html, "warning-banner class missing from invalid-bus response"
    assert "유효하지 않은 버스번호" in html, "Warning message not found in response"
