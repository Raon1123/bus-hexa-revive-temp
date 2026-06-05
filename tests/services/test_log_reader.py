"""W16 테스트: LogTailReader (F04 §4.6, AC-2, TP-015).

E-13 준수: 기대값은 임시 파일에 테스트가 직접 기록한 알려진 줄에서 도출.
구현 출력 베끼기 없음 — 각 줄의 내용은 테스트가 먼저 정의.

테스트 케이스:
- test_tail_returns_recent_lines_last_first: 10줄 파일 → tail(5)가 마지막 5줄을 최신순으로 반환
- test_tail_filters_by_level: INFO/ERROR 혼합 → level="ERROR" 시 ERROR 이상만
- test_tail_caps_lines_at_2000: lines=10**6 → 반환 길이 ≤ 2000 (DoS 상한)
- test_missing_log_file_returns_empty: 파일 없으면 예외 없이 빈 리스트
"""
from __future__ import annotations

from pathlib import Path

import pytest

from bushexa.services.log_reader import LOG_SOURCES, LogTailReader, STANDARD_LEVELS, _MAX_LINES

# logging_setup 포맷과 동일: "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
_FMT = "2026-06-01T08:{min:02d}:00+09:00 [bushexa.test] {level}: {msg}"


def _make_log_file(path: Path, lines: list[tuple[str, str]]) -> None:
    """(level, message) 리스트를 포맷에 맞춰 파일에 기록한다.

    E-13: 테스트가 직접 내용을 결정 → 기대값이 구현에서 독립.
    """
    with path.open("w", encoding="utf-8") as f:
        for i, (level, msg) in enumerate(lines):
            f.write(_FMT.format(min=i, level=level, msg=msg) + "\n")


# ─────────────────────────────────────────────────────────────────────────────
# test_tail_returns_recent_lines_last_first
# ─────────────────────────────────────────────────────────────────────────────

def test_tail_returns_recent_lines_last_first(tmp_path):
    """임시 파일 10줄 기록 후 tail(5)가 마지막 5줄을 최신순으로 반환한다.

    'tail(5)'는 파일 끝에서 5줄을 가져온다. 마지막 줄(9번, msg=line-9)이 index 0.
    기대값: ["line-9", "line-8", "line-7", "line-6", "line-5"] — 구현 독립.
    """
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    log_file = log_dir / "bushexa.log"

    # 10줄 기록: msg = "line-0" ... "line-9"
    _make_log_file(log_file, [("INFO", f"line-{i}") for i in range(10)])

    reader = LogTailReader(log_dir)
    result = reader.tail(lines=5)

    assert len(result) == 5
    # 최신(마지막 기록된 줄)이 index 0
    assert result[0].message == "line-9"
    assert result[1].message == "line-8"
    assert result[2].message == "line-7"
    assert result[3].message == "line-6"
    assert result[4].message == "line-5"


# ─────────────────────────────────────────────────────────────────────────────
# test_tail_filters_by_level
# ─────────────────────────────────────────────────────────────────────────────

def test_tail_filters_by_level(tmp_path):
    """INFO/ERROR 혼합 파일에서 level='ERROR'가 ERROR 이상 라인만 반환한다.

    기대값: ERROR 줄 2건 + CRITICAL 줄 1건 = 3건 (INFO 줄 3건 제외).
    """
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    log_file = log_dir / "bushexa.log"

    # 알려진 시퀀스: INFO, ERROR, INFO, CRITICAL, INFO, ERROR
    known_lines = [
        ("INFO",     "info-0"),
        ("ERROR",    "error-1"),
        ("INFO",     "info-2"),
        ("CRITICAL", "crit-3"),
        ("INFO",     "info-4"),
        ("ERROR",    "error-5"),
    ]
    _make_log_file(log_file, known_lines)

    reader = LogTailReader(log_dir)
    result = reader.tail(level="ERROR")

    # ERROR 이상: ERROR(×2) + CRITICAL(×1) = 3건
    assert len(result) == 3
    # 최신순: error-5 먼저
    messages = [ln.message for ln in result]
    assert messages[0] == "error-5"
    assert messages[1] == "crit-3"
    assert messages[2] == "error-1"


# ─────────────────────────────────────────────────────────────────────────────
# test_tail_caps_lines_at_2000
# ─────────────────────────────────────────────────────────────────────────────

def test_tail_caps_lines_at_2000(tmp_path):
    """lines=10**6 요청 시에도 반환 길이가 2000 이하다 (DoS / 메모리 상한).

    파일에 2050줄을 기록해 cap이 실질적으로 작동하는지 검증한다.
    파일 줄 수 < cap인 경우에는 상한이 자연스럽게 충족되므로, 반드시 cap을 초과하는
    파일이 필요하다.
    """
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    log_file = log_dir / "bushexa.log"

    # 2050줄 기록 (2000을 초과)
    with log_file.open("w", encoding="utf-8") as f:
        for i in range(2050):
            f.write(f"2026-06-01T08:00:00+09:00 [t] INFO: line-{i}\n")

    reader = LogTailReader(log_dir)
    result = reader.tail(lines=10 ** 6)

    assert len(result) <= _MAX_LINES  # ≤ 2000
    assert len(result) == _MAX_LINES  # 파일에 2050줄 있으므로 딱 2000


# ─────────────────────────────────────────────────────────────────────────────
# test_missing_log_file_returns_empty
# ─────────────────────────────────────────────────────────────────────────────

def test_missing_log_file_returns_empty(tmp_path):
    """로그 파일이 없을 때 예외 없이 빈 리스트를 반환한다."""
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    # bushexa.log 파일을 생성하지 않음

    reader = LogTailReader(log_dir)
    result = reader.tail()

    assert result == []


# ─────────────────────────────────────────────────────────────────────────────
# test_tail_level_filter_keeps_unknown_continuation_lines
# 2026-06-05 리뷰 #10 회귀 테스트: UNKNOWN(파싱 실패) 라인이 level 필터에서 살아남는지.
# ─────────────────────────────────────────────────────────────────────────────

def test_tail_level_filter_keeps_unknown_continuation_lines(tmp_path):
    """level='ERROR' 필터 시 트레이스백 연속 라인(UNKNOWN)이 제거되지 않아야 한다.

    시나리오: ERROR 라인 다음에 트레이스백 연속 라인 2개가 오는 로그 파일.
    tail(level='ERROR')는 ERROR 라인과 연속 라인(UNKNOWN) 모두를 반환해야 한다.

    연속 라인을 떨어뜨리면 스택트레이스가 통째로 사라지는 문제 방지
    (2026-06-05 리뷰 #10 회귀 테스트).

    tail()는 최신 우선(reversed)이므로 파일 끝의 연속 라인이 index 0/1,
    ERROR 라인이 index 2에 위치한다.
    """
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    log_file = log_dir / "bushexa.log"

    # 파일에 직접 쓴다 — _FMT 헬퍼는 정규 라인 전용이므로 연속 라인은 raw로 기록.
    log_content = (
        '2026-06-05T03:00:00+09:00 [bushexa.crawler] ERROR: something exploded\n'
        '  File "/app/bushexa/crawler/daemon.py", line 42, in poll\n'
        'ValueError: boom\n'
    )
    log_file.write_text(log_content, encoding="utf-8")

    reader = LogTailReader(log_dir)
    result = reader.tail(level="ERROR")

    # 3줄 모두 반환 (ERROR 1줄 + UNKNOWN 2줄)
    assert len(result) == 3, f"Expected 3 lines (1 ERROR + 2 UNKNOWN), got {len(result)}"

    # tail()는 최신 우선 — 연속 라인이 먼저, ERROR가 마지막
    assert result[0].level == "UNKNOWN"
    assert "ValueError: boom" in result[0].message
    assert result[1].level == "UNKNOWN"
    assert 'File "/app/bushexa/crawler/daemon.py"' in result[1].message
    assert result[2].level == "ERROR"
    assert result[2].message == "something exploded"


# ─────────────────────────────────────────────────────────────────────────────
# test_log_sources_sanity
# LOG_SOURCES 키·값 고정 문자열 sanity 체크.
# ─────────────────────────────────────────────────────────────────────────────

def test_log_sources_sanity():
    """LOG_SOURCES가 4개의 고정 키와 파일명을 갖는지 sanity 체크한다.

    이 매핑은 관리자 로그 뷰 소스 선택의 화이트리스트이자 CLI 역할별 로그 파일명 계약이다.
    값이 변경되면 supervisord conf, CLI setup_logging 호출, 관리자 UI가 모두 함께
    변경돼야 하므로 의도치 않은 수정을 즉시 감지하기 위해 고정값을 명시한다.
    """
    assert set(LOG_SOURCES.keys()) == {"web", "crawl", "arrival", "cache"}
    assert LOG_SOURCES["web"] == "bushexa.log"
    assert LOG_SOURCES["crawl"] == "bushexa-crawl.log"
    assert LOG_SOURCES["arrival"] == "bushexa-arrival.log"
    assert LOG_SOURCES["cache"] == "bushexa-cache.log"
