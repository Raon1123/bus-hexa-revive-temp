"""W11 — 시간표 편집 서비스 (F04 §4.4).

TimetableEditor: validate → backup → atomic save 순서.
P1 함수를 그대로 재사용(재구현 금지):
  - bushexa.data.timetable.validate_timetable  (validate 위임)
  - bushexa.data.timetable.save_timetable      (원자적 저장)
  - bushexa.data.timetable.get_busroute_info   (list_routes)

Designer 정정 반영:
  F04 §6의 ValidationIssue 스케치(index/value 필드)는 P1 실구현과 다름.
  P1 실구현의 ValidationIssue(code/weekday/departure/detail,
  code∈{bad_weekday,bad_time_format,out_of_range,duplicate})가 정답이며
  이를 그대로 사용한다.

ADR-008: 시각 직접 호출 금지 — clock 주입으로 결정적 테스트 가능.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from bushexa import fileio
from bushexa.data.timetable import (
    ValidationIssue,
    get_busroute_info,
    save_timetable,
    validate_timetable,
)
from bushexa.time_utils import Clock, KSTClock

logger = logging.getLogger("bushexa.services.timetable_editor")

# TimetableData 타입 별칭 (F04 §6)
TimetableData = dict[str, dict[str, list[str]]]  # weekday → departure → ["HH:MM", ...]


# ──────────────────────────────────────────────
# 예외 / 결과 타입
# ──────────────────────────────────────────────

class ValidationError(Exception):
    """시간표 검증 실패. issues 속성에 ValidationIssue 목록을 담는다."""

    def __init__(self, issues: list[ValidationIssue]) -> None:
        super().__init__(f"시간표 검증 실패 ({len(issues)}건): {issues[:3]}")
        self.issues = issues


@dataclass(frozen=True)
class RouteSummary:
    """노선 간략 정보 (busno 식별 가능한 최소 정보)."""
    busno: str
    departures: list[str]


@dataclass(frozen=True)
class SaveResult:
    """save() 성공 결과."""
    busno: str
    backup_path: Path | None  # 백업이 생성된 경우 해당 경로


# ──────────────────────────────────────────────
# TimetableEditor
# ──────────────────────────────────────────────

class TimetableEditor:
    """시간표 JSON 파일 편집 서비스.

    Parameters
    ----------
    dir:
        시간표 JSON 디렉터리 (예: data/timetable/).
    backup_dir:
        편집 전 백업 디렉터리 (예: data/timetable_backup/).
    clock:
        ADR-008 시각 공급자. 기본은 KSTClock(). 테스트에서 FakeClock 주입.
    """

    def __init__(self, dir: Path, backup_dir: Path, *, clock: Clock | None = None) -> None:
        self._dir = Path(dir)
        self._backup_dir = Path(backup_dir)
        self._clock = clock if clock is not None else KSTClock()

    # ── 공개 API ───────────────────────────────

    def list_routes(self) -> list[RouteSummary]:
        """ROUTEID 상수에서 노선 목록을 반환 (get_busroute_info 재사용)."""
        busnos, departure_dict = get_busroute_info()
        return [RouteSummary(busno=bn, departures=departure_dict.get(bn, []))
                for bn in busnos]

    def load(self, busno: str) -> TimetableData:
        """self.dir/{busno}.json 을 읽어 TimetableData 를 반환."""
        path = self._dir / f"{busno}.json"
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def validate(self, data: TimetableData) -> list[ValidationIssue]:
        """P1 validate_timetable 에 위임. ValidationIssue 목록 반환."""
        return validate_timetable(data)

    def save(self, busno: str, data: TimetableData) -> SaveResult:
        """시간표를 검증 → 백업 → 원자적 저장.

        (1) validate(위임) — 위반 시 ValidationError 발생, 디스크 미변경.
        (2) 기존 파일 존재 시 backup_dir/{busno}.{timestamp}.json 백업.
        (3) save_timetable(validate=False)으로 원자적 저장.

        Raises
        ------
        ValidationError
            검증 실패. issues 속성에 상세 목록.
        """
        # (1) 검증 먼저 — 실패 시 디스크를 전혀 건드리지 않는다.
        issues = validate_timetable(data)
        if issues:
            raise ValidationError(issues)

        # (2) 기존 파일 백업
        source_path = self._dir / f"{busno}.json"
        backup_path: Path | None = None
        if source_path.exists():
            ts = self._clock.now().strftime("%Y%m%d-%H%M%S")
            backup_path = self._backup_dir / f"{busno}.{ts}.json"
            # 원본 바이트를 그대로 읽어 backup_dir에 원자적으로 복사.
            original_bytes = source_path.read_bytes()
            fileio.atomic_write_bytes(backup_path, original_bytes, logger=logger)

        # (3) 원자적 저장 (validate=False — 이미 위에서 검증 완료)
        save_timetable(busno, data, dir=self._dir, validate=False)

        return SaveResult(busno=busno, backup_path=backup_path)
