"""관리자 지정 공휴일 CRUD 저장소.

관리자가 직접 지정한 공휴일 날짜(YYYYMMDD 문자열)를 JSON 파일로 관리한다.
파일 위치: ``<data_dir>/holidays.json``

실효 공휴일 집합(effective holiday_set) = admin 지정 날짜 UNION data.go.kr API 공휴일.
실효 집합 계산은 :mod:`bushexa.services.holiday_service` 에서 담당한다.

구조: ``["YYYYMMDD", ...]`` (날짜 문자열 배열).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from bushexa.fileio import atomic_write_json

_DATE_RE = re.compile(r"^\d{8}$")


def default_holidays_path(data_dir) -> Path:
    """admin 공휴일 파일의 기본 경로 (``<data_dir>/holidays.json``)."""
    return Path(data_dir) / "holidays.json"


class HolidayEditor:
    """관리자 지정 공휴일의 로드/추가/제거/저장. 파일 부재 시 빈 set로 간주."""

    def __init__(self, path):
        self.path = Path(path)

    def load(self) -> set[str]:
        """저장된 admin 지정 날짜 set 반환. 파일 부재·파손 시 빈 set."""
        if not self.path.exists():
            return set()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return set()
        if not isinstance(data, list):
            return set()
        return {s for s in data if isinstance(s, str) and _DATE_RE.match(s)}

    def save(self, dates: set[str]) -> None:
        """날짜 set을 원자적으로 저장. 형식 불일치 항목은 제거."""
        cleaned = sorted(
            s for s in dates if isinstance(s, str) and _DATE_RE.match(s)
        )
        atomic_write_json(self.path, cleaned, ensure_ascii=False, indent=2)

    def add(self, date_str: str) -> bool:
        """날짜를 추가하고 저장. YYYYMMDD 형식이 아니면 False 반환."""
        if not isinstance(date_str, str) or not _DATE_RE.match(date_str):
            return False
        dates = self.load()
        dates.add(date_str)
        self.save(dates)
        return True

    def remove(self, date_str: str) -> bool:
        """날짜를 제거하고 저장. 없으면 False 반환."""
        dates = self.load()
        if date_str not in dates:
            return False
        dates.discard(date_str)
        self.save(dates)
        return True
