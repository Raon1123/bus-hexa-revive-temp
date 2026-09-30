"""관리자 — 철도·KTX 연계 운영 (/admin/rail): 철도 시간표 상태·재수집, 연계표 환승 기본값, 구간 소요 프로필.

긴 작업은 RecrawlJob 백그라운드 + ``/admin/rail/job/<kind>`` 폴링(SSE 로 sync 워커를 붙잡지 않음).
라우트는 admin.bp 에 붙는다(admin.py 끝에서 import).
"""
from __future__ import annotations

from pathlib import Path

from flask import current_app, flash, jsonify, redirect, render_template, request, url_for

from bushexa.data.constants import KTX_LEG_LABELS, KTX_LEG_REAL_MIN_N, KTX_TRANSFER_MAX_MIN
from bushexa.services.holiday_service import read_effective_holidays
from bushexa.services.ktx_settings import KtxSettingsStore, default_ktx_settings_path
from bushexa.services.leg_profile import (
    candidate_profile_path,
    compare_profiles,
    default_profile_path,
    load_profile,
    merge_profiles,
    previous_profile_path,
    promote_profile,
    rollback_profile,
)
from bushexa.services.rail_status import summarize_rail_store
from bushexa.services.rail_timetable import RAIL_HORIZON_DAYS, default_rail_path, load_rail_store
from bushexa.services.recrawl_job import ConflictError, RecrawlJob
from bushexa.time_utils import KSTClock
from bushexa.web.routes.admin import _audit, bp, login_required

_JOB_KEYS = {"rail": "_RAIL_CRAWL_JOB", "profile": "_KTX_PROFILE_JOB"}
_LEG_5001 = ("l5001_station_jinmok", "l5001_origin_jinmok", "l5001_jinmok_station")


def _config():
    return current_app.config["BUSHEXA_CONFIG"]


def _tsv_path() -> Path:
    from bushexa.crawler.daemon import resolve_tsv_path
    return resolve_tsv_path(data_dir=_config().data_dir)


# ── 잡 함수 ──────────────────────────────────────────────────────────────────

def _rail_crawl_fn(config):
    """TAGO 열차·동해선 시간표 재수집(= CLI crawl-rail). 실패한 날짜·정차역은 기존 값 유지."""
    def run(*, vacation: bool, on_progress, days: int = RAIL_HORIZON_DAYS) -> None:
        from bushexa.api_clients.tago_rail import SubwayInfoClient, TrainInfoClient
        from bushexa.services.rail_timetable import refresh_metro, refresh_trains

        path = default_rail_path(config.data_dir)
        trains = refresh_trains(TrainInfoClient(config.api_key), path, days=days,
                                holiday_set=read_effective_holidays(config.data_dir),
                                on_progress=on_progress)
        metro = refresh_metro(SubwayInfoClient(config.api_key), path, on_progress=on_progress)
        failed = trains.failed + metro.failed
        on_progress({"stage": "summary", "ok": not failed,
                     "label": f"열차 {trains} / 동해선 {metro}"
                              + (f" — 실패(기존 유지): {', '.join(failed[:6])}" if failed else "")})
    return run


def _profile_fn(config):
    """운영 운행 기록(bus_timelog[+logs.tsv])으로 후보 프로필을 계산해 후보 파일에 쓴다."""
    def run(*, vacation: bool, on_progress, use_tsv: bool = False) -> None:
        from bushexa.crawler.daemon import resolve_tsv_path
        from bushexa.services.leg_profile import (
            build_leg_profile,
            collect_passages,
            holidays_for_span,
            save_profile,
        )

        tsv = resolve_tsv_path(data_dir=config.data_dir)
        passages, sources = collect_passages(
            db_url=config.database_url, tsv_paths=[tsv] if use_tsv and tsv.exists() else [],
            on_progress=on_progress)
        if not passages:
            raise RuntimeError("대상 노선 통과기록이 없습니다 — 후보를 만들지 않았습니다")
        holidays = holidays_for_span(passages, read_effective_holidays(config.data_dir))
        profile = build_leg_profile(passages, holidays, generated_at=KSTClock().now().isoformat(),
                                    sources=sources)
        save_profile(candidate_profile_path(config.data_dir), profile)
        on_progress({"stage": "summary", "ok": True,
                     "label": f"후보 프로필: 통과기록 {len(passages)}건, 기간 {profile['period']}"})
    return run


def _job(kind: str) -> RecrawlJob:
    """app-scope 잡(테스트는 mock 을 미리 주입할 수 있다)."""
    key = _JOB_KEYS[kind]
    job = current_app.config.get(key)
    if job is None:
        config = _config()
        fn = _rail_crawl_fn(config) if kind == "rail" else _profile_fn(config)
        name = "rail_crawl" if kind == "rail" else "ktx_profile"
        job = RecrawlJob(fn, data_dir=Path(config.data_dir), name=name)
        current_app.config[key] = job
    return job


def _snapshot(kind: str) -> dict:
    try:
        return _job(kind).snapshot()
    except Exception as exc:  # 상태 파일이 깨져도 화면은 뜬다
        current_app.logger.warning("잡 스냅샷 실패(%s): %s", kind, exc)
        return {"running": False, "events": [], "error": None, "done": False, "job_id": None}


# ── 화면 ─────────────────────────────────────────────────────────────────────

def _real_5001(profile: dict | None) -> list[dict]:
    """5001 구간별 요일구분 실측 표본 수와 근사 탈출 기준."""
    out = []
    for leg in _LEG_5001:
        days = {}
        for day in ("0", "1", "2"):
            try:
                days[day] = int(profile["legs"][leg]["by_day"][day]["all"]["n"])
            except (KeyError, TypeError, ValueError):
                days[day] = 0
        out.append({"leg": leg, "days": days,
                    "real": {d: n >= KTX_LEG_REAL_MIN_N for d, n in days.items()}})
    return out


@bp.get("/rail")
@login_required
def rail_index() -> str:
    """철도·KTX 연계 운영 화면."""
    config = _config()
    today = KSTClock().now().date()
    store = load_rail_store(default_rail_path(config.data_dir))
    current = load_profile(default_profile_path(config.data_dir))
    candidate = load_profile(candidate_profile_path(config.data_dir))
    settings = KtxSettingsStore(default_ktx_settings_path(config.data_dir))
    tsv = _tsv_path()
    return render_template(
        "admin/rail.html",
        rail=summarize_rail_store(store, today), today=today.isoformat(),
        rail_job=_snapshot("rail"), profile_job=_snapshot("profile"),
        horizon=RAIL_HORIZON_DAYS,
        settings=settings.effective(), settings_saved=settings.load(), transfer_max=KTX_TRANSFER_MAX_MIN,
        current=current, candidate=candidate,
        compare=compare_profiles(current, candidate) if candidate else compare_profiles(current, None),
        has_prev=previous_profile_path(config.data_dir).exists(),
        real_5001=_real_5001(current), real_min=KTX_LEG_REAL_MIN_N,
        leg_labels=KTX_LEG_LABELS, tsv_exists=tsv.exists(),
        tsv_size_mb=round(tsv.stat().st_size / 1e6, 1) if tsv.exists() else None,
    )


@bp.get("/rail/job/<kind>")
@login_required
def rail_job_status(kind: str):
    """잡 스냅샷 JSON(화면이 몇 초마다 GET)."""
    if kind not in _JOB_KEYS:
        return jsonify({"error": "unknown job"}), 404
    return jsonify(_snapshot(kind))


# ── 철도 시간표 재수집 ────────────────────────────────────────────────────────

@bp.post("/rail/recrawl")
@login_required
def rail_recrawl():
    """crawl-rail 백그라운드 시작. 이미 돌고 있으면 409 대신 안내 flash."""
    try:
        days = int(request.form.get("days") or RAIL_HORIZON_DAYS)
    except ValueError:
        days = RAIL_HORIZON_DAYS
    days = max(1, min(RAIL_HORIZON_DAYS, days))
    try:
        _job("rail").start(days=days)
    except ConflictError:
        flash("철도 시간표 재수집이 이미 진행 중입니다.", "error")
        return redirect(url_for("admin.rail_index"))
    _audit("rail.recrawl", days=days)
    flash(f"철도 시간표 재수집을 시작했습니다({days}일치, 몇 분 걸립니다). 실패한 날짜는 기존 값을 유지합니다.",
          "success")
    return redirect(url_for("admin.rail_index") + "#rail-job")


# ── 연계표 기본 환승 최소 시간 ────────────────────────────────────────────────

@bp.post("/rail/settings")
@login_required
def rail_settings_save():
    """환승 최소 시간 기본값 저장(빈 값 → 코드 기본값)."""
    store = KtxSettingsStore(default_ktx_settings_path(_config().data_dir))
    try:
        saved = store.save(transfer_station_min=request.form.get("transfer_station_min"),
                           transfer_jinmok_min=request.form.get("transfer_jinmok_min"))
    except ValueError as exc:
        flash(f"입력값 오류: {exc}", "error")
        return redirect(url_for("admin.rail_index") + "#ktx-settings")
    _audit("ktx_settings.save", **saved)
    flash("KTX 연계표 기본 환승 최소 시간을 저장했습니다. /ktx 에 바로 적용됩니다.", "success")
    return redirect(url_for("admin.rail_index") + "#ktx-settings")


# ── 구간 소요 프로필 ─────────────────────────────────────────────────────────

@bp.post("/rail/profile/rebuild")
@login_required
def rail_profile_rebuild():
    """운영 운행 기록으로 후보 프로필 계산(백그라운드). 현재 프로필은 건드리지 않는다."""
    use_tsv = request.form.get("use_tsv", "").lower() in ("on", "true", "1", "yes")
    try:
        _job("profile").start(use_tsv=use_tsv)
    except ConflictError:
        flash("구간 소요 재계산이 이미 진행 중입니다.", "error")
        return redirect(url_for("admin.rail_index") + "#ktx-profile")
    _audit("ktx_profile.rebuild", use_tsv=use_tsv)
    flash("운행 기록으로 후보 프로필을 계산하고 있습니다. 끝나면 비교표가 나옵니다.", "success")
    return redirect(url_for("admin.rail_index") + "#ktx-profile")


@bp.post("/rail/profile/apply")
@login_required
def rail_profile_apply():
    """후보 적용 — merge(구간·요일별로 표본 많은 쪽, 기본) 또는 replace(후보로 통째 교체)."""
    data_dir = _config().data_dir
    candidate = load_profile(candidate_profile_path(data_dir))
    if candidate is None:
        flash("적용할 후보 프로필이 없습니다.", "error")
        return redirect(url_for("admin.rail_index") + "#ktx-profile")
    mode = "replace" if request.form.get("mode") == "replace" else "merge"
    if mode == "merge":
        profile, choices = merge_profiles(load_profile(default_profile_path(data_dir)), candidate)
        picked = sum(1 for days in choices.values() for c in days.values() if c == "candidate")
    else:
        profile, picked = candidate, None
    promote_profile(data_dir, profile)
    _audit("ktx_profile.apply", mode=mode, picked=picked, period=profile.get("period"))
    flash("구간 소요 프로필을 적용했습니다(" + ("구간·요일별 표본 많은 쪽 병합" if mode == "merge" else "후보로 교체")
          + "). 이전 값은 '되돌리기'로 복구할 수 있습니다.", "success")
    return redirect(url_for("admin.rail_index") + "#ktx-profile")


@bp.post("/rail/profile/discard")
@login_required
def rail_profile_discard():
    candidate_profile_path(_config().data_dir).unlink(missing_ok=True)
    _audit("ktx_profile.discard")
    flash("후보 프로필을 버렸습니다.", "success")
    return redirect(url_for("admin.rail_index") + "#ktx-profile")


@bp.post("/rail/profile/rollback")
@login_required
def rail_profile_rollback():
    if not rollback_profile(_config().data_dir):
        flash("되돌릴 이전 프로필이 없습니다.", "error")
    else:
        _audit("ktx_profile.rollback")
        flash("이전 구간 소요 프로필로 되돌렸습니다(한 번 더 누르면 다시 돌아옵니다).", "success")
    return redirect(url_for("admin.rail_index") + "#ktx-profile")
