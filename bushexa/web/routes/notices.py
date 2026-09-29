"""기한형 공지 부분 갱신 — GET /partial/notices?surface=board|unist|stops

출발 게시판·UNIST 출발·정류소 화면은 전체 페이지를 다시 읽지 않고 HTMX 로 표만 갱신한다.
공지 영역도 이 엔드포인트를 주기적으로 불러(outerHTML 교체) 시행일 전환·만료·관리자 끄기를
열린 화면에 반영한다. 공지 선택은 app.py 의 context processor 가 한다.
"""

from __future__ import annotations

from flask import Blueprint, make_response, render_template

bp = Blueprint("notices", __name__)


@bp.route("/partial/notices", methods=["GET"])
def notices_partial():
    resp = make_response(render_template("partial/notices.html"))
    resp.headers["Cache-Control"] = "no-store"
    return resp
