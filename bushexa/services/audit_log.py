"""관리자 변경 감사 로그 서비스 (Feature 5).

모든 관리자 뮤테이션에서 호출해 append-only JSON 리스트로 기록한다.
max_entries 이상이면 가장 오래된 항목부터 제거(최신 N건 유지).
쓰기는 fileio.atomic_write_json(ADR-012) 경유.

용법:
    audit = AuditLog(path)
    audit.record("holiday.add", date="20260101", actor_ip="127.0.0.1")
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from bushexa import fileio
from bushexa.time_utils import KST as _KST  # ADR-008: KST 단일 출처

logger = logging.getLogger("bushexa.services.audit_log")
_DEFAULT_MAX = 1000


def default_audit_path(data_dir) -> Path:
    return Path(data_dir) / "audit_log.json"


def _load(path: Path) -> list[dict]:
    return fileio.read_json(path, [], expect=list, warn_label="audit 로그", logger=logger)


class AuditLog:
    """관리자 뮤테이션 감사 로그. append-only, size-capped JSON list."""

    def __init__(self, path, *, max_entries: int = _DEFAULT_MAX, clock=None):
        self.path = Path(path)
        self.max_entries = max_entries
        self._clock = clock  # KSTClock 또는 테스트용 대역; None이면 datetime.now(KST)

    def _now_iso(self) -> str:
        if self._clock is not None:
            return self._clock.now().isoformat()
        return datetime.now(_KST).isoformat()

    def record(self, action: str, *, actor_ip: str | None = None, **details) -> None:
        """감사 항목을 1건 추가한다. 실패해도 예외를 전파하지 않는다 (best-effort).

        #7: locked_update_json 경유로 동시 기록 유실 방지(fcntl.flock 크로스 프로세스 잠금).

        Parameters
        ----------
        action: str
            예) "holiday.add", "via.save", "backup.restore"
        actor_ip: str | None
            request.remote_addr (없으면 None).
        **details:
            추가 컨텍스트 (date, busno, edition_id 등). 직렬화 가능해야 한다.
        """
        try:
            entry = {
                "ts": self._now_iso(),
                "action": action,
                "actor_ip": actor_ip,
                **{k: v for k, v in details.items()},
            }
            max_entries = self.max_entries

            def _mutate(entries: list) -> list:
                entries.append(entry)
                if len(entries) > max_entries:
                    entries = entries[-max_entries:]
                return entries

            # default=[] → 파일 부재·파손 시 빈 리스트로 시작 (크로스 프로세스 잠금 #7)
            fileio.locked_update_json(self.path, _mutate, default=[])
        except Exception as exc:
            logger.error("audit 기록 실패 (action=%s): %s", action, exc, exc_info=True)

    def load(self, *, limit: int = 500) -> list[dict]:
        """최신순(역순)으로 최대 limit건 반환."""
        entries = _load(self.path)
        return list(reversed(entries[-limit:]))
