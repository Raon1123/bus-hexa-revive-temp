"""W4 — 노선 정보 라우트 (F03).

GET /info

정적 콘텐츠 + changelog 로드.
?hexa=6 관리자 unlock 완전 제거 (S1: 숨김 진입 없음).
changelog 없을 때 500 없이 200 + 빈 이력.

changelog는 관리자가 편집한다(admin/changelog). 편집본은 ``<data_dir>/changelog.json``,
공장 초기값(seed)은 ``static/data/changelog.json``. 둘 다 없으면 빈 이력으로 렌더.
"""

from __future__ import annotations

import logging
from pathlib import Path

from flask import Blueprint, current_app, render_template

from bushexa.services.changelog_editor import ChangelogEditor, default_changelog_path
from bushexa.web.route_diagram import build_route_lines

log = logging.getLogger("bushexa.web.routes.info")

bp = Blueprint("info", __name__)

# seed(공장 초기값) 디렉터리. 테스트(test_changelog_missing_ok)가 monkeypatch하므로 유지.
_STATIC_DATA = Path(__file__).parent.parent / "static" / "data"


@bp.route("/info", methods=["GET"])
def info_page() -> str:
    """노선 정보 페이지. ?hexa=6 등 어떤 쿼리도 관리자 UI를 노출하지 않는다."""
    config = current_app.config["BUSHEXA_CONFIG"]
    editor = ChangelogEditor(
        live_path=default_changelog_path(config.data_dir),
        seed_path=_STATIC_DATA / "changelog.json",
    )
    changelog = editor.load()
    return render_template(
        "info.html", changelog=changelog, route_lines=build_route_lines(),
    )
