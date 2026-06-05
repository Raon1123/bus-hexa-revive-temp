"""W2 time_utils 검증. 요일은 freezegun으로 고정, 기대값은 그레고리력(독립 출처)에서.

2026-06-01=월, 2026-06-13=토, 2026-06-14=일 (달력 확인).
"""
from __future__ import annotations

from datetime import timedelta

from freezegun import freeze_time

from bushexa.time_utils import KSTClock, get_weekday


@freeze_time("2026-06-01")  # 월요일
def test_weekday_on_plain_weekday():
    """평일을 freeze하고 빈 holiday_set을 주면 get_weekday가 0(평일)을 반환하는지."""
    assert get_weekday(holiday_set=set()) == 0


@freeze_time("2026-06-13")  # 토요일 (공휴일 아님)
def test_weekday_on_saturday():
    """일반 토요일을 freeze하여 1을 반환하는지(현충일 06-06과 구분되는 평범한 토요일)."""
    assert get_weekday(holiday_set=set()) == 1


@freeze_time("2026-06-14")  # 일요일
def test_weekday_on_sunday():
    """일요일을 freeze하여 2를 반환하는지."""
    assert get_weekday(holiday_set=set()) == 2


@freeze_time("2026-06-01")  # 월요일이지만 공휴일로 주입
def test_weekday_on_holiday_weekday():
    """평일이지만 holiday_set에 든 날짜는 평일임에도 2(공휴일 우선)를 반환하는지."""
    assert get_weekday(holiday_set={"20260601"}) == 2


def test_kstclock_is_kst():
    """KSTClock().now()의 utcoffset이 정확히 9시간(UTC+9)인지."""
    assert KSTClock().now().utcoffset() == timedelta(hours=9)
