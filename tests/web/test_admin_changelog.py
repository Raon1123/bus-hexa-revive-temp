"""관리자 변경이력(changelog) 관리 라우트 테스트.

/admin/changelog GET — 목록 + 추가 폼 (data_dir 없으면 static seed 폴백)
/admin/changelog/add POST — 항목 추가 (date=YYYY-MM-DD, description)
/admin/changelog/remove POST — index로 항목 제거
편집본은 <data_dir>/changelog.json 에 저장되고 info 페이지에 반영된다.

네트워크 없음. 파일 조작은 tmp_path 격리.
"""
from __future__ import annotations

import pytest
from zoneinfo import ZoneInfo

from bushexa.config import AppConfig
from bushexa.services.changelog_editor import ChangelogEditor, default_changelog_path
from bushexa.web.app import create_app

_KST = ZoneInfo("Asia/Seoul")
_CSRF = "changelog-csrf-token"


@pytest.fixture
def app(tmp_path):
    config = AppConfig(
        api_key="k", database_url="sqlite:///:memory:", session_secret="s",
        manager_password_path=tmp_path / "pw.txt", data_dir=tmp_path / "data",
        tz=_KST, log_level="INFO", log_dir=tmp_path / "logs",
    )
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    return create_app(config)


@pytest.fixture
def authed(app):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["admin_authed"] = True
        sess["csrf_token"] = _CSRF
    return client, app


def _saved(app):
    config = app.config["BUSHEXA_CONFIG"]
    return ChangelogEditor(default_changelog_path(config.data_dir)).load()


def test_changelog_index_requires_login(app):
    """비로그인 → 로그인 페이지 리다이렉트."""
    resp = app.test_client().get("/admin/changelog")
    assert resp.status_code in (302, 401)


def test_changelog_index_shows_seed(authed):
    """data_dir 비었을 때 static seed(공장 초기값)가 목록에 표시된다."""
    client, _ = authed
    resp = client.get("/admin/changelog")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    # static/data/changelog.json 의 최초 항목
    assert "2024-12-21" in html


def test_changelog_add_persists_to_data_dir_sorted(authed):
    """POST add → data_dir 파일에 저장되고 날짜 오름차순 정렬된다.

    seed 항목이 함께 data_dir 로 이관(persist)되는지도 확인.
    """
    client, app = authed
    resp = client.post("/admin/changelog/add", data={
        "csrf_token": _CSRF,
        "date": "2026-06-02",
        "description": "테스트 변경이력",
    })
    assert resp.status_code in (302, 303)

    saved = _saved(app)
    descs = [e["description"] for e in saved]
    dates = [e["date"] for e in saved]
    assert "테스트 변경이력" in descs, "새 항목이 저장되지 않음"
    # seed 5개 + 신규 1개
    assert "2024-12-21" in dates, "seed 항목이 data_dir 로 이관되지 않음"
    assert dates == sorted(dates), "날짜 오름차순 정렬이 아님"


def test_changelog_add_invalid_flashes_error(authed):
    """날짜 형식 오류/빈 설명 → 저장 안 됨 (data_dir 파일 미생성)."""
    client, app = authed
    resp = client.post("/admin/changelog/add", data={
        "csrf_token": _CSRF,
        "date": "2026/06/02",   # 잘못된 형식
        "description": "x",
    })
    assert resp.status_code in (302, 303)
    config = app.config["BUSHEXA_CONFIG"]
    assert not default_changelog_path(config.data_dir).exists(), "잘못된 입력인데 파일이 생성됨"


def test_changelog_remove_by_index(authed):
    """추가 후 index로 제거되면 항목 수가 줄어든다."""
    client, app = authed
    # 먼저 추가(=seed 이관 + 신규)
    client.post("/admin/changelog/add", data={
        "csrf_token": _CSRF, "date": "2026-06-02", "description": "삭제대상",
    })
    before = _saved(app)
    n = len(before)
    # 표시 순서(날짜 오름차순)에서 마지막 항목(2026-06-02 = "삭제대상")은 index n-1
    resp = client.post("/admin/changelog/remove", data={
        "csrf_token": _CSRF, "index": str(n - 1),
    })
    assert resp.status_code in (302, 303)
    after = _saved(app)
    assert len(after) == n - 1
    assert "삭제대상" not in [e["description"] for e in after]


def test_info_reflects_changelog_edits(authed):
    """admin이 추가한 항목이 /info 의 Update History 에 표시된다."""
    client, _ = authed
    client.post("/admin/changelog/add", data={
        "csrf_token": _CSRF, "date": "2026-06-02", "description": "INFO반영확인",
    })
    resp = client.get("/info")
    assert resp.status_code == 200
    assert "INFO반영확인" in resp.data.decode("utf-8")
