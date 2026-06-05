"""공휴일·특별 시간표 우선순위 테스트.

우선순위: 특별 시간표 > 공휴일 > 평일(요일 분류)

테스트 시나리오:
1. 공휴일로 지정된 날짜 → weekday=2 (일·공휴일 스케줄)
2. 공휴일 제거 → weekday=0 (평일)로 복귀
3. 특별 시간표가 배정된 날 → 특별 시간표가 공휴일보다 우선 (timetable_provider 교체로 구현)
4. 특별 시간표 미배정 날 → 영향 없음
"""
from __future__ import annotations

import datetime
import json
from pathlib import Path
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest

from bushexa.domain.board import get_board_data, BoardSnapshot
from bushexa.data.timetable import get_timetable
from bushexa.services.special_timetable import SpecialTimetableService
from bushexa.time_utils import get_weekday

KST = ZoneInfo("Asia/Seoul")


class FakeClock:
    def __init__(self, now: datetime.datetime):
        self._now = now

    def now(self) -> datetime.datetime:
        return self._now


# ── Feature 1: 공휴일 → weekday=2 ─────────────────────────────────────────

def test_holiday_set_makes_weekday_2():
    """공휴일 집합에 포함된 날짜는 평일(월요일)이더라도 weekday=2를 반환한다."""
    # 2026-06-01 = 월요일(weekday()=0)
    d = datetime.date(2026, 6, 1)
    holiday_set = {"20260601"}

    result = get_weekday(d, holiday_set)
    assert result == 2, "공휴일이면 2(일·공휴일 스케줄)를 반환해야 함"


def test_removing_holiday_reverts_to_weekday():
    """공휴일 집합에서 제거하면 평일(0)으로 복귀한다."""
    d = datetime.date(2026, 6, 1)  # 월요일
    holiday_set: set[str] = set()  # 빈 집합 → 공휴일 없음

    result = get_weekday(d, holiday_set)
    assert result == 0, "공휴일 제거 후 평일(0)이어야 함"


def test_holiday_affects_board_timetable_choice():
    """공휴일 set이 주입되면 get_board_data가 weekday=2 시간표를 선택한다.

    독립 출처: 공휴일(20260601) + FakeClock(2026-06-01, 월요일) → weekday=2
    시간표 provider: weekday=0 → 빈 목록, weekday=2 → ["10:00"]
    공휴일 없으면 weekday=0 → 빈 목록 → 빈 보드
    공휴일 있으면 weekday=2 → ["10:00"] → 10:00 이후이므로 보드에 나타남
    """
    # FakeClock: 2026-06-01 09:00 KST (월요일이지만 공휴일로 지정할 것)
    clock = FakeClock(datetime.datetime(2026, 6, 1, 9, 0, 0, tzinfo=KST))

    # timetable_provider: weekday=0(평일)은 빈 목록, weekday=2(공휴일)은 ["10:00"]
    def timetable_provider(busno, weekday, departure):
        if weekday == 2 and busno == "713" and departure == "UNIST":
            return ["10:00", "11:00"]
        return []

    client = MagicMock()
    client.fetch_arrivals.return_value = []

    # 공휴일 set 없이 → weekday=0 → 빈 목록 → 빈 보드
    snapshot_no_holiday = get_board_data(
        "196040234", clock, client=client,
        timetable_provider=timetable_provider,
        holiday_set=set(),
    )

    # 공휴일 set 있이 (20260601=오늘) → weekday=2 → ["10:00"] → 보드에 10:00 등장
    snapshot_with_holiday = get_board_data(
        "196040234", clock, client=client,
        timetable_provider=timetable_provider,
        holiday_set={"20260601"},
    )

    no_holiday_times = [r.arrival_time for r in snapshot_no_holiday.rows]
    with_holiday_times = [r.arrival_time for r in snapshot_with_holiday.rows]

    assert "10:00" not in no_holiday_times, "공휴일 없으면 공휴일 시간표 미표시"
    assert "10:00" in with_holiday_times, "공휴일 지정 시 공휴일 시간표 표시"


# ── Feature 2: 특별 시간표 우선순위 ──────────────────────────────────────────

def test_special_edition_overrides_normal_timetable(tmp_path):
    """특별 에디션 배정 날 → 특별 시간표가 정상 시간표보다 우선.

    시나리오:
    - 오늘(20260610): 특별 에디션 "exam" 배정
    - 정상 시간표(weekday=0): 713/UNIST → ["08:00"]
    - 특별 시간표(weekday=0): 713/UNIST → ["14:00"]  ← 시험기간 특별 운행
    - 기대: 보드에 "14:00"이 나타나고, "08:00"은 나타나지 않는다.
    """
    # 특별 에디션 파일 생성
    tt_dir = tmp_path / "timetable"
    tt_dir.mkdir()
    edition_dir = tt_dir / "special" / "exam"
    edition_dir.mkdir(parents=True)
    # 713.json: weekday=0, UNIST → ["14:00"]
    (edition_dir / "713.json").write_text(json.dumps({
        "0": {"UNIST": ["14:00", "15:00"]},
        "1": {"UNIST": []},
        "2": {"UNIST": []},
    }), encoding="utf-8")

    svc = SpecialTimetableService(
        map_path=tmp_path / "special_timetables.json",
        timetable_dir=tt_dir,
    )
    svc.assign("20260610", "exam")

    # FakeClock: 2026-06-10 07:00 KST (수요일, 평일=weekday 0)
    # 07:00이어야 08:00이 미래 시간으로 보드에 나타남
    clock = FakeClock(datetime.datetime(2026, 6, 10, 7, 0, 0, tzinfo=KST))
    today_str = "20260610"

    # 라우트가 하는 것처럼 provider를 교체
    edition_id = svc.get_edition_for_date(today_str)
    assert edition_id == "exam"
    assert svc.edition_exists(edition_id)
    ed_dir = svc.edition_dir(edition_id)

    def special_provider(busno, weekday, departure, *, dir=ed_dir):
        """라우트와 동일하게 weekday fallback 포함."""
        try:
            return get_timetable(busno, weekday, departure, dir=dir)
        except KeyError:
            return get_timetable(busno, 0, departure, dir=dir)

    def normal_provider(busno, weekday, departure):
        if busno == "713" and departure == "UNIST":
            return ["08:00", "09:30"]
        return []

    client = MagicMock()
    client.fetch_arrivals.return_value = []

    # 특별 시간표 provider 사용
    snapshot_special = get_board_data(
        "196040234", clock, client=client,
        timetable_provider=special_provider,
    )
    # 정상 시간표 provider 사용
    snapshot_normal = get_board_data(
        "196040234", clock, client=client,
        timetable_provider=normal_provider,
    )

    special_times = [r.arrival_time for r in snapshot_special.rows]
    normal_times = [r.arrival_time for r in snapshot_normal.rows]

    assert "14:00" in special_times, "특별 시간표에서 14:00이 표시돼야 함"
    assert "08:00" not in special_times, "특별 시간표 적용 시 정상 시간표(08:00) 미표시"
    assert "08:00" in normal_times, "정상 시간표에는 08:00이 표시돼야 함"


def test_special_over_holiday_precedence(tmp_path):
    """특별 시간표는 공휴일 분류보다 우선한다 — 판별 테스트.

    시나리오 (실제 운영 상황):
    - 오늘(20260601)은 공휴일(weekday=2)
    - 에디션 "exam": weekday="0"(평일) 탭만 채움, "2" 키는 없음
    - 공휴일 분류만 적용되면 weekday=2 키를 찾다가 KeyError → 빈 보드 (버그)
    - 특별 에디션 우선순위가 올바르면: weekday=2 없으면 "0"으로 fallback → 14:00 표시

    이 테스트는 provider가 weekday="0" fallback을 구현하는지를 검증한다.
    """
    tt_dir = tmp_path / "timetable"
    tt_dir.mkdir()
    edition_dir = tt_dir / "special" / "exam"
    edition_dir.mkdir(parents=True)

    # 에디션에 weekday="0"만 채움 — "2" 키 없음 (판별 조건)
    (edition_dir / "713.json").write_text(json.dumps({
        "0": {"UNIST": ["14:00", "15:00"]},   # 특별 운행 시간표
        "1": {"UNIST": []},
        # "2" 키 의도적으로 생략
    }), encoding="utf-8")

    svc = SpecialTimetableService(
        map_path=tmp_path / "special_timetables.json",
        timetable_dir=tt_dir,
    )
    svc.assign("20260601", "exam")

    # FakeClock: 2026-06-01 09:00 KST = 월요일이지만 공휴일로 지정 → weekday=2
    clock = FakeClock(datetime.datetime(2026, 6, 1, 9, 0, 0, tzinfo=KST))
    holiday_set = {"20260601"}  # 오늘을 공휴일로 지정

    ed_dir = svc.edition_dir("exam")

    # 라우트가 하는 것처럼 fallback 포함 provider 사용
    def special_provider_with_fallback(busno, weekday, departure, *, dir=ed_dir):
        try:
            return get_timetable(busno, weekday, departure, dir=dir)
        except KeyError:
            return get_timetable(busno, 0, departure, dir=dir)

    client = MagicMock()
    client.fetch_arrivals.return_value = []

    # 공휴일 set 주입 → weekday=2로 계산
    # 특별 provider fallback → weekday=2 없어도 "0"에서 14:00을 가져와야 함
    snapshot = get_board_data(
        "196040234", clock, client=client,
        timetable_provider=special_provider_with_fallback,
        holiday_set=holiday_set,
    )

    times = [r.arrival_time for r in snapshot.rows]
    assert "14:00" in times, (
        "공휴일 날짜에 특별 에디션(key='0'만 있음)이 배정되면 "
        "weekday=0 fallback으로 특별 시간표(14:00)가 표시돼야 함"
    )


def test_unassigned_date_unaffected(tmp_path):
    """특별 에디션이 배정되지 않은 날짜는 정상 시간표를 사용한다."""
    svc = SpecialTimetableService(
        map_path=tmp_path / "special_timetables.json",
        timetable_dir=tmp_path / "timetable",
    )
    # 배정 없음
    assert svc.get_edition_for_date("20260610") is None
