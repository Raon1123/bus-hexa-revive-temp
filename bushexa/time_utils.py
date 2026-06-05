"""KST 시간·요일·공휴일 유틸 (W2).

ADR-008: 시간 의존성을 주입 가능한 ``Clock``으로 추상화해 결정적 테스트(freezegun/FakeClock)를
가능하게 한다. ``is_holiday``는 네트워크/파일 의존이 없는 순수 함수다(공휴일 집합을 주입받음).
요일 코드: 0=평일, 1=토요일, 2=일요일/공휴일 (공휴일이 우선).
"""
from __future__ import annotations

import datetime as _dt
from typing import Protocol, runtime_checkable
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")


@runtime_checkable
class Clock(Protocol):
    """현재 시각 공급자. 기본 구현은 :class:`KSTClock`, 테스트는 FakeClock/freezegun."""

    def now(self) -> _dt.datetime: ...


class KSTClock:
    """KST(UTC+9) aware 현재 시각."""

    def now(self) -> _dt.datetime:
        return _dt.datetime.now(tz=KST)


def get_now(clock: Clock | None = None) -> _dt.datetime:
    """현재 KST 시각. clock 주입 시 그것을 사용(테스트 결정성)."""
    return (clock or KSTClock()).now()


def is_holiday(d: _dt.date, holiday_set: set[str]) -> bool:
    """``d``(YYYYMMDD)가 공휴일 집합에 포함되면 True. 순수 함수(외부 의존 없음)."""
    return d.strftime("%Y%m%d") in holiday_set


def get_weekday(d: _dt.date | _dt.datetime | None = None,
                holiday_set: set[str] | None = None,
                *, clock: Clock | None = None) -> int:
    """요일 코드 반환: 0=평일, 1=토요일, 2=일요일/공휴일.

    공휴일이면 평일/토요일이라도 2(일/공휴일 스케줄)를 우선 반환한다.
    ``d`` 미지정 시 ``clock``(기본 KSTClock)의 현재 날짜를 사용한다.
    """
    holiday_set = holiday_set or set()
    if d is None:
        d = (clock or KSTClock()).now()
    if isinstance(d, _dt.datetime):
        d = d.date()
    if is_holiday(d, holiday_set):
        return 2
    wd = d.weekday()  # Mon=0 … Sat=5, Sun=6
    if wd == 5:
        return 1
    if wd == 6:
        return 2
    return 0


def get_time(holiday_set: set[str] | None = None,
             *, clock: Clock | None = None) -> tuple[int, int, int]:
    """(요일코드, 시, 분) 튜플. legacy ``get_time`` 대체."""
    now = (clock or KSTClock()).now()
    return get_weekday(now, holiday_set), now.hour, now.minute
