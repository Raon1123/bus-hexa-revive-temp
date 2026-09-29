"""arrival 데몬 상태 writer/reader (Feature 4 — govtrack_status.py 대칭 구현).

각 폴 사이클의 건강도(마지막 폴 시각, 마지막 성공, 연속 오류 수, 정류장 성공 수)를
상태파일(JSON)에 기록한다. govtrack_status.py와 동일한 구조: list of records, trim to max_history.

쓰기는 fileio.atomic_write_json(ADR-012) 경유.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from bushexa import fileio
from bushexa.redact import redact_secrets

logger = logging.getLogger("bushexa.services.arrival_status")


@dataclass(frozen=True)
class ArrivalStatus:
    cycle_started_at: str       # ISO8601 KST
    stops_ok: int               # 이번 사이클에서 성공한 정류장 수
    stops_total: int            # 폴링 대상 전체 정류장 수
    consecutive_errors: int     # 연속 실패 사이클 수 (성공이면 0으로 리셋)
    last_success_at: str | None  # 마지막 성공 사이클 시작 ISO8601
    last_error_msg: str | None   # 마지막 오류 메시지 (없으면 None)


def _iso(value) -> str:
    return value.isoformat() if isinstance(value, datetime) else str(value)


def _load(path: Path) -> list[dict]:
    return fileio.read_json(path, [], expect=list, warn_label="arrival 상태", logger=logger)


def _to_status(rec: dict) -> ArrivalStatus:
    # .get + 기본값: 구버전/부분 스키마 상태파일에서도 관리자 페이지가 500 나지 않게 방어
    return ArrivalStatus(
        cycle_started_at=rec.get("cycle_started_at", ""),
        stops_ok=rec.get("stops_ok", 0),
        stops_total=rec.get("stops_total", 0),
        consecutive_errors=rec.get("consecutive_errors", 0),
        last_success_at=rec.get("last_success_at"),
        last_error_msg=rec.get("last_error_msg"),
    )


class ArrivalStatusWriter:
    """매 사이클 결과를 status 파일에 append-and-trim으로 기록한다."""

    def __init__(self, path, *, max_history: int = 200):
        self.path = Path(path)
        self.max_history = max_history

    def write(self, *, cycle_started_at, stops_ok: int, stops_total: int,
              last_error_msg: str | None = None) -> None:
        """사이클 결과를 기록한다.

        성공 정의: stops_ok == stops_total (모든 정류장 성공).
        부분 실패여도 consecutive_errors는 1 증가한다.
        """
        history = _load(self.path)
        prev = history[-1] if history else None

        success = stops_ok == stops_total
        if success:
            consecutive = 0
            last_success = _iso(cycle_started_at)
        else:
            consecutive = (prev.get("consecutive_errors", 0) if prev else 0) + 1
            last_success = prev.get("last_success_at") if prev else None

        record = {
            "cycle_started_at": _iso(cycle_started_at),
            "stops_ok": stops_ok,
            "stops_total": stops_total,
            "consecutive_errors": consecutive,
            "last_success_at": last_success,
            # PM-016: 예외 문자열에 요청 URL(serviceKey=…)이 섞일 수 있어 저장 전 가림.
            "last_error_msg": redact_secrets(last_error_msg) if last_error_msg else last_error_msg,
        }
        history.append(record)
        if len(history) > self.max_history:
            history = history[-self.max_history:]
        fileio.atomic_write_json(self.path, history)


class ArrivalStatusReader:
    """status 파일에서 최신 및 이력을 읽는다."""

    def __init__(self, path):
        self.path = Path(path)

    def latest(self) -> ArrivalStatus | None:
        history = _load(self.path)
        return _to_status(history[-1]) if history else None

    def history(self, limit: int = 50) -> list[ArrivalStatus]:
        """최신순(역순)으로 최대 limit개 반환."""
        history = _load(self.path)
        return [_to_status(r) for r in reversed(history[-limit:])]
