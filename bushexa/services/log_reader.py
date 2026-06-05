"""W16 — 애플리케이션 로그 tail 리더 (F04 §4.6, TP-015).

설정된 log_dir 안의 단일 파일(bushexa.log)만 읽는 read-only tail 리더.
경로는 생성자에서 고정 — 사용자 입력으로 파일 경로를 받지 않는다(S3 path traversal 방지).

tail(lines, level) 계약:
- 파일 끝에서 최대 lines 줄을 역순(최신 우선)으로 읽어 반환.
- lines 상한은 2000 (DoS / 메모리 보호, S9).
- level 이상(severity >= requested level)만 포함 (None이면 전체).
- 파일 부재 시 빈 리스트 반환 (FileNotFoundError 전파 금지).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

# 표준 레벨 집합 (화이트리스트) — 검증에 사용
STANDARD_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}

# 레벨 순서 (낮은 숫자 = 낮은 심각도)
_LEVEL_ORDER = {
    "DEBUG": 10,
    "INFO": 20,
    "WARNING": 30,
    "ERROR": 40,
    "CRITICAL": 50,
}

# logging_setup.py LOG_FORMAT = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
# 예: "2026-06-01T08:30:00+09:00 [bushexa.crawler] INFO: some message"
_LINE_RE = re.compile(
    r"^(?P<ts>\S+)\s+\[(?P<logger>[^\]]+)\]\s+(?P<level>[A-Z]+):\s*(?P<message>.*)$"
)

_MAX_LINES = 2000


@dataclass(frozen=True)
class LogLine:
    ts: str       # KST ISO 타임스탬프 (파싱 실패 시 원문)
    logger: str   # 예: "bushexa.crawler"
    level: str    # "INFO" | "WARNING" | "ERROR" ...
    message: str
    raw: str      # 원본 라인


def _parse_line(raw: str) -> LogLine:
    """원본 라인을 LogLine으로 파싱. 형식 불일치 시 기본값으로 채운다."""
    m = _LINE_RE.match(raw.rstrip())
    if m:
        return LogLine(
            ts=m.group("ts"),
            logger=m.group("logger"),
            level=m.group("level"),
            message=m.group("message"),
            raw=raw,
        )
    # 파싱 실패: 원본을 그대로 보존 (level 필터에서 걸리지 않도록 UNKNOWN 처리)
    return LogLine(ts="", logger="", level="UNKNOWN", message=raw.rstrip(), raw=raw)


def _level_value(level: str) -> int:
    return _LEVEL_ORDER.get(level.upper(), 0)


class LogTailReader:
    """설정된 로그 디렉토리 안의 단일 파일만 읽는 read-only tail 리더.

    파일 경로는 생성자에서 ``log_dir / filename``으로 고정된다.
    외부에서 경로를 주입할 수 없으므로 path traversal이 원천 차단된다.
    """

    def __init__(self, log_dir: Path, filename: str = "bushexa.log") -> None:
        self._path = Path(log_dir) / filename

    @property
    def path(self) -> Path:
        """실제 읽는 파일 경로 (테스트 검증 용도)."""
        return self._path

    def tail(self, lines: int = 200, level: str | None = None) -> list[LogLine]:
        """파일 끝에서 최대 ``lines``줄을 역순(최신 우선)으로 읽어 파싱·필터.

        Args:
            lines: 반환할 최대 줄 수. 2000이 상한.
            level: None이면 전체 반환. 표준 레벨 문자열이면 해당 레벨 이상만 반환.

        Returns:
            파싱된 LogLine 리스트 (최신 라인이 index 0).
            파일 부재 시 빈 리스트.
        """
        # 상한 강제 (S9 DoS 방어)
        cap = min(int(lines), _MAX_LINES)

        try:
            raw_lines = self._path.read_text(encoding="utf-8", errors="replace").splitlines()
        except FileNotFoundError:
            return []
        except OSError:
            return []

        # 파일 끝에서 cap 줄 취득 후 역순(최신 우선)
        tail_raw = raw_lines[-cap:] if len(raw_lines) > cap else raw_lines
        result: list[LogLine] = [_parse_line(ln) for ln in reversed(tail_raw)]

        # level 필터 (None이면 전체)
        if level is not None:
            min_val = _level_value(level)
            result = [ln for ln in result if _level_value(ln.level) >= min_val]

        return result
