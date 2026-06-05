"""govtrack 데몬 상태 writer/reader (W6).

마지막 사이클 결과를 상태파일(JSON)에 누적해, 관리자(F04)가 데몬 건강도를 읽을 수 있게 한다.
``consecutive_failures``/``last_success_at``으로 '데몬 미동작'을 노출한다(F04 AC-G1/G2).

성공 사이클 정의: ``committed`` AND ``total_errors == 0`` (정상 commit + 오류 없음). 조용한
사이클(통과 0·오류 0)도 성공으로 보아 연속 실패 카운터를 리셋한다. 실패면 직전 카운터에서 +1.
쓰기는 ``fileio.atomic_write_json``(ADR-012) 경유.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from bushexa import fileio

logger = logging.getLogger("bushexa.services.govtrack_status")


@dataclass(frozen=True)
class GovtrackStatus:
    cycle_started_at: str
    total_inserts: int
    total_errors: int
    committed: bool
    route_breakdown: dict[str, int]
    consecutive_failures: int
    last_success_at: str | None


def _iso(value) -> str:
    return value.isoformat() if isinstance(value, datetime) else str(value)


def _load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("govtrack 상태 로드 실패(%s), 빈 이력으로 시작: %s", path, exc)
        return []
    return data if isinstance(data, list) else []


def _to_status(rec: dict) -> GovtrackStatus:
    return GovtrackStatus(
        cycle_started_at=rec["cycle_started_at"],
        total_inserts=rec["total_inserts"],
        total_errors=rec["total_errors"],
        committed=rec["committed"],
        route_breakdown=dict(rec.get("route_breakdown", {})),
        consecutive_failures=rec["consecutive_failures"],
        last_success_at=rec.get("last_success_at"),
    )


class GovtrackStatusWriter:
    def __init__(self, path, *, max_history: int = 200):
        self.path = Path(path)
        self.max_history = max_history

    def write(self, cyc) -> None:
        history = _load(self.path)
        prev = history[-1] if history else None
        success = bool(cyc.committed) and cyc.total_errors == 0
        if success:
            consecutive = 0
            last_success = _iso(cyc.cycle_started_at)
        else:
            consecutive = (prev["consecutive_failures"] if prev else 0) + 1
            last_success = prev["last_success_at"] if prev else None

        record = {
            "cycle_started_at": _iso(cyc.cycle_started_at),
            "total_inserts": cyc.total_inserts,
            "total_errors": cyc.total_errors,
            "committed": bool(cyc.committed),
            "route_breakdown": {rid: s.inserts for rid, s in cyc.route_results.items()},
            "consecutive_failures": consecutive,
            "last_success_at": last_success,
        }
        history.append(record)
        if len(history) > self.max_history:
            history = history[-self.max_history:]
        fileio.atomic_write_json(self.path, history)


class GovtrackStatusReader:
    def __init__(self, path):
        self.path = Path(path)

    def latest(self) -> GovtrackStatus | None:
        history = _load(self.path)
        return _to_status(history[-1]) if history else None

    def history(self, limit: int = 50) -> list[GovtrackStatus]:
        """최근 사이클을 최신순(역순)으로 최대 limit개 반환."""
        history = _load(self.path)
        return [_to_status(r) for r in reversed(history[-limit:])]
