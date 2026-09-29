"""W4 — 노선 정보 라우트 (F03).

GET  /info         정적 콘텐츠 + changelog + 노선도. 노선도는 A(지도)·B(노선별 목록) 중 하나를
                   보여 준다: ?view=a|b > 쿠키 > 무작위. 노출·전환을 센다(services/route_map_ab).
POST /info/event   브라우저가 보내는 A/B 이벤트(전환·조작). 노출은 서버만 센다.

정적 콘텐츠 + changelog 로드.
?hexa=6 관리자 unlock 완전 제거 (S1: 숨김 진입 없음).
changelog 없을 때 500 없이 200 + 빈 이력.

changelog는 관리자가 편집한다(admin/changelog). 편집본은 ``<data_dir>/changelog.json``,
공장 초기값(seed)은 ``static/data/changelog.json``. 둘 다 없으면 빈 이력으로 렌더.
"""

from __future__ import annotations

import logging
import secrets
from pathlib import Path

from flask import Blueprint, abort, current_app, make_response, render_template, request

from bushexa.services.changelog_editor import ChangelogEditor, default_changelog_path
from bushexa.services import route_map_ab
from bushexa.time_utils import get_now
from bushexa.web.route_diagram import ROUTE_CHANGES, render_route_diagram
from bushexa.web.route_lines import build_route_lines

log = logging.getLogger("bushexa.web.routes.info")

bp = Blueprint("info", __name__)

# seed(공장 초기값) 디렉터리. 테스트(test_changelog_missing_ok)가 monkeypatch하므로 유지.
_STATIC_DATA = Path(__file__).parent.parent / "static" / "data"

VIEW_COOKIE = "route_map_view"
_VIEW_COOKIE_MAX_AGE = 60 * 60 * 24 * 90


@bp.route("/info", methods=["GET"])
def info_page() -> str:
    """노선 정보 페이지. ?hexa=6 등 어떤 쿼리도 관리자 UI를 노출하지 않는다."""
    config = current_app.config["BUSHEXA_CONFIG"]
    editor = ChangelogEditor(
        live_path=default_changelog_path(config.data_dir),
        seed_path=_STATIC_DATA / "changelog.json",
    )
    changelog = editor.load()
    today = get_now().date()

    asked = request.args.get("view")
    remembered = request.cookies.get(VIEW_COOKIE)
    if asked in route_map_ab.VARIANTS:
        variant = asked
        # JS 없이 전환 링크(?view=)로 넘어온 경우. JS 전환은 /info/event 로 이미 셌다.
        if remembered in route_map_ab.VARIANTS and remembered != asked:
            _count(config.data_dir, f"switch_to_{asked}", today)
    elif remembered in route_map_ab.VARIANTS:
        variant = remembered
    else:
        variant = secrets.choice(route_map_ab.VARIANTS)
    _count(config.data_dir, f"view_{variant}", today)

    resp = make_response(render_template(
        "info.html",
        changelog=changelog,
        variant=variant,
        diagram=render_route_diagram(today),
        route_lines=build_route_lines(today),
        upcoming_changes=[c for c in ROUTE_CHANGES if today < c.effective],
    ))
    resp.set_cookie(VIEW_COOKIE, variant, max_age=_VIEW_COOKIE_MAX_AGE,
                    samesite="Lax", secure=config.session_cookie_secure)
    return resp


@bp.route("/info/event", methods=["POST"])
def info_event():
    """A/B 이벤트 1회 기록(sendBeacon). 브라우저용이 아닌 이벤트는 400, 기록 실패는 로그 후 204."""
    event = request.form.get("e") or request.args.get("e") or ""
    if event not in route_map_ab.CLIENT_EVENTS:
        abort(400)
    config = current_app.config["BUSHEXA_CONFIG"]
    _count(config.data_dir, event, get_now().date())
    return "", 204


def _count(data_dir, event: str, today) -> None:
    # 카운터는 부가 기능이다. 파일 오류로 페이지를 깨뜨리지 않되 반드시 로그한다.
    try:
        route_map_ab.record(route_map_ab.default_path(data_dir), event, today)
    except OSError:
        log.exception("route_map_ab 기록 실패: %s", event)
