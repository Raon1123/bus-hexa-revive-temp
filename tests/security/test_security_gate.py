"""P5 W1 보안 게이트 테스트 (S-finding 봉인 검증).

각 테스트는 P4 보안 감사 잔여 medium 항목의 회귀 방지 목적이다.
E-13 준수: 기대값은 spec/hand-calc 독립 출처, 구현 출력 복사 금지.
"""
from __future__ import annotations

import os
import stat
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

_KST = ZoneInfo("Asia/Seoul")

# ─────────────────────────────────────────────────────────────────
# S7 — 코드/compose에 평문 비밀번호가 0건이어야 한다
# ─────────────────────────────────────────────────────────────────

def test_no_plaintext_secret():
    """코드/compose에 평문 비밀번호가 0건이어야 한다 (S7).

    WhenMyBusRun: legacy DB 평문 비밀번호. 다음에서 0회 등장해야 한다:
      - bushexa/ .py 소스
      - docker/ 디렉터리(있으면): *.yaml, *.yml, Dockerfile  (E-9 — compose/Dockerfile 평문 가드)
      - 루트 .env.example (있으면)
    """
    SECRET = "WhenMyBusRun"
    project_root = Path(__file__).parent.parent.parent  # bus-hexa-revive-temp/

    matches: list[str] = []

    def _scan(path: Path) -> None:
        text = path.read_text(encoding="utf-8", errors="replace")
        if SECRET in text:
            matches.append(str(path))

    # bushexa/ .py 소스 스캔
    bushexa_dir = project_root / "bushexa"
    for py_file in bushexa_dir.rglob("*.py"):
        _scan(py_file)

    # docker/ 디렉터리: 존재하면 compose YAML + Dockerfile 스캔, 없으면 건너뜀
    docker_dir = project_root / "docker"
    if docker_dir.is_dir():
        for pattern in ("*.yaml", "*.yml", "Dockerfile"):
            for f in docker_dir.rglob(pattern):
                _scan(f)

    # 루트 .env.example: 존재하면 스캔
    env_example = project_root / ".env.example"
    if env_example.is_file():
        _scan(env_example)

    assert matches == [], (
        f"평문 비밀번호 '{SECRET}'이 소스에서 발견됨 (S7 위반): {matches}"
    )


# ─────────────────────────────────────────────────────────────────
# S2 — 비로그인 admin 접근은 차단(302/401)
# ─────────────────────────────────────────────────────────────────

def _make_test_app(tmp_path: Path):
    """테스트용 Flask app (비밀번호 파일 있는 상태)."""
    from bushexa.config import AppConfig
    from bushexa.web.app import create_app

    pw_path = tmp_path / "manager_password.txt"
    pw_path.write_text("test-password-1234")  # legacy 평문 — verify()가 수락함
    config = AppConfig(
        api_key="test-api-key",
        database_url="sqlite:///:memory:",
        session_secret="test-session-secret",
        manager_password_path=pw_path,
        data_dir=tmp_path / "data",
        tz=_KST,
        log_level="DEBUG",
        log_dir=tmp_path / "logs",
    )
    return create_app(config)


def test_admin_routes_protected(tmp_path):
    """비로그인 admin 접근은 차단(302/401) (S2).

    /admin/login 은 공개 접근 허용(exempt). 나머지 보호 라우트는 302 또는 401 응답이어야 한다.
    독립 출처: F04 §7 AC-A1, W10 AC-1.
    """
    app = _make_test_app(tmp_path)
    client = app.test_client()

    # /admin/login 은 공개 접근 — exempt
    resp = client.get("/admin/login")
    assert resp.status_code == 200, (
        f"/admin/login은 공개 접근이어야 하나 {resp.status_code}"
    )

    # 보호 라우트: 비로그인 상태에서 302 또는 401이어야 한다
    protected_routes = [
        "/admin/",
        "/admin/data",
        "/admin/logs",
        "/admin/govtrack/status",
    ]
    for route in protected_routes:
        resp = client.get(route)
        assert resp.status_code in (302, 401), (
            f"{route}: 비로그인 접근이 {resp.status_code}를 반환 — 302/401이어야 함 (S2)"
        )


# ─────────────────────────────────────────────────────────────────
# CSV formula injection — ' 무력화 (P1 §7 R4)
# ─────────────────────────────────────────────────────────────────

def test_csv_formula_injection():
    """CSV 셀 선두 수식문자는 ' 로 무력화되어야 한다 (formula injection, P1 §7 R4).

    기대값은 OWASP CSV-injection guidance 기반 hand-spec:
      =SUM(A1) → '=SUM(A1)
      +1       → '+1
      -1       → '-1
      @FOO     → '@FOO
      1234     → 1234  (변경 없음)
      None     → ""    (빈 문자열)

    _sanitize_csv_cell 헬퍼를 직접 단위 테스트한 뒤,
    end-to-end 통합 확인을 위해 repo.export_csv도 구동한다.
    """
    from bushexa.db.repo import _sanitize_csv_cell

    # ── 단위 테스트: hand-specified 기대값 (E-13 — impl 출력 복사 금지) ──
    assert _sanitize_csv_cell("=SUM(A1)") == "'=SUM(A1)", "= 선두 무력화 실패"
    assert _sanitize_csv_cell("+1") == "'+1", "+ 선두 무력화 실패"
    assert _sanitize_csv_cell("-1") == "'-1", "- 선두 무력화 실패"
    assert _sanitize_csv_cell("@FOO") == "'@FOO", "@ 선두 무력화 실패"
    assert _sanitize_csv_cell("\t=EXEC") == "'\t=EXEC", "탭 선두 무력화 실패"
    assert _sanitize_csv_cell("\r=EXEC") == "'\r=EXEC", "CR 선두 무력화 실패"

    # 무해한 값은 변경 없음
    assert _sanitize_csv_cell("1234") == "1234", "숫자 값은 변경 없어야 함"
    assert _sanitize_csv_cell("normal text") == "normal text", "일반 텍스트는 변경 없어야 함"
    assert _sanitize_csv_cell(None) == "", "None → 빈 문자열"
    assert _sanitize_csv_cell("") == "", "빈 문자열은 변경 없어야 함"

    # ── end-to-end 통합: export_csv가 수식값을 포함한 행을 sanitize 하는지 ──
    from bushexa.db.connection import create_connection
    from bushexa.db.repo import BusLogRepo, LogRow
    from bushexa.db.schema import create_schema

    conn = create_connection("sqlite:///:memory:")
    create_schema(conn)
    repo = BusLogRepo(conn)

    # stop_id에 수식 문자 삽입 — export_csv가 sanitize 해야 함
    repo.insert_batch([
        LogRow(
            idx="20260601_08:00:00",
            stop_id="=SUM(A1)",  # formula injection 시도
            route_id="R1",
            vehicle_no="V1",
        )
    ])

    chunks = list(repo.export_csv())
    # BOM + 헤더 + 1개 데이터 행 (총 3 chunks)
    assert chunks[0] == b"\xef\xbb\xbf"  # BOM 보존

    # 데이터 행(3번째 chunk)에서 '=SUM(A1) 가 있어야 한다
    data_line = chunks[2].decode("utf-8")
    assert "'=SUM(A1)" in data_line, (
        f"수식값이 무력화되어 있어야 하나 라인에서 발견 안됨: {data_line!r}"
    )
    # 원본 =SUM(A1) 는 선두에 ' 없이는 존재하면 안 됨
    assert "=SUM(A1)" not in data_line.replace("'=SUM(A1)", ""), (
        "원본 수식 문자열이 sanitize 없이 출력되면 안 됨"
    )
