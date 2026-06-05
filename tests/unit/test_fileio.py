"""W12 fileio 감사 로깅 검증 (ADR-012).

PM-002 T-1: ``bushexa.*`` 로거는 setup_logging 적용 시 propagate=False이므로 caplog 대신
자체 핸들러를 직접 부착해 캡처한다. 기대값(생성/수정 동사, 무손상, 내용 미기록)은 구현과
독립적으로 도출(E-13).
"""
from __future__ import annotations

import json
import logging

import pytest

from bushexa import fileio


class _Capture(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def _attach():
    log = logging.getLogger("bushexa.fileio")
    cap = _Capture()
    log.addHandler(cap)
    log.setLevel(logging.INFO)
    return log, cap


def test_create_logs_created(tmp_path):
    """새 경로에 쓰면 파일이 생기고 'created' INFO가 정확히 1줄 남는지(사용자 '생성' 요구)."""
    log, cap = _attach()
    try:
        p = tmp_path / "sub" / "data.json"
        fileio.atomic_write_json(p, {"a": 1})
    finally:
        log.removeHandler(cap)

    assert json.loads(p.read_text(encoding="utf-8")) == {"a": 1}
    msgs = [r.getMessage() for r in cap.records]
    assert sum("created" in m for m in msgs) == 1
    assert all("modified" not in m for m in msgs)


def test_overwrite_logs_modified(tmp_path):
    """기존 경로에 다시 쓰면 동사가 'modified'로 바뀌고 내용이 새 값으로 교체되는지('수정' 구분)."""
    p = tmp_path / "data.json"
    fileio.atomic_write_json(p, {"v": 1})

    log, cap = _attach()
    try:
        fileio.atomic_write_json(p, {"v": 2})
    finally:
        log.removeHandler(cap)

    assert json.loads(p.read_text(encoding="utf-8")) == {"v": 2}
    msgs = [r.getMessage() for r in cap.records]
    assert sum("modified" in m for m in msgs) == 1
    assert all("created" not in m for m in msgs)


def test_atomic_no_partial_on_failure(tmp_path):
    """직렬화 불가 객체(set)를 주면 예외가 나고 기존 파일이 손상되지 않으며 tmp 잔여물이 없는지(원자성)."""
    p = tmp_path / "data.json"
    fileio.atomic_write_json(p, {"ok": True})

    with pytest.raises(TypeError):
        fileio.atomic_write_json(p, {"bad": {1, 2, 3}})

    assert json.loads(p.read_text(encoding="utf-8")) == {"ok": True}
    assert list(tmp_path.glob("*.tmp.*")) == []


def test_content_not_logged(tmp_path):
    """로그 메시지에 파일 내용이 포함되지 않고 경로·크기만 남는지(시크릿 유출 방지)."""
    log, cap = _attach()
    try:
        fileio.atomic_write_text(tmp_path / "secret.txt", "SUPERSECRETVALUE")
    finally:
        log.removeHandler(cap)

    assert cap.records, "감사 로그가 비어 있으면 안 된다"
    for r in cap.records:
        assert "SUPERSECRETVALUE" not in r.getMessage()
