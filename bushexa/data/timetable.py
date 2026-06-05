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
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

from bushexa import fileio
from bushexa.data.constants import ROUTEID

logger = logging.getLogger("bushexa.data.timetable")

_DEFAULT_DIR = "data/timetable"
_VALID_WEEKDAYS = {"0", "1", "2"}

# ---------------------------------------------------------------------------
# 리뷰 E4: get_timetable mtime 기반 캐시
#
# 캐시 설계 근거:
#   - 키: os.path.abspath(경로) — resolve()와 달리 순수 렉시컬 연산이므로 심볼릭 링크
#     오류나 파일 부재에서도 안전하며, special/<edition>/ 경로와 기본 경로를 자연스럽게
#     분리한다.
#   - 서명: (mtime_ns, size) — fileio.atomic_write_json이 os.replace(임시파일→원본)로
#     갱신하므로 inode 교체 시 mtime_ns가 반드시 변한다. size를 함께 확인해 동일
#     타임스탬프(빠른 연속 쓰기) 충돌을 방어한다(테스트 E-13 무효화 케이스 참고).
#   - Lock: threading.Lock — gunicorn sync 워커는 단일 스레드이지만, 크롤 데몬·테스트
#     병렬 실행 시 다른 스레드가 같은 경로를 동시에 재로드하는 레이스를 막는다.
#     Lock 비용(소켓이 없는 단순 mutex)은 파일 I/O 대비 무시 가능하다.
#   - 반환값 안전성: data[weekday][departure] 리스트를 그대로 반환하면 캐시 내부 객체를
#     호출자가 수정(sort/append)할 경우 캐시가 오염된다(리뷰 #2 캐시 오염 재현 경로).
#     admin.py:1179·1213을 확인한 결과 times를 dict에 대입만 하고 변형하지 않으나,
#     향후 호출처 보증을 위해 list() 얕은 복사로 새 리스트를 반환한다.
#     요소는 불변 str("HH:MM")이므로 얕은 복사로 완전 분리된다 — 깊은 복사 불필요.
# ---------------------------------------------------------------------------

class _CacheEntry(NamedTuple):
    mtime_ns: int
    size: int
    data: dict  # 전체 weekday→departure→[times] dict (내부 전용, 외부로 직접 노출 금지)


_cache: dict[str, _CacheEntry] = {}   # 절대경로 → _CacheEntry
_cache_lock = threading.Lock()


def _clear_cache() -> None:
    """캐시를 비운다. 테스트 격리용 — 프로덕션 코드는 호출하지 않는다."""
    with _cache_lock:
        _cache.clear()


def timetable_dir() -> Path:
    """시간표 JSON 디렉터리. BUSHEXA_TIMETABLE_DIR로 override 가능."""
    return Path(os.environ.get("BUSHEXA_TIMETABLE_DIR", _DEFAULT_DIR))


def _route_path(bus_number, base: Path | None) -> Path:
    return (Path(base) if base is not None else timetable_dir()) / f"{bus_number}.json"


def get_timetable(bus_number, weekday: int, departure: str, *, dir: Path | None = None) -> list[str]:
    """``{busno}.json``에서 weekday·departure에 해당하는 "HH:MM" 목록을 반환.

    mtime_ns + size 서명 기반 캐시를 사용한다. 파일이 atomic_write_json(os.replace)으로
    교체되면 서명이 변해 자동 무효화된다. FileNotFoundError는 os.stat 단계에서 발생해
    호출자 계약(파일 없으면 예외)을 유지한다.
    """
    departure = departure.split()[0]
    path_str = os.path.abspath(_route_path(bus_number, dir))

    # os.stat은 파일 부재 시 FileNotFoundError를 발생시켜 호출자 계약을 유지한다.
    st = os.stat(path_str)
    sig = (st.st_mtime_ns, st.st_size)

    with _cache_lock:
        entry = _cache.get(path_str)
        if entry is not None and (entry.mtime_ns, entry.size) == sig:
            # 캐시 히트 — 파일 I/O 없이 반환 (list() 복사로 캐시 내부 보호)
            return list(entry.data[str(weekday)][departure])

    # 캐시 미스 또는 무효화 — 재로드
    with open(path_str, "r", encoding="utf-8") as f:
        data = json.load(f)

    with _cache_lock:
        _cache[path_str] = _CacheEntry(mtime_ns=sig[0], size=sig[1], data=data)

    return list(data[str(weekday)][departure])


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
