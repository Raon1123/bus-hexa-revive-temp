"""원자적 파일 쓰기 + 생성/수정 감사 로깅 (ADR-012).

bushexa 내에서 디스크 파일을 쓰는 **유일한 합법 경로**다. 직접 ``open(..., "w")`` /
``json.dump(..., 파일)`` / ``Path.write_*`` 대신 이 헬퍼를 사용한다. 모든 쓰기는
임시파일 → fsync → 원자적 rename으로 손상을 막고, 생성/수정을 구분해 INFO 로그를
``bushexa.fileio`` 로거(= ``logs/bushexa.log`` sink, 관리자 로그 뷰어 F04 §4.6이 읽음)에 남긴다.
파일 **내용은 절대 로그하지 않는다**(시크릿 유출 방지).
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

_DEFAULT_LOGGER = logging.getLogger("bushexa.fileio")


def _atomic_write(path: Path, data: bytes, *, logger: logging.Logger | None = None) -> None:
    """``data``를 ``path``에 원자적으로 쓰고 생성/수정 여부를 INFO 로그로 남긴다."""
    log = logger or _DEFAULT_LOGGER
    path = Path(path)
    verb = "modified" if path.exists() else "created"  # 쓰기 '직전' 판정 (ADR-012)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp.{os.getpid()}")
    try:
        with open(tmp, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)  # 원자적 rename
    except BaseException:
        # 실패 시 tmp만 정리 — 기존 path 내용은 건드리지 않는다(원자성).
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
        raise
    # 경로·크기·동사만 기록한다. 내용 미기록(ADR-012 / ADR-009 시크릿 보호).
    log.info("file %s: %s (%dB)", verb, path.resolve(), len(data))


def atomic_write_bytes(path, data: bytes, *, logger: logging.Logger | None = None) -> None:
    _atomic_write(Path(path), data, logger=logger)


def atomic_write_text(path, text: str, *, encoding: str = "utf-8",
                      logger: logging.Logger | None = None) -> None:
    _atomic_write(Path(path), text.encode(encoding), logger=logger)


def atomic_write_json(path, obj: Any, *, ensure_ascii: bool = False, indent: int | None = None,
                      logger: logging.Logger | None = None) -> None:
    # 직렬화 실패(예: set)는 파일을 만들기 '전'에 발생 → 기존 파일 무손상.
    text = json.dumps(obj, ensure_ascii=ensure_ascii, indent=indent)
    _atomic_write(Path(path), text.encode("utf-8"), logger=logger)
