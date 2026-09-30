"""Flask application factory (P4 W1).

create_app(config) -> Flask
- Registers blueprints (W2 board_bp, future blueprints).
- Sets session cookie security flags (S1: HttpOnly, SameSite=Lax, Secure if HTTPS).
- Uses config.session_secret as SECRET_KEY (S7: no hardcoding).
- Template/static folders under bushexa/web/ (not package root).
- Seeds a CSRF-ready session token on every request so Set-Cookie is emitted
  (session write required for cookie headers; also lays the S5 groundwork).
"""

from __future__ import annotations

import hmac
import secrets
import time
from pathlib import Path

from flask import Flask, g, redirect, request, session, url_for

from bushexa.config import AppConfig
from bushexa.logging_setup import setup_logging
from bushexa.services.stop_name_dict import get_stop_names
from bushexa.web.i18n import SUPPORTED_LANGS, lang_url, localize_stop, resolve_lang, translate
from bushexa.web.timing import record, server_timing_header

_HERE = Path(__file__).parent


def create_app(config: AppConfig) -> Flask:
    """Construct and return a configured Flask application.

    Parameters
    ----------
    config : AppConfig
        Resolved runtime configuration (frozen dataclass).
    """
    app = Flask(
        __name__,
        template_folder=str(_HERE / "templates"),
        static_folder=str(_HERE / "static"),
    )

    # --- Logging setup (W16) --------------------------------------------
    setup_logging(level=config.log_level, log_dir=config.log_dir)

    # --- Core settings --------------------------------------------------
    app.secret_key = config.session_secret            # S7: from config, never hardcoded

    # --- Session cookie security flags (S1) -----------------------------
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    # Secure flag: driven by config.session_cookie_secure (env: BUSHEXA_SESSION_COOKIE_SECURE).
    # Default False for dev/HTTP environments; set True for HTTPS production deployments.
    # Flask cannot vary SECURE per-request from static config, so this must be set at
    # startup time (W1 §2, S1).
    app.config["SESSION_COOKIE_SECURE"] = config.session_cookie_secure

    # Stash the config object so blueprints/routes can retrieve it.
    app.config["BUSHEXA_CONFIG"] = config

    # --- CSRF session token seeding (S5 groundwork) ---------------------
    # Writing to the session forces Flask to emit Set-Cookie on every first
    # response.  This also provides the token storage point for admin POST
    # CSRF enforcement (W10+).  No enforcement happens here — W1/W2 are
    # GET-only, and CSRF is for state-changing admin POSTs only.
    @app.before_request
    def _seed_csrf_token() -> None:
        if "csrf_token" not in session:
            session["csrf_token"] = secrets.token_urlsafe(32)

    # --- Server-Timing: request wall-clock start (perf 진단) -------------
    # 단계별 구간은 라우트/도메인에서 bushexa.web.timing.span() 으로 누적되고,
    # 전체 소요(total)는 여기서 시작점을 잡아 after_request에서 마감한다.
    @app.before_request
    def _timing_start() -> None:
        g._timing_t0 = time.perf_counter()

    # --- CSRF enforcement for admin state-changing requests (S5) --------
    # All POST/PUT/PATCH/DELETE under /admin/ must supply a matching CSRF
    # token either in the form body (csrf_token) or the X-CSRFToken header.
    # Mismatch or absence → 400.  GET/HEAD/OPTIONS are exempt.
    @app.before_request
    def _csrf_protect() -> None:
        from flask import request as _req, abort as _abort
        if _req.method in ("GET", "HEAD", "OPTIONS", "TRACE"):
            return
        if not _req.path.startswith("/admin/"):
            return
        expected = session.get("csrf_token")
        if not expected:
            _abort(400)
        provided = (
            _req.form.get("csrf_token")
            or _req.headers.get("X-CSRFToken")
        )
        # 타이밍 안전 비교(S5): 단순 != 는 일치 길이에 비례한 비교 시간을 누설한다.
        # bytes로 인코딩 — compare_digest는 비ASCII str(공격자 제어 폼 값)에 TypeError를
        # 던지므로 encode 없이는 400 대신 500이 된다.
        if not provided or not hmac.compare_digest(
                provided.encode("utf-8"), expected.encode("utf-8")):
            _abort(400)

    # --- i18n: language resolution (before_request) ---------------------
    # Resolves ?lang= → cookie → "ko" and stores result in flask.g so the
    # context processor and any route handler can read g.lang without
    # repeating the resolution.
    @app.before_request
    def _resolve_lang() -> None:
        g.lang = resolve_lang(request)

    # --- i18n: context processor ----------------------------------------
    # Exposes `lang`, `t(key, **kw)` and `lang_url(code)` to every template.
    # lang_url keeps the current query string (e.g. /busno?bus=713) when switching.
    @app.context_processor
    def _inject_i18n() -> dict:
        lang = getattr(g, "lang", "ko")
        return {
            "lang": lang,
            "t": lambda key, **kw: translate(key, lang, **kw),
            "lang_url": lambda code: lang_url(request, code),
        }

    # --- i18n: stop-name filter (ADR-014) -------------------------------
    # {{ name | stop }} — 정류소 이름을 현재 언어로. 사전은 관리자 편집 파일
    # (<data_dir>/stop_names.json) + 시드이며, mtime 캐시라 다른 워커의 저장도 즉시 반영.
    @app.template_filter("stop")
    def _stop_filter(name):
        lang = getattr(g, "lang", "ko")
        if lang == "ko" or not name:
            return name
        return localize_stop(str(name), lang, get_stop_names(config.data_dir))

    # --- i18n: persist lang cookie on valid ?lang= ----------------------
    # Sets a 1-year cookie only when the user explicitly sends ?lang=.
    # This is done in after_request so we always return a response object.
    @app.after_request
    def _persist_lang(response):
        q = request.args.get("lang", "")
        if q in SUPPORTED_LANGS:
            response.set_cookie(
                "lang", q,
                max_age=365 * 24 * 3600,
                samesite="Lax",
                httponly=False,  # readable by client JS if needed
            )
        # 같은 URL이 쿠키·Accept-Language에 따라 다른 언어로 렌더되므로 캐시 키에 포함시킨다.
        response.vary.add("Cookie")
        response.vary.add("Accept-Language")
        return response

    # --- Server-Timing 응답 헤더 (perf 진단) ----------------------------
    # 라우트/도메인이 span()으로 누적한 구간 + 전체(total)를 직렬화해 헤더로 노출.
    # 브라우저 DevTools Network → 요청 → Timing → "Server Timing" 에서 확인.
    @app.after_request
    def _emit_server_timing(response):
        t0 = getattr(g, "_timing_t0", None)
        if t0 is not None:
            record("total", (time.perf_counter() - t0) * 1000.0)
        header = server_timing_header()
        if header:
            response.headers["Server-Timing"] = header
        return response

    # --- Root redirect --------------------------------------------------
    @app.route("/")
    def index():
        return redirect(url_for("board.departure_board"))

    # --- Blueprint registration -----------------------------------------
    from bushexa.web.routes.board import bp as board_bp
    app.register_blueprint(board_bp)

    from bushexa.web.routes.board_lite import bp as board_lite_bp
    app.register_blueprint(board_lite_bp)

    from bushexa.web.routes.busno import bp as busno_bp
    app.register_blueprint(busno_bp)

    from bushexa.web.routes.info import bp as info_bp
    app.register_blueprint(info_bp)

    from bushexa.web.routes.stops import bp as stops_bp
    app.register_blueprint(stops_bp)

    from bushexa.web.routes.unist_board import bp as unist_board_bp
    app.register_blueprint(unist_board_bp)

    from bushexa.web.routes.unist_timetable import bp as unist_timetable_bp
    app.register_blueprint(unist_timetable_bp)

    from bushexa.web.routes.busan import bp as busan_bp
    app.register_blueprint(busan_bp)

    from bushexa.web.routes.seoul import bp as seoul_bp
    app.register_blueprint(seoul_bp)

    from bushexa.web.routes.ktx import bp as ktx_bp
    app.register_blueprint(ktx_bp)

    from bushexa.web.routes.running import bp as running_bp
    app.register_blueprint(running_bp)

    from bushexa.web.routes.admin import bp as admin_bp
    app.register_blueprint(admin_bp)

    return app
