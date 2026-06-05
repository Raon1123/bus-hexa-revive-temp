"""P4 W10 + W12 + W13a + W13b + W14 + W16 — 관리자 라우트 (F04, TP-007/008/012/009/010/011/015).

W10: login/logout/dashboard/password  (login_required 데코레이터 포함)
W12: /admin/data  + /admin/data.csv   (필터·페이지네이션·CSV)
W13a: /admin/timetable (목록·편집·저장; TimetableEditor.save 위임, TP-009)
W13b: /admin/timetable/recrawl (+/<job_id>/stream SSE; TimetableCrawlJob, TP-010)
W14: /admin/govtrack/status (JSON) + /admin/govtrack/status/stream (SSE 5초)
W16: /admin/logs (로그 tail 뷰어, LogTailReader, level/lines 검증, 고정 경로)
F3: /admin/backup  — 설정 백업/복구 (zip export + import)
F4: /admin/worker-status  — govtrack + arrival 데몬 상태 대시보드
F5: /admin/audit  — 관리자 변경 감사 로그

lockout 상태는 현재 app context (current_app.config["_ADMIN_LOCKOUT"])에 보관 —
테스트마다 새 app을 만들므로 자동 격리. module 전역 dict는 쓰지 않는다.
재크롤 job도 동일하게 app-scope(current_app.config["_TIMETABLE_CRAWL_JOB"])에 보관 —
start-POST·stream-GET·conflict가 같은 인스턴스를 공유해야 하고, 테스트는 mock을 주입한다.

S5 CSRF 검증은 app.py before_request에서 담당(admin prefix POST 한정).
이 파일에서 CSRF 토큰을 직접 검증하지 않는다.
"""

from __future__ import annotations

import functools
import json
import logging
import os
import re
import time
from dataclasses import asdict, is_dataclass
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    stream_with_context,
    url_for,
)

from bushexa.data.constants import ROUTEID
from bushexa.data.timetable import timetable_dir, save_timetable, get_timetable, validate_timetable
from bushexa.domain.board import via_default
from bushexa.db.connection import create_connection
from bushexa.db.repo import BusLogRepo
from bushexa.api_clients.holiday import HolidayClient
from bushexa.services.arrival_status import ArrivalStatusReader
from bushexa.services.audit_log import AuditLog, default_audit_path
from bushexa.services.auth import AuthService
from bushexa.services.backup import create_backup_zip, validate_and_restore, RestoreError
from bushexa.services.changelog_editor import ChangelogEditor, default_changelog_path
from bushexa.services.govtrack_status import GovtrackStatusReader
from bushexa.services.holiday_editor import HolidayEditor, default_holidays_path
from bushexa.services.holiday_service import get_effective_holiday_set
from bushexa.services.log_reader import LogTailReader, STANDARD_LEVELS
from bushexa.services.special_timetable import SpecialTimetableService, default_special_path
from bushexa.services.timetable_crawl import ConflictError, TimetableCrawlJob
from bushexa.services.timetable_editor import TimetableEditor, ValidationError
from bushexa.services.via_editor import ViaEditor, default_via_path
from bushexa.time_utils import KSTClock, is_holiday

log = logging.getLogger("bushexa.web.routes.admin")

bp = Blueprint("admin", __name__, url_prefix="/admin")

# ─────────────────────────────────────────────────
# lockout 상수
# ─────────────────────────────────────────────────

_MAX_FAILS = 5
_LOCKOUT_SECS = 10


# ─────────────────────────────────────────────────
# 내부 헬퍼 — AuthService 팩토리
# ─────────────────────────────────────────────────

def _get_auth_service() -> AuthService:
    config = current_app.config["BUSHEXA_CONFIG"]
    env_pw = os.environ.get("MANAGER_PASSWORD")
    return AuthService(secret_path=config.manager_password_path, env_password=env_pw)


# ─────────────────────────────────────────────────
# login_required 데코레이터
# ─────────────────────────────────────────────────

def login_required(view):
    """session['admin_authed'] 가 True가 아니면 /admin/login?next=<path> 로 302."""
    @functools.wraps(view)          # E-1 endpoint 이름 보존
    def wrapper(*args, **kwargs):
        if not session.get("admin_authed"):
            # advisor 지침: f-string 방식으로 next= 조립 (URL-encoding 슬래시 방지)
            login_url = f"{url_for('admin.login_form')}?next={request.path}"
            return redirect(login_url)
        return view(*args, **kwargs)
    return wrapper


# ─────────────────────────────────────────────────
# lockout 헬퍼 — app-scope state
# ─────────────────────────────────────────────────

def _lockout_state() -> dict:
    """현재 앱의 lockout dict 반환. _ADMIN_LOCKOUT 키가 없으면 생성."""
    return current_app.config.setdefault("_ADMIN_LOCKOUT", {})


def _is_locked(key: str) -> bool:
    """IP 가 현재 lockout 상태인지 검사. 만료된 lockout은 자동 해제."""
    state = _lockout_state()
    entry = state.get(key)
    if entry is None:
        return False
    locked_until, _ = entry
    if locked_until is None:
        # lockout이 아닌 일반 실패 카운트 entry
        return False
    now_ts = KSTClock().now().timestamp()
    if now_ts >= locked_until:
        del state[key]
        return False
    return True


def _record_fail(key: str) -> int:
    """실패 횟수 +1. _MAX_FAILS 도달 시 lockout 등록. 현재 누적 실패 수 반환."""
    state = _lockout_state()
    now_ts = KSTClock().now().timestamp()
    entry = state.get(key)
    if entry is None:
        fails = 1
        locked_until = None
    else:
        locked_until, fails = entry
        if locked_until is not None and now_ts >= locked_until:
            # 만료된 lockout → 초기화
            fails = 1
            locked_until = None
        else:
            fails = (fails or 0) + 1

    if fails >= _MAX_FAILS:
        locked_until = now_ts + _LOCKOUT_SECS
    # else: locked_until stays None (not locked, just counting)

    state[key] = (locked_until, fails)
    return fails


def _reset_fails(key: str) -> None:
    state = _lockout_state()
    state.pop(key, None)


def _lockout_key() -> str:
    """요청 IP 기반 lockout 키 (프록시 없으면 remote_addr)."""
    return request.remote_addr or "unknown"


# ─────────────────────────────────────────────────
# S1/OPEN-REDIRECT 방어 헬퍼
# ─────────────────────────────────────────────────

def _safe_next(next_url: str) -> str:
    """next_url이 안전한 내부 경로면 반환, 아니면 '/admin/'을 반환한다.

    안전 판정 기준 (모두 만족해야 함):
      1. 제어문자·공백 제거 후 단일 '/'로 시작한다.
      2. '//' 또는 '/\' (백슬래시)로 시작하지 않는다.
         (브라우저가 '/\' → '//' → 외부 도메인으로 정규화하는 우회 차단)
      3. '\\' 문자가 포함되지 않는다.
      4. urlparse 결과 netloc == "" 이고 scheme == "".
         (http://evil.com 형태의 절대 URL 차단)

    S1/OPEN-REDIRECT (security-audit-P4-20260602-T01.md) 수정.
    """
    _DEFAULT = "/admin/"
    if not next_url:
        return _DEFAULT

    # 1. 제어문자·공백 정리 — 정규화 후 검사
    cleaned = re.sub(r"[\x00-\x1f\x7f\s]", "", next_url)
    if not cleaned:
        return _DEFAULT

    # 2. 단일 '/'로 시작해야 한다
    if not cleaned.startswith("/"):
        return _DEFAULT

    # 3. '//' 또는 '/\' 로 시작하면 거부 (프로토콜 상대 URL / 백슬래시 우회)
    if cleaned.startswith("//") or cleaned.startswith("/\\"):
        return _DEFAULT

    # 4. 백슬래시 포함 자체를 거부 (브라우저 정규화 우회 차단)
    if "\\" in cleaned:
        return _DEFAULT

    # 5. urlparse로 netloc·scheme 이중 검증
    parsed = urlparse(cleaned)
    if parsed.netloc != "" or parsed.scheme != "":
        return _DEFAULT

    return cleaned


# ─────────────────────────────────────────────────
# W10 라우트
# ─────────────────────────────────────────────────

@bp.get("/login")
def login_form() -> str:
    auth = _get_auth_service()
    return render_template("admin/login.html", needs_setup=auth.needs_setup)


@bp.post("/login")
def login_submit() -> Response:
    auth = _get_auth_service()
    key = _lockout_key()

    # setup 모드: 비밀번호를 신규 설정
    if auth.needs_setup:
        new_pw = request.form.get("new_password", "")
        confirm = request.form.get("confirm_password", "")
        if len(new_pw) < 8:
            flash("비밀번호는 8자 이상이어야 합니다.", "error")
            return render_template("admin/login.html", needs_setup=True), 422
        if new_pw != confirm:
            flash("비밀번호 확인이 일치하지 않습니다.", "error")
            return render_template("admin/login.html", needs_setup=True), 422
        # 초기 비밀번호 설정은 AuthService.set_initial로 위임 (F04 §4.4).
        result = auth.set_initial(new_pw)
        if not result.success:
            if result.code == "too_short":
                flash("비밀번호는 8자 이상이어야 합니다.", "error")
                return render_template("admin/login.html", needs_setup=True), 422
            # already_set: 다른 요청이 먼저 설정 → 일반 로그인으로 안내
            flash("비밀번호 저장에 실패했습니다. 다시 시도해 주세요.", "error")
            status = 409 if result.code == "already_set" else 500
            return render_template("admin/login.html", needs_setup=auth.needs_setup), status
        session["admin_authed"] = True
        return redirect(url_for("admin.dashboard"))

    # lockout 검사
    if _is_locked(key):
        abort(423)

    pw = request.form.get("password", "")
    if not auth.verify(pw):
        fails = _record_fail(key)
        if fails >= _MAX_FAILS:
            abort(423)
        flash("비밀번호가 올바르지 않습니다.", "error")
        return render_template("admin/login.html", needs_setup=False), 401

    _reset_fails(key)
    session["admin_authed"] = True
    next_url = request.args.get("next", "")
    # S1/OPEN-REDIRECT 방어: _safe_next()가 내부 경로만 허용, 아니면 /admin/
    return redirect(_safe_next(next_url))


@bp.post("/logout")
@login_required
def logout() -> Response:
    session.pop("admin_authed", None)
    return redirect(url_for("admin.login_form"))


@bp.get("/")
@login_required
def dashboard() -> str:
    return render_template("admin/dashboard.html")


@bp.get("/password")
@login_required
def password_form() -> str:
    return render_template("admin/password.html", error=None)


@bp.post("/password")
@login_required
def password_change() -> Response:
    current_pw = request.form.get("current", "")
    new_pw = request.form.get("new", "")
    confirm = request.form.get("confirm", "")

    if new_pw != confirm:
        return render_template("admin/password.html", error="new_mismatch"), 422

    auth = _get_auth_service()
    result = auth.change_password(current_pw, new_pw)

    if not result.success:
        if result.code == "current_invalid":
            return render_template("admin/password.html", error="current_invalid"), 422
        if result.code == "too_short":
            return render_template("admin/password.html", error="too_short"), 422
        return render_template("admin/password.html", error="io_error"), 500

    flash("비밀번호가 변경되었습니다.", "success")
    _audit("password.change")
    return redirect(url_for("admin.dashboard"))


# ─────────────────────────────────────────────────
# W12 라우트
# ─────────────────────────────────────────────────

def _parse_day(day_str: str | None) -> date | None:
    """?day=YYYYMMDD → date. 잘못된 형식이면 ValueError."""
    if not day_str:
        return None
    if len(day_str) != 8 or not day_str.isdigit():
        raise ValueError(f"잘못된 day 형식: {day_str!r}")
    try:
        return date(int(day_str[:4]), int(day_str[4:6]), int(day_str[6:8]))
    except ValueError:
        raise ValueError(f"잘못된 day 형식: {day_str!r}")


def _get_repo_conn():
    config = current_app.config["BUSHEXA_CONFIG"]
    conn = create_connection(config.database_url)
    return conn


@bp.get("/data")
@login_required
def data_browser() -> str:
    """DB 브라우저: ?route_id=&stop_id=&vehicle=&day=YYYYMMDD&page=&size="""
    route_id = request.args.get("route_id") or None
    stop_id = request.args.get("stop_id") or None
    vehicle = request.args.get("vehicle") or None
    day_str = request.args.get("day") or None
    try:
        page = max(1, int(request.args.get("page", "1") or "1"))
    except (ValueError, TypeError):
        page = 1
    try:
        size = max(1, min(500, int(request.args.get("size", "100") or "100")))
    except (ValueError, TypeError):
        size = 100

    try:
        day = _parse_day(day_str)
    except ValueError:
        abort(400)

    try:
        conn = _get_repo_conn()
        with BusLogRepo(conn) as repo:
            result = repo.query_paged(
                route_id=route_id,
                stop_id=stop_id,
                vehicle_no=vehicle,
                day=day,
                page=page,
                size=size,
            )
    except Exception as exc:
        log.error("data_browser DB 오류: %s", exc, exc_info=True)
        result = None

    return render_template(
        "admin/data_browser.html",
        result=result,
        filters=dict(route_id=route_id or "", stop_id=stop_id or "",
                     vehicle=vehicle or "", day=day_str or ""),
        page=page,
        size=size,
    )


@bp.get("/data.csv")
@login_required
def data_csv() -> Response:
    """동일 필터로 CSV (UTF-8 BOM) streaming, max_rows=10000."""
    route_id = request.args.get("route_id") or None
    stop_id = request.args.get("stop_id") or None
    vehicle = request.args.get("vehicle") or None
    day_str = request.args.get("day") or None

    try:
        day = _parse_day(day_str)
    except ValueError:
        abort(400)

    def generate():
        conn = _get_repo_conn()
        with BusLogRepo(conn) as repo:
            yield from repo.export_csv(
                route_id=route_id,
                stop_id=stop_id,
                vehicle_no=vehicle,
                day=day,
                max_rows=10000,
            )

    return Response(
        stream_with_context(generate()),
        mimetype="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": "attachment; filename=bus_data.csv",
        },
    )


# ─────────────────────────────────────────────────
# 경유지(주요 정류소) 편집 — 출발 게시판 '경유' 표시 문자열
#
# 코드 상수 VIA_STOPS(노선→목적지→문자열)가 기본값. 운영자가 admin에서 고친 값은
# data/via_overrides.json에 override로 저장되어 board가 우선 적용한다(domain._via_for).
# ─────────────────────────────────────────────────

def _via_editor() -> ViaEditor:
    config = current_app.config["BUSHEXA_CONFIG"]
    return ViaEditor(default_via_path(config.data_dir))


def _via_catalog() -> list[tuple[str, str, str, str]]:
    """board에 나타날 수 있는 (busno, via_key, route_id, terminal) 목록.

    via_key는 목적지(terminal.split()[0]) — VIA_STOPS 키와 동일 규칙. ROUTEID의 양방향을
    모두 포함하므로 UNIST 방면처럼 curated가 없는 방향도 편집 대상이 된다(중복 제거, ROUTEID 순).
    """
    seen: set[tuple[str, str]] = set()
    out: list[tuple[str, str, str, str]] = []
    for route_id, (busno, terminal, _dep, _stops) in ROUTEID.items():
        via_key = terminal.split()[0] if terminal else ""
        key = (busno, via_key)
        if key in seen:
            continue
        seen.add(key)
        out.append((busno, via_key, route_id, terminal))
    return out


def _via_entries() -> list[dict]:
    """편집 대상 목록: board에 나타나는 모든 (노선, 방향) + 기본값/현재값."""
    overrides = _via_editor().load()
    entries: list[dict] = []
    for busno, via_key, route_id, terminal in _via_catalog():
        default_str = via_default(route_id, busno, terminal)
        ov = overrides.get(busno, {}).get(via_key, "")
        entries.append({
            "busno": busno,
            "dest": via_key,
            "default": default_str,
            "value": ov or default_str,
            "is_override": bool(ov),
            "field": f"{busno}|{via_key}",  # 폼 필드명 (POST에서 분해)
        })
    return entries


@bp.get("/via")
@login_required
def via_index() -> str:
    """경유지 편집 화면 — 노선·목적지별 경유 문자열 textarea."""
    return render_template("admin/via.html", entries=_via_entries())


@bp.post("/via")
@login_required
def via_save() -> Response:
    """편집된 경유지 문자열을 override로 저장. 기본값과 같거나 빈 값은 override에서 제외."""
    overrides: dict[str, dict[str, str]] = {}
    for busno, via_key, route_id, terminal in _via_catalog():
        default_str = via_default(route_id, busno, terminal)
        raw = (request.form.get(f"{busno}|{via_key}") or "").strip()
        # 빈 값 또는 기본값과 동일하면 override 불필요(상수/노선 fallback 사용)
        if raw and raw != default_str.strip():
            overrides.setdefault(busno, {})[via_key] = raw
    _via_editor().save(overrides)
    flash("경유지 표시가 저장되었습니다.", "success")
    _audit("via.save", override_count=sum(len(v) for v in overrides.values()))
    return redirect(url_for("admin.via_index"))


# ─────────────────────────────────────────────────
# W13a — 시간표 편집 (TP-009)
#
# weekday 키는 데이터 계약상 "0"(평일)/"1"(토요일)/"2"(일·공휴일) — 숫자 문자열.
# 화면 라벨만 평일/토요일/일·공휴일이고 폼/디스크 키는 숫자다(validate_timetable 강제).
# ─────────────────────────────────────────────────

# weekday 키 → 화면 라벨 (TP-009 §2 탭). 키 순서가 탭 순서.
_WEEKDAY_TABS: list[tuple[str, str]] = [
    ("0", "평일"),
    ("1", "토요일"),
    ("2", "일·공휴일"),
]


def _get_timetable_editor() -> TimetableEditor:
    """공개 라우트와 동일한 디렉터리(timetable_dir)를 읽고 쓰는 에디터.

    busno 라우트가 get_timetable(dir 미지정 → timetable_dir())로 읽으므로,
    편집 결과가 공개 화면에 그대로 보이려면 같은 dir을 써야 한다.
    백업은 그 형제 디렉터리 timetable_backup/ 에 둔다(atomic_write_bytes가 부모 자동 생성).
    """
    tdir = timetable_dir()
    bdir = tdir.parent / "timetable_backup"
    return TimetableEditor(dir=tdir, backup_dir=bdir)


def _known_busnos() -> set[str]:
    """알려진 노선 화이트리스트 (traversal·임의 파일 접근 차단, TP-009 §4)."""
    return {r.busno for r in _get_timetable_editor().list_routes()}


def _require_known_busno(busno: str) -> None:
    if busno not in _known_busnos():
        abort(404)


@bp.get("/timetable")
@login_required
def timetable_index() -> str:
    """노선 목록 — 편집 진입점 (TP-009 §2 #1)."""
    editor = _get_timetable_editor()
    routes = editor.list_routes()
    return render_template("admin/timetable_index.html", routes=routes)


@bp.get("/timetable/<busno>")
@login_required
def timetable_edit(busno: str) -> str:
    """편집 화면 — 3개 weekday 탭 + departure별 시각 목록 (TP-009 §2 #2)."""
    _require_known_busno(busno)
    editor = _get_timetable_editor()
    try:
        data = editor.load(busno)
    except FileNotFoundError:
        # 디스크에 아직 파일이 없으면 빈 시간표로 편집 시작 (빈 상태, TP-009 §5).
        data = {key: {} for key, _ in _WEEKDAY_TABS}
    return render_template(
        "admin/timetable_edit.html",
        busno=busno,
        data=data,
        weekday_tabs=_WEEKDAY_TABS,
    )


def _parse_timetable_form() -> dict:
    """폼 → TimetableData 재구성.

    와이어 포맷(Designer 미명시 → Executor 결정, 보고 대상):
      hidden `weekdays`(공백 구분 키 목록)과 각 (wd, dep) 조합에 대해
      hidden `departures__<wd>`(공백 구분 departure 목록),
      그리고 textarea/입력 `times__<wd>__<dep>`(줄바꿈 또는 콤마 구분 HH:MM).
    빈 시각은 제거하되 잘못된 값은 그대로 둬서 validate_timetable이 422로 거른다.
    """
    weekdays = (request.form.get("weekdays") or "").split()
    data: dict = {}
    for wd in weekdays:
        deps = (request.form.get(f"departures__{wd}") or "").split()
        data[wd] = {}
        for dep in deps:
            raw = request.form.get(f"times__{wd}__{dep}", "")
            # 줄바꿈·콤마·공백 어느 것으로 구분해도 받아들인다.
            tokens = [t.strip() for t in raw.replace(",", "\n").splitlines()]
            data[wd][dep] = [t for t in tokens if t]
    return data


@bp.post("/timetable/<busno>")
@login_required
def timetable_save(busno: str) -> Response:
    """저장 — TimetableEditor.save 위임. 검증 실패 시 422 + 원본 보존 (TP-009 §6)."""
    _require_known_busno(busno)
    data = _parse_timetable_form()
    editor = _get_timetable_editor()
    try:
        editor.save(busno, data)
    except ValidationError as exc:
        # 디스크 원본은 save가 검증을 먼저 하므로 무손상 (TP-009 §6).
        return render_template(
            "admin/timetable_edit.html",
            busno=busno,
            data=data,
            weekday_tabs=_WEEKDAY_TABS,
            errors=exc.issues,
        ), 422
    flash(f"{busno} 시간표가 저장되었습니다 (백업 생성됨).", "success")
    _audit("timetable.save", busno=busno)
    return redirect(url_for("admin.timetable_edit", busno=busno))


# ─────────────────────────────────────────────────
# W13b — 시간표 재크롤 SSE (TP-010)
# ─────────────────────────────────────────────────

def _make_crawl_fn():
    """운영 재크롤 함수: W4 crawl_all_timetables에 config/client를 바인딩한 closure.

    시그니처는 TimetableCrawlJob이 요구하는 ``(*, vacation, on_progress) -> None``.
    timetable_dir()(공개 라우트와 동일 dir)에 5개 노선 JSON을 원자적으로 기록한다.
    client/import는 호출 시점에 묶어 app-factory import 비용을 피한다.
    """
    config = current_app.config["BUSHEXA_CONFIG"]

    def _crawl(*, vacation: bool, on_progress) -> None:
        from bushexa.api_clients.ulsan_bis import UlsanBisClient
        from bushexa.crawler.timetable_crawl import crawl_all_timetables

        client = UlsanBisClient(config.api_key)
        crawl_all_timetables(client, vacation=vacation, on_progress=on_progress)

    return _crawl


def _get_crawl_job() -> TimetableCrawlJob:
    """app-scope 재크롤 job 싱글턴. 테스트는 mock을 미리 주입할 수 있다."""
    job = current_app.config.get("_TIMETABLE_CRAWL_JOB")
    if job is None:
        job = TimetableCrawlJob(_make_crawl_fn())
        current_app.config["_TIMETABLE_CRAWL_JOB"] = job
    return job


@bp.post("/timetable/recrawl")
@login_required
def timetable_recrawl() -> Response:
    """재크롤 job 시작 → job_id JSON. 동시 2번째는 409 (TP-010 §6)."""
    vacation = request.form.get("vacation", "").lower() in ("on", "true", "1", "yes")
    job = _get_crawl_job()
    try:
        job_id = job.start(vacation=vacation)
    except ConflictError:
        return jsonify({"error": "이미 진행 중인 재크롤이 있습니다"}), 409
    return jsonify({"job_id": job_id})


def _sse_payload(payload) -> str:
    """progress 이벤트 payload를 JSON 문자열로 직렬화 (ProgressEvent dataclass 포함)."""
    if is_dataclass(payload) and not isinstance(payload, type):
        payload = asdict(payload)
    return json.dumps(payload, ensure_ascii=False, default=str)


def _format_sse(kind: str, payload) -> str:
    """(kind, payload) → `event: <kind>\\ndata: <json>\\n\\n` (TP-010 §8 형식)."""
    if kind == "progress":
        data = _sse_payload(payload)
    elif kind == "done":
        data = "{}"
    else:  # error
        data = json.dumps({"message": str(payload)}, ensure_ascii=False)
    return f"event: {kind}\ndata: {data}\n\n"


def _stream_events(events):
    """progress 이벤트 iterator → SSE 라인. done/error에서 종결."""
    for kind, payload in events:
        yield _format_sse(kind, payload)
        if kind in ("done", "error"):
            return


@bp.get("/timetable/recrawl/<job_id>/stream")
@login_required
def timetable_recrawl_stream(job_id: str) -> Response:
    """SSE 스트림 — progress(≥1)/done/error. 미존재 job_id는 404 (TP-010 §6)."""
    job = _get_crawl_job()
    # progress()는 generator라 호출만으로 본문이 실행되지 않는다 —
    # 첫 이벤트를 미리 당겨봐서 KeyError(미존재 job_id)면 스트림 전에 404로 끝낸다.
    events = job.progress(job_id)
    try:
        first = next(events)
    except KeyError:
        abort(404)
    except StopIteration:
        first = None

    def generate():
        if first is not None:
            kind, payload = first
            yield _format_sse(kind, payload)
            if kind in ("done", "error"):
                return
        yield from _stream_events(events)

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ─────────────────────────────────────────────────
# W14 — govtrack status + SSE (TP-011)
# ─────────────────────────────────────────────────

def _get_govtrack_reader() -> GovtrackStatusReader:
    """status 파일 경로: config.data_dir / govtrack_status.json (cli.py Writer와 동일)."""
    config = current_app.config["BUSHEXA_CONFIG"]
    from pathlib import Path as _Path
    return GovtrackStatusReader(_Path(config.data_dir) / "govtrack_status.json")


def _status_to_dict(status) -> dict:
    """GovtrackStatus dataclass → JSON-serializable dict."""
    if status is None:
        return {}
    return {
        "cycle_started_at": status.cycle_started_at,
        "last_success_at": status.last_success_at,
        "consecutive_failures": status.consecutive_failures,
        "total_inserts": status.total_inserts,
        "total_errors": status.total_errors,
        "committed": status.committed,
        "route_breakdown": status.route_breakdown,
    }


@bp.get("/govtrack/status")
@login_required
def govtrack_status() -> Response:
    """govtrack 데몬 최신 상태 JSON (F04 AC-G1/G2, TP-011 AC-1).

    consecutive_failures>0 이면 데몬 미동작으로 판단 (카드 강조는 템플릿 담당).
    파일 부재/빈 이력 시 빈 dict 반환 (500 아님).
    """
    reader = _get_govtrack_reader()
    status = reader.latest()
    return jsonify(_status_to_dict(status))


_SSE_INTERVAL_SECS = 5


@bp.get("/govtrack/status/stream")
@login_required
def govtrack_status_stream() -> Response:
    """SSE 5초 간격 govtrack status push (F04 AC-G3, TP-011 AC-2).

    첫 이벤트는 즉시 전송하고 이후 5초 간격.
    클라이언트 연결 종료 시 GeneratorExit / BrokenPipeError로 자연 종료.
    """
    reader = _get_govtrack_reader()

    def generate():
        while True:
            status = reader.latest()
            data = json.dumps(_status_to_dict(status), ensure_ascii=False, default=str)
            yield f"event: status\ndata: {data}\n\n"
            time.sleep(_SSE_INTERVAL_SECS)

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ─────────────────────────────────────────────────
# W16 — 관리자 로그 뷰어 (TP-015)
# ─────────────────────────────────────────────────

# 알려진 시크릿 패턴 마스킹 (S7). key=value 형식에서 value를 **** 로 치환.
# Bearer 토큰 형태: "Authorization: Bearer <token>" — "Bearer " 접두어 포함 값을 가림.
_SECRET_PATTERN = re.compile(
    r"(?i)(password|token|secret|api_key|apikey|authorization)\s*[=:]\s*(?:Bearer\s+)?\S+",
    re.IGNORECASE,
)


def _mask_secrets(text: str) -> str:
    """알려진 시크릿 키 패턴을 마스킹한다 (S7 — 로그 노출 방어).

    지원 형태:
      password=hunter2          → password=****
      api_key=ABCDEF123         → api_key=****
      Authorization: Bearer secrettoken123  → Authorization=****
    """
    return _SECRET_PATTERN.sub(lambda m: m.group(1) + "=****", text)


@bp.get("/logs")
@login_required
def logs_view() -> str:
    """애플리케이션 로그 tail 뷰 (F04 §4.6, TP-015).

    쿼리:
      ?level=INFO   — 표준 레벨 화이트리스트 검증, 미인식 레벨은 None(전체) 처리.
      ?lines=200    — 정수, 2000 상한 (LogTailReader가 강제).

    경로 파라미터 없음 — ?file=... 같은 traversal 파라미터는 무시된다 (S3).
    파일 부재 시 빈 목록 + "로그 파일이 아직 없습니다" 안내.
    """
    config = current_app.config["BUSHEXA_CONFIG"]

    # level 파라미터 검증 (화이트리스트)
    level_raw = (request.args.get("level") or "").upper().strip()
    level = level_raw if level_raw in STANDARD_LEVELS else None

    # lines 파라미터 검증 (정수, 기본값 200)
    try:
        lines = max(1, int(request.args.get("lines", "200") or "200"))
    except (ValueError, TypeError):
        lines = 200

    # 고정 경로 — config.log_dir / "bushexa.log" 만 읽음 (path traversal 차단)
    reader = LogTailReader(config.log_dir)
    raw_lines = reader.tail(lines=lines, level=level)

    # 시크릿 마스킹 (S7) — 뷰 레이어에서 적용
    log_lines = [
        line.__class__(
            ts=line.ts,
            logger=line.logger,
            level=line.level,
            message=_mask_secrets(line.message),
            raw=_mask_secrets(line.raw),
        )
        for line in raw_lines
    ]

    return render_template(
        "admin/logs.html",
        log_lines=log_lines,
        level=level or "",
        lines=lines,
        log_file_path=str(reader.path),
    )


# ─────────────────────────────────────────────────
# 공휴일 관리 — /admin/holidays
# ─────────────────────────────────────────────────

def _holiday_editor() -> HolidayEditor:
    config = current_app.config["BUSHEXA_CONFIG"]
    return HolidayEditor(default_holidays_path(config.data_dir))


@bp.get("/holidays")
@login_required
def holidays_index() -> str:
    """관리자 지정 공휴일 목록."""
    editor = _holiday_editor()
    dates = sorted(editor.load())
    return render_template("admin/holidays.html", dates=dates)


@bp.post("/holidays/add")
@login_required
def holidays_add() -> Response:
    """날짜 추가 (YYYYMMDD)."""
    date_str = (request.form.get("date") or "").strip()
    editor = _holiday_editor()
    if not editor.add(date_str):
        flash(f"날짜 형식이 올바르지 않습니다: {date_str!r} (YYYYMMDD 형식 필요)", "error")
    else:
        flash(f"{date_str} 을 공휴일로 등록했습니다.", "success")
        _audit("holidays.add", date=date_str)
    return redirect(url_for("admin.holidays_index"))


@bp.post("/holidays/remove")
@login_required
def holidays_remove() -> Response:
    """날짜 제거."""
    date_str = (request.form.get("date") or "").strip()
    editor = _holiday_editor()
    if not editor.remove(date_str):
        flash(f"{date_str} 은 등록되지 않은 날짜입니다.", "error")
    else:
        flash(f"{date_str} 을 공휴일에서 제거했습니다.", "success")
        _audit("holidays.remove", date=date_str)
    return redirect(url_for("admin.holidays_index"))


# ─────────────────────────────────────────────────
# 변경이력(changelog) 관리 — /admin/changelog
# 편집본은 <data_dir>/changelog.json, seed는 static/data/changelog.json.
# ─────────────────────────────────────────────────

def _changelog_editor() -> ChangelogEditor:
    config = current_app.config["BUSHEXA_CONFIG"]
    # seed = info 페이지가 읽는 공장 초기값(static). current_app.root_path = bushexa/web.
    seed_path = Path(current_app.root_path) / "static" / "data" / "changelog.json"
    return ChangelogEditor(
        live_path=default_changelog_path(config.data_dir),
        seed_path=seed_path,
    )


@bp.get("/changelog")
@login_required
def changelog_index() -> str:
    """변경이력 목록 + 추가 폼. (날짜 오름차순)"""
    entries = _changelog_editor().load()
    return render_template("admin/changelog.html", entries=entries)


@bp.post("/changelog/add")
@login_required
def changelog_add() -> Response:
    """변경이력 항목 추가 (date=YYYY-MM-DD, description)."""
    date_str = (request.form.get("date") or "").strip()
    description = (request.form.get("description") or "").strip()
    if not _changelog_editor().add(date_str, description):
        flash("날짜(YYYY-MM-DD)와 설명을 올바르게 입력하세요.", "error")
    else:
        flash(f"{date_str} 변경이력을 추가했습니다.", "success")
    return redirect(url_for("admin.changelog_index"))


@bp.post("/changelog/remove")
@login_required
def changelog_remove() -> Response:
    """변경이력 항목 제거 (index = 표시 순서 기준)."""
    try:
        index = int(request.form.get("index", ""))
    except (TypeError, ValueError):
        index = -1
    if not _changelog_editor().remove(index):
        flash("해당 변경이력 항목을 찾을 수 없습니다.", "error")
    else:
        flash("변경이력 항목을 제거했습니다.", "success")
    return redirect(url_for("admin.changelog_index"))


# ─────────────────────────────────────────────────
# 특별 시간표 관리 — /admin/special
# ─────────────────────────────────────────────────

def _special_svc() -> SpecialTimetableService:
    config = current_app.config["BUSHEXA_CONFIG"]
    return SpecialTimetableService(
        map_path=default_special_path(config.data_dir),
        timetable_dir=timetable_dir(),
    )


def _require_valid_edition(edition_id: str) -> None:
    """에디션 ID가 화이트리스트 형식이 아니면 404."""
    import re as _re
    if not _re.match(r"^[A-Za-z0-9_-]{1,64}$", edition_id):
        abort(404)


@bp.get("/special")
@login_required
def special_index() -> str:
    """특별 시간표 에디션 목록 + 날짜 배정 현황."""
    svc = _special_svc()
    editions = svc.list_editions()
    mapping = svc.load_map()
    return render_template("admin/special_index.html", editions=editions, mapping=mapping)


def _load_special_edition_data(ed_dir) -> dict[str, dict]:
    """에디션 디렉터리에서 노선별 시간표를 읽어 {busno: timetable_data} dict 반환.

    파일이 없거나 파손된 노선은 빈 timetable_data로 채운다.
    """
    import json as _json
    from bushexa.data.timetable import get_busroute_info as _gbi
    busnos, departure_dict = _gbi()
    empty = lambda: {wd: {} for wd, _ in _WEEKDAY_TABS}
    result: dict[str, dict] = {}
    for bn in busnos:
        p = ed_dir / f"{bn}.json"
        if p.exists():
            try:
                result[bn] = _json.loads(p.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                result[bn] = empty()
        else:
            result[bn] = empty()
    return result


@bp.get("/special/<edition_id>")
@login_required
def special_edit(edition_id: str) -> str:
    """에디션 시간표 편집 화면."""
    _require_valid_edition(edition_id)
    svc = _special_svc()
    ed_dir = svc.edition_dir(edition_id)
    if ed_dir is None:
        abort(404)
    from bushexa.data.timetable import get_busroute_info as _gbi
    busnos, departure_dict = _gbi()
    busno_data = _load_special_edition_data(ed_dir) if svc.edition_exists(edition_id) else {
        bn: {wd: {} for wd, _ in _WEEKDAY_TABS} for bn in busnos
    }
    assignments = svc.assignments_for_edition(edition_id)
    return render_template(
        "admin/special_edit.html",
        edition_id=edition_id,
        busnos=busnos,
        departure_dict=departure_dict,
        busno_data=busno_data,
        weekday_tabs=_WEEKDAY_TABS,
        assignments=assignments,
        errors=None,
    )


@bp.post("/special/create")
@login_required
def special_create() -> Response:
    """새 에디션 생성 (빈 데이터로 초기화 후 편집 화면으로)."""
    edition_id = (request.form.get("edition_id") or "").strip()
    _require_valid_edition(edition_id)
    svc = _special_svc()
    ed_dir = svc.edition_dir(edition_id)
    if ed_dir is not None:
        ed_dir.mkdir(parents=True, exist_ok=True)
    flash(f"에디션 {edition_id!r} 을 생성했습니다. 시간표를 입력하세요.", "success")
    _audit("special.create", edition_id=edition_id)
    return redirect(url_for("admin.special_edit", edition_id=edition_id))


@bp.post("/special/<edition_id>")
@login_required
def special_save(edition_id: str) -> Response:
    """에디션 시간표 저장 (노선별 개별 저장).

    폼 구조:
      hidden ``busnos`` — 공백 구분 노선 목록
      hidden ``weekdays__{busno}`` — 공백 구분 weekday 키 목록 (각 노선)
      hidden ``departures__{busno}__{wd}`` — 공백 구분 출발지 목록
      textarea ``times__{busno}__{wd}__{dep}`` — 시각 목록 (줄바꿈/콤마 구분)
    """
    _require_valid_edition(edition_id)
    svc = _special_svc()
    ed_dir = svc.edition_dir(edition_id)
    if ed_dir is None:
        abort(404)
    ed_dir.mkdir(parents=True, exist_ok=True)

    busnos_raw = (request.form.get("busnos") or "").split()
    all_issues = []
    parsed_data: dict[str, dict] = {}  # busno → validated data
    for busno in busnos_raw:
        weekdays = (request.form.get(f"weekdays__{busno}") or "").split()
        data: dict = {}
        for wd in weekdays:
            deps = (request.form.get(f"departures__{busno}__{wd}") or "").split()
            data[wd] = {}
            for dep in deps:
                raw = request.form.get(f"times__{busno}__{wd}__{dep}", "")
                tokens = [t.strip() for t in raw.replace(",", "\n").splitlines()]
                data[wd][dep] = [t for t in tokens if t]
        issues = validate_timetable(data)
        if issues:
            all_issues.extend(issues)
        else:
            parsed_data[busno] = data

    # 검증 실패 시 디스크를 전혀 건드리지 않는다 (TP-009 §6 준용)
    if all_issues:
        from bushexa.data.timetable import get_busroute_info as _gbi
        busnos_all, departure_dict = _gbi()
        busno_data = _load_special_edition_data(ed_dir)
        assignments = svc.assignments_for_edition(edition_id)
        return render_template(
            "admin/special_edit.html",
            edition_id=edition_id,
            busnos=busnos_all,
            departure_dict=departure_dict,
            busno_data=busno_data,
            weekday_tabs=_WEEKDAY_TABS,
            assignments=assignments,
            errors=all_issues,
        ), 422
    # 모든 노선 검증 통과 후 일괄 저장 (원자성 보장)
    for busno, data in parsed_data.items():
        save_timetable(busno, data, dir=ed_dir, validate=False)

    flash(f"에디션 {edition_id!r} 시간표를 저장했습니다.", "success")
    _audit("special.save", edition_id=edition_id)
    return redirect(url_for("admin.special_edit", edition_id=edition_id))


@bp.post("/special/<edition_id>/assign")
@login_required
def special_assign(edition_id: str) -> Response:
    """날짜에 에디션 배정."""
    _require_valid_edition(edition_id)
    date_str = (request.form.get("date") or "").strip()
    svc = _special_svc()
    if not svc.assign(date_str, edition_id):
        flash(f"날짜 형식이 올바르지 않습니다: {date_str!r}", "error")
    else:
        flash(f"{date_str} 에 에디션 {edition_id!r} 을 배정했습니다.", "success")
        _audit("special.assign", edition_id=edition_id, date=date_str)
    return redirect(url_for("admin.special_edit", edition_id=edition_id))


@bp.post("/special/<edition_id>/unassign")
@login_required
def special_unassign(edition_id: str) -> Response:
    """날짜 배정 해제."""
    _require_valid_edition(edition_id)
    date_str = (request.form.get("date") or "").strip()
    svc = _special_svc()
    if not svc.unassign(date_str):
        flash(f"{date_str} 에는 이 에디션이 배정되지 않았습니다.", "error")
    else:
        flash(f"{date_str} 의 특별 시간표 배정을 해제했습니다.", "success")
        _audit("special.unassign", edition_id=edition_id, date=date_str)
    return redirect(url_for("admin.special_edit", edition_id=edition_id))


# ─────────────────────────────────────────────────
# 공휴일 API 클라이언트 — 테스트 주입 가능 (injectable)
# ─────────────────────────────────────────────────

def _get_holiday_client() -> HolidayClient:
    """HolidayClient 싱글턴 (테스트는 _HOLIDAY_CLIENT 키로 대역 주입 가능)."""
    injected = current_app.config.get("_HOLIDAY_CLIENT")
    if injected is not None:
        return injected
    config = current_app.config["BUSHEXA_CONFIG"]
    return HolidayClient(config.api_key)


# ─────────────────────────────────────────────────
# F1 — 특별 시간표 "그날 미리보기" /admin/special/preview
# ─────────────────────────────────────────────────

def _resolve_preview(target_date: date) -> tuple[str, str | None, dict]:
    """날짜 하나에 대해 적용 시간표를 결정하고 (label, edition_id, busno→times) 반환.

    반환값:
        label      — '특별편', '공휴일', '평일', '토요일', '일요일'
        edition_id — 특별편인 경우 에디션 ID, 아니면 None
        timetable  — {busno: {departure: [times]}} dict (화면 렌더링용)
    """
    from bushexa.data.timetable import get_busroute_info, get_timetable
    config = current_app.config["BUSHEXA_CONFIG"]

    # 1. 특별편 확인
    svc = _special_svc()
    date_str = target_date.strftime("%Y%m%d")
    edition_id = svc.get_edition_for_date(date_str)
    if edition_id and svc.edition_exists(edition_id):
        label = f"특별편 ({edition_id})"
        ed_dir = svc.edition_dir(edition_id)
        busnos, departure_dict = get_busroute_info()
        timetable: dict = {}
        for busno in busnos:
            deps = departure_dict.get(busno, [])
            timetable[busno] = {}
            for dep in deps:
                try:
                    times = get_timetable(busno, 0, dep, dir=ed_dir)
                except (FileNotFoundError, KeyError):
                    times = []
                timetable[busno][dep] = times
        return label, edition_id, timetable

    # 2. 공휴일/요일 분류
    holiday_editor = _holiday_editor()
    holiday_client = _get_holiday_client()
    holiday_cache = current_app.config.setdefault("_HOLIDAY_CACHE", {})
    holiday_set = get_effective_holiday_set(
        target_date,
        holiday_editor=holiday_editor,
        holiday_client=holiday_client,
        cache=holiday_cache,
    )

    # 요일 코드 결정
    from bushexa.time_utils import get_weekday as _get_weekday
    weekday_code = _get_weekday(target_date, holiday_set)

    if is_holiday(target_date, holiday_set):
        label = "공휴일 (일·공휴일 시간표)"
    else:
        _wd_labels = {0: "평일", 1: "토요일", 2: "일요일"}
        label = _wd_labels.get(weekday_code, "평일")

    busnos, departure_dict = get_busroute_info()
    timetable = {}
    for busno in busnos:
        deps = departure_dict.get(busno, [])
        timetable[busno] = {}
        for dep in deps:
            try:
                times = get_timetable(busno, weekday_code, dep)
            except (FileNotFoundError, KeyError):
                times = []
            timetable[busno][dep] = times

    return label, None, timetable


@bp.get("/special/preview")
@login_required
def special_preview() -> str:
    """특별 시간표 미리보기 — 특정 날짜에 실제로 적용될 시간표를 표시.

    ?date=YYYYMMDD 미지정 시 오늘(KST)이 기본값.
    우선순위: 특별편 > 공휴일 > 요일.
    """
    clock = KSTClock()
    today = clock.now().date()
    date_str = (request.args.get("date") or "").strip()

    if date_str:
        try:
            target_date = _parse_day(date_str)
        except ValueError:
            flash(f"날짜 형식이 올바르지 않습니다: {date_str!r} (YYYYMMDD 형식 필요)", "error")
            target_date = today
            date_str = today.strftime("%Y%m%d")
    else:
        target_date = today
        date_str = today.strftime("%Y%m%d")

    from bushexa.data.timetable import get_busroute_info
    busnos, departure_dict = get_busroute_info()

    label, edition_id, timetable = _resolve_preview(target_date)

    return render_template(
        "admin/special_preview.html",
        target_date=target_date,
        date_str=date_str,
        label=label,
        edition_id=edition_id,
        busnos=busnos,
        departure_dict=departure_dict,
        timetable=timetable,
        today_str=today.strftime("%Y%m%d"),
    )


# ─────────────────────────────────────────────────
# F2 — 공휴일 API 일괄 동기화 (2단계: fetch+preview → confirm)
# ─────────────────────────────────────────────────

@bp.post("/holidays/sync")
@login_required
def holidays_sync_fetch() -> str:
    """1단계: 연도 입력 → 12개월 API 조회 → 미리보기 렌더링.

    API 실패 시 500 없이 오류 메시지. 성공 시 미리보기 + confirm 폼.
    """
    year_raw = (request.form.get("year") or "").strip()
    try:
        year = int(year_raw)
        if not (2000 <= year <= 2099):
            raise ValueError(f"연도 범위 오류: {year}")
    except ValueError:
        flash(f"유효하지 않은 연도: {year_raw!r} (2000~2099 범위의 4자리 숫자 필요)", "error")
        return redirect(url_for("admin.holidays_index"))

    client = _get_holiday_client()
    fetched: list[str] = []
    fetch_error: str | None = None

    for month in range(1, 13):
        try:
            dates = client.fetch(year, month)
        except Exception as exc:
            fetch_error = f"{year}-{month:02d} 조회 오류: {exc}"
            break
        fetched.extend(d.strftime("%Y%m%d") for d in dates)

    if fetch_error:
        flash(f"공휴일 API 조회 실패: {fetch_error}", "error")
        return redirect(url_for("admin.holidays_index"))

    # 기존 등록 날짜와 비교: 신규/중복 분류
    existing = _holiday_editor().load()
    fetched_set = set(fetched)
    new_dates = sorted(fetched_set - existing)
    dup_dates = sorted(fetched_set & existing)

    return render_template(
        "admin/holidays_sync_preview.html",
        year=year,
        new_dates=new_dates,
        dup_dates=dup_dates,
        total_fetched=len(fetched_set),
    )


@bp.post("/holidays/sync/confirm")
@login_required
def holidays_sync_confirm() -> Response:
    """2단계: 미리보기 확인 후 병합 저장.

    폼에서 year와 new_dates(공백 구분 YYYYMMDD 목록)를 받아 기존 set과 union 후 저장.
    """
    year_raw = (request.form.get("year") or "").strip()
    new_dates_raw = (request.form.get("new_dates") or "").strip()

    try:
        year = int(year_raw)
    except ValueError:
        flash("잘못된 요청입니다.", "error")
        return redirect(url_for("admin.holidays_index"))

    new_dates = [d.strip() for d in new_dates_raw.split() if d.strip()]

    editor = _holiday_editor()
    existing = editor.load()
    merged = existing | set(new_dates)
    editor.save(merged)

    flash(f"{year}년 공휴일 {len(new_dates)}건을 동기화했습니다 (합계 {len(merged)}건).", "success")
    _audit("holidays.sync_confirm", year=year, added=len(new_dates), total=len(merged))
    return redirect(url_for("admin.holidays_index"))


# ─────────────────────────────────────────────────
# F5 — 감사 로그 헬퍼 및 기존 뮤테이션 라우트 훅
# ─────────────────────────────────────────────────

def _get_audit_log() -> AuditLog:
    """현재 앱의 AuditLog 인스턴스를 반환한다."""
    config = current_app.config["BUSHEXA_CONFIG"]
    clock = current_app.config.get("_AUDIT_CLOCK")  # 테스트 주입 가능
    return AuditLog(default_audit_path(config.data_dir), clock=clock)


def _audit(action: str, **details) -> None:
    """감사 로그에 best-effort 기록. 실패해도 상위 흐름을 중단하지 않는다."""
    try:
        _get_audit_log().record(action, actor_ip=request.remote_addr, **details)
    except Exception as exc:
        log.error("audit 기록 오류 (action=%s): %s", action, exc)


# ─────────────────────────────────────────────────
# F5 — 감사 로그 뷰 /admin/audit
# ─────────────────────────────────────────────────

@bp.get("/audit")
@login_required
def audit_index() -> str:
    """감사 로그 뷰 — 최신순 500건."""
    entries = _get_audit_log().load(limit=500)
    return render_template("admin/audit.html", entries=entries)


# ─────────────────────────────────────────────────
# F3 — 설정 백업/복구 /admin/backup
# ─────────────────────────────────────────────────

def _backup_roots() -> tuple[Path, Path]:
    """(data_dir, timetable_base_dir) 반환."""
    config = current_app.config["BUSHEXA_CONFIG"]
    return Path(config.data_dir), timetable_dir()


@bp.get("/backup")
@login_required
def backup_index() -> str:
    """백업/복구 화면."""
    return render_template("admin/backup.html")


@bp.get("/backup/export")
@login_required
def backup_export():
    """현재 설정을 ZIP으로 다운로드."""
    from datetime import datetime as _dt
    data_dir, tt_dir = _backup_roots()
    try:
        zip_bytes = create_backup_zip(data_dir, tt_dir)
    except Exception as exc:
        log.error("backup export 실패: %s", exc, exc_info=True)
        flash(f"백업 생성 실패: {exc}", "error")
        return redirect(url_for("admin.backup_index"))

    ts = _dt.now().strftime("%Y%m%d_%H%M%S")
    filename = f"bushexa_config_{ts}.zip"
    _audit("backup.export", filename=filename)
    return Response(
        zip_bytes,
        mimetype="application/zip",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@bp.post("/backup/import/preview")
@login_required
def backup_import_preview():
    """1단계: 업로드 검증 → 파일 목록 미리보기 (확인 폼)."""
    import base64
    import io as _io
    import zipfile as _zf

    from bushexa.services.backup import _is_safe_path, _MANIFEST

    uploaded = request.files.get("bundle")
    if not uploaded or not uploaded.filename:
        flash("ZIP 파일을 선택하세요.", "error")
        return redirect(url_for("admin.backup_index"))

    zip_bytes = uploaded.read()

    # 빠른 검증 — 실제 복구는 confirm에서만
    try:
        with _zf.ZipFile(_io.BytesIO(zip_bytes), "r") as zfobj:
            names = zfobj.namelist()
    except _zf.BadZipFile:
        flash("업로드된 파일이 유효한 ZIP 아카이브가 아닙니다.", "error")
        return redirect(url_for("admin.backup_index"))

    bad_paths = [n for n in names if not _is_safe_path(n)]
    if bad_paths:
        flash(f"허용되지 않은 경로가 포함되어 있습니다: {bad_paths[:3]}", "error")
        return redirect(url_for("admin.backup_index"))

    # 미리보기 — ZIP 내용을 세션에 넣기엔 크기가 커서, base64 인코딩해 폼에 전달
    encoded = base64.b64encode(zip_bytes).decode("ascii")
    preview_files = [n for n in names if n != _MANIFEST]

    return render_template(
        "admin/backup_preview.html",
        preview_files=preview_files,
        encoded_bundle=encoded,
    )


@bp.post("/backup/import/confirm")
@login_required
def backup_import_confirm():
    """2단계: 미리보기 확인 후 실제 복구."""
    import base64
    encoded = request.form.get("encoded_bundle", "")
    if not encoded:
        flash("복구 데이터가 없습니다. 다시 시도하세요.", "error")
        return redirect(url_for("admin.backup_index"))

    try:
        zip_bytes = base64.b64decode(encoded)
    except Exception:
        flash("복구 데이터가 손상되었습니다.", "error")
        return redirect(url_for("admin.backup_index"))

    data_dir, tt_dir = _backup_roots()
    try:
        restored = validate_and_restore(zip_bytes, data_dir, tt_dir)
    except RestoreError as exc:
        flash(f"복구 실패: {exc}", "error")
        return redirect(url_for("admin.backup_index"))
    except Exception as exc:
        log.error("backup restore 예외: %s", exc, exc_info=True)
        flash(f"복구 중 오류가 발생했습니다: {exc}", "error")
        return redirect(url_for("admin.backup_index"))

    _audit("backup.restore", restored_count=len(restored), files=restored[:10])
    flash(f"복구 완료: {len(restored)}개 파일 복원됨.", "success")
    return redirect(url_for("admin.backup_index"))


# ─────────────────────────────────────────────────
# F4 — 워커 상태 대시보드 /admin/worker-status
# ─────────────────────────────────────────────────

_STALE_SECS = 60  # 마지막 사이클이 이 초보다 오래되면 "stale" 경고


def _get_arrival_reader() -> ArrivalStatusReader:
    config = current_app.config["BUSHEXA_CONFIG"]
    return ArrivalStatusReader(Path(config.data_dir) / "arrival_status.json")


def _seconds_since(iso_ts: str | None, clock: KSTClock) -> float | None:
    """ISO8601 타임스탬프와 현재 시각의 차이(초)를 반환. None이면 None."""
    if not iso_ts:
        return None
    try:
        from datetime import datetime as _dt
        ts = _dt.fromisoformat(iso_ts)
        now = clock.now()
        diff = (now - ts).total_seconds()
        return diff
    except Exception:
        return None


@bp.get("/worker-status")
@login_required
def worker_status() -> str:
    """govtrack + arrival 데몬 상태 대시보드."""
    clock = KSTClock()

    govtrack_reader = _get_govtrack_reader()
    govtrack = govtrack_reader.latest()

    arrival_reader = _get_arrival_reader()
    arrival = arrival_reader.latest()

    govtrack_stale = False
    if govtrack:
        diff = _seconds_since(govtrack.cycle_started_at, clock)
        govtrack_stale = diff is not None and diff > _STALE_SECS

    arrival_stale = False
    if arrival:
        diff = _seconds_since(arrival.cycle_started_at, clock)
        arrival_stale = diff is not None and diff > _STALE_SECS

    return render_template(
        "admin/worker_status.html",
        govtrack=govtrack,
        govtrack_stale=govtrack_stale,
        arrival=arrival,
        arrival_stale=arrival_stale,
    )

