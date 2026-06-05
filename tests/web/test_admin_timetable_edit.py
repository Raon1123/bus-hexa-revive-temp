"""W13a 테스트: admin timetable editor (F04, TP-009).

E-13 준수: 기대값은 구현 독립 출처에서 온다.
- test_edit_view: TP-009 §2 #2 "3개 weekday 탭(평일/토/일·공휴일)".
- test_save: "저장 후 디스크 JSON 변경 + backup_dir에 백업 생성"(TP-009 §2 #4, AC-2 spec).
- test_invalid_save_422: "잘못된 weekday 키 → 422 + 원본 보존"(TP-009 §6, validate_timetable 계약).

타임테이블 dir은 BUSHEXA_TIMETABLE_DIR로 tmp에 격리하고 713.json을 시드한다
(공개 라우트와 동일 dir; admin.py _get_timetable_editor가 timetable_dir() 사용).
CSRF: 세션에 토큰 주입 + 폼 필드로 동일 토큰 전송(app.py before_request 검증).
"""
from __future__ import annotations

import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from bushexa.config import AppConfig
from bushexa.web.app import create_app

_KST = ZoneInfo("Asia/Seoul")
_CSRF = "test-csrf-token"

# 알려진 노선 713의 시드 시간표 (weekday 키 "0"/"1"/"2", departure 명촌/UNIST).
_SEED_713: dict = {
    "0": {"명촌": ["06:00", "07:00"], "UNIST": ["08:00"]},
    "1": {"명촌": ["09:00"], "UNIST": ["10:00"]},
    "2": {"명촌": ["11:00"], "UNIST": ["12:00"]},
}


@pytest.fixture
def tt_app(tmp_path, monkeypatch):
    """BUSHEXA_TIMETABLE_DIR을 tmp로 격리하고 713.json을 시드한 Flask app."""
    tdir = tmp_path / "timetable"
    tdir.mkdir()
    (tdir / "713.json").write_text(
        json.dumps(_SEED_713, ensure_ascii=False, indent=4), encoding="utf-8"
    )
    monkeypatch.setenv("BUSHEXA_TIMETABLE_DIR", str(tdir))

    config = AppConfig(
        api_key="test-api-key",
        database_url="sqlite:///:memory:",
        session_secret="test-secret",
        manager_password_path=tmp_path / "manager_password.txt",
        data_dir=tmp_path / "data",
        tz=_KST,
        log_level="DEBUG",
        log_dir=tmp_path / "logs",
    )
    app = create_app(config)
    return app, tdir


@pytest.fixture
def authed_client(tt_app):
    """로그인 + CSRF 토큰이 주입된 test_client."""
    app, tdir = tt_app
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["admin_authed"] = True
        sess["csrf_token"] = _CSRF
    return client, tdir


# ──────────────────────────────────────────────────
# AC-1: 편집 화면 200 + 3개 weekday 탭
# ──────────────────────────────────────────────────

def test_edit_view(authed_client):
    """GET /admin/timetable/713 → 200 + 평일/토/일 탭 (TP-009 §2 #2, AC-1)."""
    client, _ = authed_client
    resp = client.get("/admin/timetable/713")
    assert resp.status_code == 200, f"expected 200, got {resp.status_code}"
    html = resp.data.decode("utf-8")
    # 3개 weekday 탭 라벨 (독립 출처: TP-009 §2 #2).
    assert "평일" in html
    assert "토요일" in html
    assert "일·공휴일" in html
    # role="tab" 3개 (탭 구조).
    assert html.count('role="tab"') == 3, "weekday 탭 3개여야 함"


# ──────────────────────────────────────────────────
# AC-2: 저장 → 디스크 JSON 변경 + 백업 생성
# ──────────────────────────────────────────────────

def test_save(authed_client):
    """시간 1건 수정 POST → 디스크 JSON 갱신 + 백업 생성 (TP-009 §2 #4, AC-2).

    독립 출처: 저장 전후 713.json 내용이 달라지고, timetable_backup/에 713.* 백업 1건.
    """
    client, tdir = authed_client
    src = tdir / "713.json"
    before = json.loads(src.read_text(encoding="utf-8"))
    assert before == _SEED_713  # 시드 확인

    # 평일 명촌 출발에 새 시각 1건 추가(13:00). 나머지는 시드 그대로 전송.
    resp = client.post(
        "/admin/timetable/713",
        data={
            "csrf_token": _CSRF,
            "weekdays": "0 1 2",
            "departures__0": "명촌 UNIST",
            "departures__1": "명촌 UNIST",
            "departures__2": "명촌 UNIST",
            "times__0__명촌": "06:00\n07:00\n13:00",
            "times__0__UNIST": "08:00",
            "times__1__명촌": "09:00",
            "times__1__UNIST": "10:00",
            "times__2__명촌": "11:00",
            "times__2__UNIST": "12:00",
        },
        follow_redirects=False,
    )
    assert resp.status_code in (200, 302), f"save expected 200/302, got {resp.status_code}"

    # 디스크 JSON 변경됨.
    after = json.loads(src.read_text(encoding="utf-8"))
    assert after != before, "디스크 JSON이 갱신되어야 함"
    assert "13:00" in after["0"]["명촌"], "추가한 시각이 반영되어야 함"

    # 백업 생성됨 (timetable_backup/713.{ts}.json).
    bdir = tdir.parent / "timetable_backup"
    backups = list(bdir.glob("713.*.json"))
    assert len(backups) >= 1, f"백업이 생성되어야 함, found {backups}"
    # 백업 내용 == 저장 직전 원본(데이터 보호).
    backed_up = json.loads(backups[0].read_text(encoding="utf-8"))
    assert backed_up == before, "백업은 저장 직전 원본이어야 함"


# ──────────────────────────────────────────────────
# test_invalid_save_422: 잘못된 weekday 키 → 422 + 원본 보존
# ──────────────────────────────────────────────────

def test_invalid_save_422(authed_client):
    """잘못된 weekday 키('월요일') 저장 → 422 + 디스크 원본 미변경 (TP-009 §6).

    독립 출처: validate_timetable의 _VALID_WEEKDAYS={"0","1","2"} 계약 →
    비숫자 키는 bad_weekday로 거부됨.
    """
    client, tdir = authed_client
    src = tdir / "713.json"
    before = src.read_bytes()

    resp = client.post(
        "/admin/timetable/713",
        data={
            "csrf_token": _CSRF,
            "weekdays": "월요일",          # 잘못된 weekday 키
            "departures__월요일": "명촌",
            "times__월요일__명촌": "06:00",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 422, f"invalid weekday should be 422, got {resp.status_code}"

    # 디스크 원본 무손상.
    assert src.read_bytes() == before, "검증 실패 시 디스크 원본이 보존되어야 함"
