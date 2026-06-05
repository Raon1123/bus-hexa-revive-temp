"""특별 시간표(Special Edition) 관리 서비스.

## 저장 레이아웃

``data/special_timetables.json`` — 날짜→에디션 ID 매핑:
    ``{"YYYYMMDD": "edition_id", ...}``

``data/timetable/special/<edition_id>/<busno>.json`` — 에디션 시간표:
    기존 시간표 JSON 형식과 동일(``{"0": {"UNIST": ["HH:MM", ...]}, ...}``).
    키 "0"/"1"/"2" 중 최소한 "0" 과 사용되는 키를 채워야 한다.

## 우선순위

**특별 시간표 > 공휴일/요일 분류**

날짜에 특별 에디션이 지정되면 ``get_timetable`` 은 ``special/<edition_id>/`` 디렉터리를
바라보도록 wrapping된 provider가 공급된다.

provider는 요청된 weekday 키를 먼저 시도하고, 없으면 ``"0"``(평일)으로 fallback한다.
이로써 관리자가 **평일(키 "0") 탭만 채운 에디션도 공휴일·토요일에 올바르게 작동**한다.
에디션이 weekday별로 다른 시간표를 제공하려면 해당 키를 채우면 된다.

## 에디션 ID 보안

에디션 ID는 ``[A-Za-z0-9_-]`` 만 허용하며 경로 구분자(``/``, ``\\``)와 ``..`` 을 금지한다.
"""
from __future__ import annotations

import json
import re
import logging
from pathlib import Path
from typing import Iterator

from bushexa.fileio import atomic_write_json

log = logging.getLogger("bushexa.services.special_timetable")

_DATE_RE = re.compile(r"^\d{8}$")
_EDITION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _validate_edition_id(edition_id: str) -> bool:
    """에디션 ID 형식 검증: 영숫자·``_``·``-`` 만 허용, 1~64자."""
    return bool(_EDITION_ID_RE.match(edition_id))


def default_special_path(data_dir) -> Path:
    """날짜→에디션 매핑 파일의 기본 경로."""
    return Path(data_dir) / "special_timetables.json"


def special_timetable_dir(timetable_dir: Path, edition_id: str) -> Path:
    """특정 에디션의 시간표 디렉터리 경로를 반환한다."""
    return timetable_dir / "special" / edition_id


class SpecialTimetableService:
    """날짜→에디션 매핑의 로드/저장/조회 + 에디션 목록 관리.

    Parameters
    ----------
    map_path : Path
        ``data/special_timetables.json`` 경로.
    timetable_dir : Path
        ``data/timetable/`` 디렉터리 (에디션 데이터는 그 하위 ``special/`` 에 위치).
    """

    def __init__(self, map_path: Path, timetable_dir: Path):
        self.map_path = Path(map_path)
        self.timetable_dir = Path(timetable_dir)

    # ── 날짜→에디션 매핑 ────────────────────────────────────────────────────

    def load_map(self) -> dict[str, str]:
        """날짜→에디션 매핑 dict 반환. 파일 부재·파손 시 빈 dict."""
        if not self.map_path.exists():
            return {}
        try:
            data = json.loads(self.map_path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return {}
        if not isinstance(data, dict):
            return {}
        return {
            k: v
            for k, v in data.items()
            if (isinstance(k, str) and _DATE_RE.match(k)
                and isinstance(v, str) and _validate_edition_id(v))
        }

    def save_map(self, mapping: dict[str, str]) -> None:
        """날짜→에디션 매핑을 원자적으로 저장."""
        cleaned = {
            k: v
            for k, v in mapping.items()
            if (_DATE_RE.match(k) and _validate_edition_id(v))
        }
        atomic_write_json(self.map_path, cleaned, ensure_ascii=False, indent=2)

    def assign(self, date_str: str, edition_id: str) -> bool:
        """날짜에 에디션을 배정한다. 형식 오류 시 False 반환."""
        if not _DATE_RE.match(date_str) or not _validate_edition_id(edition_id):
            return False
        mapping = self.load_map()
        mapping[date_str] = edition_id
        self.save_map(mapping)
        return True

    def unassign(self, date_str: str) -> bool:
        """날짜 배정을 해제한다. 없으면 False 반환."""
        mapping = self.load_map()
        if date_str not in mapping:
            return False
        del mapping[date_str]
        self.save_map(mapping)
        return True

    def get_edition_for_date(self, date_str: str) -> str | None:
        """해당 날짜에 배정된 에디션 ID, 없으면 None."""
        return self.load_map().get(date_str)

    # ── 에디션 목록 ─────────────────────────────────────────────────────────

    def list_editions(self) -> list[str]:
        """``data/timetable/special/`` 하위의 에디션 ID 목록 (정렬)."""
        special_dir = self.timetable_dir / "special"
        if not special_dir.is_dir():
            return []
        return sorted(
            d.name for d in special_dir.iterdir()
            if d.is_dir() and _validate_edition_id(d.name)
        )

    def edition_dir(self, edition_id: str) -> Path | None:
        """에디션 디렉터리 경로. 형식 오류 시 None."""
        if not _validate_edition_id(edition_id):
            return None
        return special_timetable_dir(self.timetable_dir, edition_id)

    def edition_exists(self, edition_id: str) -> bool:
        """에디션 디렉터리가 존재하는지 확인."""
        d = self.edition_dir(edition_id)
        return d is not None and d.is_dir()

    def assignments_for_edition(self, edition_id: str) -> list[str]:
        """주어진 에디션에 배정된 날짜 목록 (정렬)."""
        mapping = self.load_map()
        return sorted(k for k, v in mapping.items() if v == edition_id)
