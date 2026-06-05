"""실효 공휴일 — 읽기 경로(캐시 전용) + 백엔드 갱신.

설계(ADR-010 정합 확장): 화면(board/lite/busno/unist_timetable 등)은 **외부 API를 절대
호출하지 않는다**. data.go.kr 공휴일 API는 백엔드 cache-refresh 워커가 새벽 유휴시간에만
호출해 ``<data_dir>/holiday_cache.json`` 에 영속화하고, 읽기 경로는 이 파일 + admin 지정
(``holidays.json``) 만 합집합으로 읽는다.

- 읽기 경로:  :func:`read_effective_holidays` — admin ∪ 캐시, 네트워크 없음, ~파일 2회 읽기.
- 백엔드:     :class:`HolidayCache` ``.refresh(client, months)`` — API 호출 후 월별 영속화.

월별(JSON ``{"YYYYMM": ["YYYYMMDD", ...]}``)로 저장해, 일부 월 API 실패가 다른 월의
캐시를 덮어쓰지 않게 한다(실패 월은 기존 값 보존). 빈 달도 캐시한다 — 읽기 경로가 빈 달
때문에 API로 폴백하는 일이 없도록(과거 인메모리 캐시의 결함을 제거).
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date
from pathlib import Path

from bushexa.fileio import atomic_write_json
from bushexa.services.holiday_editor import HolidayEditor, default_holidays_path

log = logging.getLogger("bushexa.services.holiday_service")

_DATE_RE = re.compile(r"^\d{8}$")
_YM_RE = re.compile(r"^\d{6}$")


def default_holiday_cache_path(data_dir) -> Path:
    """API 공휴일 캐시 파일 경로 (``<data_dir>/holiday_cache.json``)."""
    return Path(data_dir) / "holiday_cache.json"


def upcoming_months(d: date, count: int = 2) -> list[tuple[int, int]]:
    """``d`` 기준 이번 달부터 ``count``개월의 (year, month) 목록.

    월말 자정 롤오버 직후라도 '오늘이 속한 달'이 cold-miss 되지 않도록 백엔드는
    이번 달 + 다음 달(기본 2개월)을 함께 갱신한다.
    """
    out: list[tuple[int, int]] = []
    y, m = d.year, d.month
    for _ in range(count):
        out.append((y, m))
        m += 1
        if m > 12:
            m = 1
            y += 1
    return out


class HolidayCache:
    """data.go.kr 공휴일 API 결과의 월별 영속 캐시.

    파일 부재·파손 시 빈 캐시로 간주한다(읽기 경로는 절대 예외를 던지지 않음).
    """

    def __init__(self, path):
        self.path = Path(path)

    def _load_raw(self) -> dict[str, list[str]]:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return {}
        if not isinstance(data, dict):
            return {}
        clean: dict[str, list[str]] = {}
        for ym, dates in data.items():
            if isinstance(ym, str) and _YM_RE.match(ym) and isinstance(dates, list):
                clean[ym] = sorted(
                    s for s in dates if isinstance(s, str) and _DATE_RE.match(s)
                )
        return clean

    def load(self) -> set[str]:
        """캐시된 모든 월의 공휴일을 평탄화한 set(YYYYMMDD). 읽기 경로 전용."""
        return {d for dates in self._load_raw().values() for d in dates}

    def refresh(self, client, months) -> set[str]:
        """``months`` (iterable[(year, month)])를 API로 갱신하고 영속화한다(백엔드 전용).

        월 단위로 처리: 성공한 월만 갱신하고 실패한 월은 기존 캐시를 보존한다(전체를
        덮어쓰지 않음). 빈 결과(공휴일 없는 달)도 그대로 캐시한다. 반환값은 갱신 후
        전체 공휴일 set.
        """
        raw = self._load_raw()
        changed = False
        for year, month in months:
            try:
                dates = client.fetch(year, month)
            except Exception as exc:
                log.warning("공휴일 API 갱신 실패 %d-%02d (기존 캐시 유지): %s", year, month, exc)
                continue
            ym = f"{year}{month:02d}"
            raw[ym] = sorted(d.strftime("%Y%m%d") for d in dates)
            changed = True
            log.info("공휴일 캐시 갱신 %s: %d건", ym, len(raw[ym]))
        if changed:
            atomic_write_json(self.path, raw, ensure_ascii=False, indent=2)
        return {d for dates in raw.values() for d in dates}


def read_effective_holidays(data_dir) -> set[str]:
    """읽기 경로 전용 실효 공휴일 set = admin 지정(holidays.json) ∪ API 캐시(holiday_cache.json).

    외부 API를 호출하지 않는다 — 두 로컬 JSON 파일만 읽으므로 화면 경로에서 즉시 반환된다.
    """
    admin = HolidayEditor(default_holidays_path(data_dir)).load()
    cached = HolidayCache(default_holiday_cache_path(data_dir)).load()
    return admin | cached


# ---------------------------------------------------------------------------
# admin 전용 — 임의 날짜 라이브 조회
# ---------------------------------------------------------------------------
# 공개 화면(board/busno/unist_timetable)은 위 read_effective_holidays(캐시 전용)를 쓴다.
# admin '그날 미리보기'는 운영자가 임의의 (먼) 날짜를 고를 수 있어 캐시(이번+다음 달) 범위를
#벗어나므로, 저빈도 운영자 액션에 한해 라이브 API를 호출한다. 결과는 app-scope(워커별)
# 메모 캐시로 같은 월 반복 호출을 줄인다.


def _fetch_api_holidays(client, year: int, month: int) -> set[str]:
    """HolidayClient.fetch를 호출해 YYYYMMDD 문자열 set 반환. 실패 시 빈 set."""
    try:
        dates = client.fetch(year, month)
    except Exception as exc:
        log.warning("공휴일 API 조회 실패 %d-%02d: %s", year, month, exc)
        return set()
    return {d.strftime("%Y%m%d") for d in dates}


def _cached_api_holidays(client, year: int, month: int, cache: dict) -> set[str]:
    """app-scope 메모 캐시를 경유한 API 공휴일 조회(성공한 비어있지 않은 결과만 캐시)."""
    key = (year, month)
    if key in cache:
        return cache[key]
    result = _fetch_api_holidays(client, year, month)
    if result:
        cache[key] = result
    return result


def get_effective_holiday_set(d: date, *, holiday_editor, holiday_client, cache: dict) -> set[str]:
    """admin 미리보기 전용: ``d`` 월의 admin 지정 ∪ 라이브 API 공휴일 set.

    공개 화면 경로에서는 쓰지 말 것 — 외부 API를 호출하므로 cold 지연을 유발한다
    (화면은 :func:`read_effective_holidays` 사용).
    """
    admin_dates = holiday_editor.load()
    api_dates = _cached_api_holidays(holiday_client, d.year, d.month, cache)
    return admin_dates | api_dates
