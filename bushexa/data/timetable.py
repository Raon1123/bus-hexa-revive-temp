"""시간표 JSON 로더·검증·저장 (W3).

- ``get_timetable``  : 노선·요일·기점별 "HH:MM" 목록 조회 (런타임 경로)
- ``validate_timetable`` : weekday 키·시각 형식·범위·중복 검사
- ``save_timetable`` : ADR-012 준수 저장(fileio 경유) — P2 크롤 저장·P4 관리자 편집의 공용 쓰기 경로

기본 디렉터리는 ``data/timetable/``, ``BUSHEXA_TIMETABLE_DIR`` 환경변수로 override.
xlsx→json 초기 부트스트랩(legacy ``init_timetable``)은 1회성 도구로, 현재 timetable/*.json이
이미 존재하므로 P2 시간표 도구에서 다룬다(ADR-012: 그 저장도 ``save_timetable`` 경유).
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from bushexa import fileio
from bushexa.data.constants import ROUTEID

logger = logging.getLogger("bushexa.data.timetable")

_DEFAULT_DIR = "data/timetable"
_VALID_WEEKDAYS = {"0", "1", "2"}


def timetable_dir() -> Path:
    """시간표 JSON 디렉터리. BUSHEXA_TIMETABLE_DIR로 override 가능."""
    return Path(os.environ.get("BUSHEXA_TIMETABLE_DIR", _DEFAULT_DIR))


def _route_path(bus_number, base: Path | None) -> Path:
    return (Path(base) if base is not None else timetable_dir()) / f"{bus_number}.json"


def get_timetable(bus_number, weekday: int, departure: str, *, dir: Path | None = None) -> list[str]:
    """``{busno}.json``에서 weekday·departure에 해당하는 "HH:MM" 목록을 반환."""
    departure = departure.split()[0]
    with open(_route_path(bus_number, dir), "r", encoding="utf-8") as f:
        data = json.load(f)
    return data[str(weekday)][departure]


def get_busroute_info() -> tuple[list[str], dict[str, list[str]]]:
    """ROUTEID에서 (버스번호 목록, 버스번호→기점목록) 추출. legacy 동등."""
    busnos: list[str] = []
    departure_dict: dict[str, list[str]] = {}
    for routes in ROUTEID.values():
        bus_number = routes[0]
        if bus_number not in busnos:
            busnos.append(bus_number)
        departure_dict.setdefault(bus_number, [])
        departure = routes[2]
        if departure not in departure_dict[bus_number]:
            departure_dict[bus_number].append(departure)
    return busnos, departure_dict


@dataclass(frozen=True)
class ValidationIssue:
    code: str  # "bad_weekday" | "bad_time_format" | "out_of_range" | "duplicate"
    weekday: str
    departure: str
    detail: str


def validate_timetable(data: dict) -> list[ValidationIssue]:
    """시간표 데이터 무결성 검사. 위반마다 ValidationIssue 1건을 모아 반환."""
    issues: list[ValidationIssue] = []
    for wd, deps in data.items():
        if wd not in _VALID_WEEKDAYS:
            issues.append(ValidationIssue("bad_weekday", str(wd), "", f"weekday {wd!r}"))
            continue
        for dep, times in deps.items():
            seen: set[str] = set()
            for t in times:
                if not (isinstance(t, str) and len(t) == 5 and t[2] == ":"
                        and t[:2].isdigit() and t[3:].isdigit()):
                    issues.append(ValidationIssue("bad_time_format", str(wd), str(dep), repr(t)))
                    continue
                hh, mm = int(t[:2]), int(t[3:])
                if not (0 <= hh <= 23 and 0 <= mm <= 59):
                    issues.append(ValidationIssue("out_of_range", str(wd), str(dep), repr(t)))
                if t in seen:
                    issues.append(ValidationIssue("duplicate", str(wd), str(dep), repr(t)))
                seen.add(t)
    return issues


def save_timetable(bus_number, data: dict, *, dir: Path | None = None,
                   validate: bool = True) -> Path:
    """시간표 데이터를 ``{busno}.json``에 ADR-012 준수로 저장(fileio 원자적 쓰기+감사 로그).

    validate=True(기본)면 저장 전 validate_timetable로 검사하고 위반 시 ValueError.
    """
    if validate:
        issues = validate_timetable(data)
        if issues:
            raise ValueError(f"시간표 검증 실패({len(issues)}건): {issues[:3]}")
    path = _route_path(bus_number, dir)
    fileio.atomic_write_json(path, data, ensure_ascii=False, indent=4, logger=logger)
    return path
