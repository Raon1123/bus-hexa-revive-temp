"""bushexa command-line interface.

전 서브커맨드 배선 완료:

* ``serve``              -> P4/P5 (gunicorn 운영, --dev 시 Werkzeug)
* ``crawl-once``         -> P2 (1회 폴링, --route/--dry-run)
* ``crawl-loop``         -> P2 (govtrack 데몬, PM-001 수정) --poll/--night-sleep
* ``arrival-loop``       -> P2 / ADR-010 (울산 도착 캐시 poller)
* ``cache-refresh-loop`` -> 유휴 윈도(02–03시) 공휴일·시간표 재크롤 워커
* ``init-db``            -> 스키마 생성(--reset 시 bus_timelog 비움)
* ``crawl-timetable``    -> P2 / F10 (시간표 재크롤)
* ``crawl-rail``         -> 부산 루트 철도(열차·동해선) 시간표 즉시 갱신
* ``debug-running``      -> F05 운행 재구성 진단 (제외 정류장·분리·덮어쓰기 출력)
* ``build-leg-profile``  -> 통과기록 → 513 구간 소요 프로필(ktx_leg_profile.json, /ktx 입력)
* ``ktx-connections``    -> 요일별 KTX↔513 연계표 출력(로컬 파일만, 네트워크 없음)

설계(F09 §4.1)에 맞춰 ``crawl-loop``의 폴링 인자는 ``--poll``(기본 15초, 2026-06-06 10→15
상향 — admin 크롤 주기 설정이 런타임 우선)이다. 신호 핸들러는
메인 스레드에서만 등록하고, 데몬 루프는 stop_event로 graceful 종료한다.
"""

from __future__ import annotations

import argparse


def _load_config():
    from bushexa.config import AppConfig

    return AppConfig.from_env()


def cmd_init_db(args) -> int:
    from bushexa.db.connection import create_connection
    from bushexa.db.schema import create_schema

    config = _load_config()
    conn = create_connection(config.database_url)
    create_schema(conn)
    if getattr(args, "reset", False):
        cur = conn.cursor()
        cur.execute("DELETE FROM bus_timelog")
        conn.commit()
        print("bus_timelog 비움 (--reset)")
    print("스키마 생성 완료")
    return 0


def cmd_crawl_once(args, *, recorder=None) -> int:
    from bushexa.crawler.daemon import build_recorder, crawl_once
    from bushexa.logging_setup import setup_logging

    # config을 먼저 로드해 log_level/log_dir를 확보한 뒤 로깅 설정 —
    # 역할별 파일(LOG_SOURCES "crawl")로 분리해 회전 경합 방지 + 관리자 로그 뷰 소스 일치.
    config = _load_config()
    setup_logging(level=config.log_level, log_dir=config.log_dir, filename="bushexa-crawl.log")
    if recorder is None:
        recorder = build_recorder(config)
    stats = crawl_once(recorder, args.route, dry_run=args.dry_run)
    print(f"route={stats.route_id} api_ok={stats.api_ok} parsed={stats.parsed_count} "
          f"inserts={stats.inserts} unchanged={stats.skipped_unchanged} "
          f"untracked={stats.skipped_unknown_stop} vehicle_errors={stats.vehicle_errors}"
          + (" [dry-run]" if args.dry_run else ""))
    return 0


def cmd_crawl_loop(args) -> int:
    import signal
    import threading
    from pathlib import Path

    from bushexa.crawler.daemon import run_daemon
    from bushexa.logging_setup import setup_logging
    from bushexa.services.govtrack_status import GovtrackStatusWriter

    # 역할별 파일(LOG_SOURCES "crawl")로 분리해 회전 경합 방지 + 관리자 로그 뷰 소스 일치.
    config = _load_config()
    setup_logging(level=config.log_level, log_dir=config.log_dir, filename="bushexa-crawl.log")
    stop = threading.Event()
    # SIGTERM/SIGINT은 메인 스레드에서만 등록 가능 — 데몬 루프는 stop_event를 폴링한다.
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_a: stop.set())
    # 매 사이클 결과를 status에 기록 → 관리자(F04)가 데몬 건강도 조회(EC-7).
    writer = GovtrackStatusWriter(Path(config.data_dir) / "govtrack_status.json")
    run_daemon(config, poll_seconds=args.poll, night_sleep_seconds=args.night_sleep,
               stop_event=stop, on_cycle=writer.write)
    return 0


def cmd_arrival_loop(args) -> int:
    import signal
    import threading
    from pathlib import Path

    from bushexa.crawler.arrival_poller import run_arrival_poller
    from bushexa.logging_setup import setup_logging
    from bushexa.services.arrival_status import ArrivalStatusWriter

    # 역할별 파일(LOG_SOURCES "arrival")로 분리해 회전 경합 방지 + 관리자 로그 뷰 소스 일치.
    config = _load_config()
    setup_logging(level=config.log_level, log_dir=config.log_dir, filename="bushexa-arrival.log")
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_a: stop.set())
    # 매 사이클 결과를 status에 기록 → 관리자(F04)가 데몬 건강도 조회.
    writer = ArrivalStatusWriter(Path(config.data_dir) / "arrival_status.json")
    run_arrival_poller(config, poll_seconds=args.poll, stop_event=stop,
                       status_writer=writer)
    return 0


def cmd_cache_refresh_loop(args) -> int:
    import signal
    import threading

    from bushexa.crawler.cache_refresh import run_cache_refresh_loop
    from bushexa.logging_setup import setup_logging

    # 역할별 파일(LOG_SOURCES "cache")로 분리해 회전 경합 방지 + 관리자 로그 뷰 소스 일치.
    config = _load_config()
    setup_logging(level=config.log_level, log_dir=config.log_dir, filename="bushexa-cache.log")
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_a: stop.set())
    run_cache_refresh_loop(config, check_seconds=args.check,
                           run_on_start=not args.no_run_on_start, stop_event=stop)
    return 0


def cmd_crawl_timetable(args) -> int:
    from bushexa.api_clients.ulsan_bis import UlsanBisClient
    from bushexa.crawler.timetable_crawl import TimetableCrawlError, crawl_all_timetables
    from bushexa.logging_setup import setup_logging

    # 역할별 파일(LOG_SOURCES "crawl")로 분리해 회전 경합 방지 + 관리자 로그 뷰 소스 일치.
    config = _load_config()
    setup_logging(level=config.log_level, log_dir=config.log_dir, filename="bushexa-crawl.log")
    client = UlsanBisClient(config.api_key)

    def _on_progress(ev) -> None:
        print(f"  route={ev.route} day={ev.day} page={ev.page}")

    try:
        written = crawl_all_timetables(client, vacation=args.vacation, on_progress=_on_progress)
    except TimetableCrawlError as exc:  # 부분 실패 — 성공 노선은 이미 기록됨(ADR-013 격리)
        print(f"시간표 {len(exc.written)}개 노선 갱신: {', '.join(sorted(exc.written))}")
        print(f"실패 {len(exc.failed)}개 노선(기존 파일 보존): {', '.join(sorted(exc.failed))}")
        return 1
    print(f"시간표 {len(written)}개 노선 갱신: {', '.join(written)}")
    return 0


def cmd_crawl_rail(args) -> int:
    """TAGO 열차·동해선 시간표를 즉시 받아 ``rail_timetable.json`` 에 병합(워커와 같은 규칙)."""
    from bushexa.api_clients.tago_rail import SubwayInfoClient, TrainInfoClient
    from bushexa.logging_setup import setup_logging
    from bushexa.services.rail_timetable import (
        default_rail_path,
        refresh_metro,
        refresh_trains,
    )

    config = _load_config()
    setup_logging(level=config.log_level, log_dir=config.log_dir, filename="bushexa-crawl.log")
    path = default_rail_path(config.data_dir)
    from bushexa.services.holiday_service import read_effective_holidays

    kwargs = {} if args.days is None else {"days": args.days}
    trains = refresh_trains(TrainInfoClient(config.api_key), path,
                            holiday_set=read_effective_holidays(config.data_dir), **kwargs)
    print(f"열차 시간표: {trains}")
    metro = refresh_metro(SubwayInfoClient(config.api_key), path)
    print(f"동해선 시간표: {metro}")
    for label in trains.failed + metro.failed:
        print(f"  실패(기존 유지): {label}")
    return 1 if trains.failed or metro.failed else 0


def cmd_build_leg_profile(args) -> int:
    """통과기록(TSV·DB) → 513 구간 소요 프로필 ``ktx_leg_profile.json``(요일별 KTX 연계표 입력)."""
    from pathlib import Path

    from bushexa.services.leg_profile import (
        build_leg_profile,
        collect_passages,
        default_profile_path,
        holidays_for_span,
        save_profile,
    )
    from bushexa.services.holiday_service import read_effective_holidays
    from bushexa.time_utils import KSTClock

    passages, sources = collect_passages(
        db_url=args.db, tsv_paths=args.tsv or [],
        on_progress=lambda e: print(f"  {e['label']}"))
    if not passages:
        print("통과기록이 없습니다 — --tsv 또는 --db 를 지정하세요(기존 프로필은 그대로 둡니다).")
        return 1

    config = _load_config()
    holidays = holidays_for_span(passages, read_effective_holidays(config.data_dir))
    profile = build_leg_profile(passages, holidays, generated_at=KSTClock().now().isoformat(),
                                sources=sources)
    for name, leg in profile["legs"].items():
        cells = [f"{d}:{v['all']['p50']}분(n={v['all']['n']})" for d, v in leg["by_day"].items()]
        print(f"  {name:15s} " + "  ".join(cells))
    out = Path(args.out) if args.out else default_profile_path(config.data_dir)
    save_profile(out, profile)
    print(f"저장: {out} (기간 {profile['period']})")
    return 0


def cmd_ktx_connections(args) -> int:
    """요일별 KTX 연계표를 로컬 파일만으로 만들어 출력(네트워크 없음)."""
    import dataclasses
    import json

    from bushexa.domain.ktx_connect import Transfers
    from bushexa.services.holiday_service import read_effective_holidays
    from bushexa.services.ktx_connections import build_connect_table
    from bushexa.time_utils import KSTClock

    config = _load_config()
    today = KSTClock().now().date()
    holidays = read_effective_holidays(config.data_dir)
    from bushexa.services.ktx_settings import KtxSettingsStore, default_ktx_settings_path

    saved = KtxSettingsStore(default_ktx_settings_path(config.data_dir)).effective()
    transfers = Transfers(
        station=saved["transfer_station_min"] if args.transfer_station is None else args.transfer_station,
        jinmok=saved["transfer_jinmok_min"] if args.transfer_jinmok is None else args.transfer_jinmok)
    table, errors, _ = build_connect_table(config, today, holidays, direction=args.dir,
                                           dest=args.to, day=args.day, transfers=transfers)
    if args.json:
        data = dataclasses.asdict(table)
        data["ref_date"] = table.ref_date.isoformat() if table.ref_date else None
        print(json.dumps(data, ensure_ascii=False, indent=1))
        return 0
    print(f"{args.dir} {args.to} day={args.day} 기준일={table.ref_date} 철도={table.rail_state} "
          f"버스={table.bus_state} 소요={table.profile_state} 5001={table.alt_state}"
          f"{'(근사)' if table.alt_proxied else ''} 환승={transfers.station}/{transfers.jinmok}분 "
          f"제외={table.skipped}편")
    for e in errors:
        print(f"  오류: {e}")
    for r in table.rows:
        mark = " (빠듯)" if r.tight else ""
        a = r.alt
        amark = " (빠듯)" if a and a.tight else ""
        if args.dir == "out":
            print(f"  {r.grade} {r.train_dep}→{r.train_arr}  최선={r.best or '-'}")
            if r.origin_dep:
                print(f"    ① 덕하 {r.origin_dep} → UNIST {r.unist_at} → 울산역 {r.station_at}"
                      f" 여유 {r.margin_min}분{mark}")
            if a:
                print(f"    ② UNIST {a.unist_dep}({a.feeder_no}) → 진목회관 {a.jinmok_arr} → 5001 {a.bus_dep}"
                      f" → 울산역 {a.station_at} 여유 {a.margin_min}분{amark}")
        else:
            print(f"  {r.grade} {r.train_dep}→울산 {r.train_arr}  최선={r.best or '-'}")
            if r.origin_dep:
                print(f"    ① 513 삼남 {r.origin_dep} → 울산역 {r.station_at} → UNIST {r.unist_at}"
                      f" 대기 {r.wait_min}분{mark}")
            if a:
                print(f"    ② 5001 {a.bus_dep} → 진목회관 {a.jinmok_arr} → {a.feeder_no} {a.feeder_dep}"
                      f" → UNIST {a.unist_at} 대기 {a.wait_min}분{amark}")
    return 0


def _parse_cli_date(value: str | None):
    """``YYYYMMDD``/``YYYY-MM-DD`` → date. 미지정 시 오늘(KST). 형식 오류는 argparse 에러."""
    from datetime import date

    from bushexa.time_utils import KSTClock

    if value is None:
        return KSTClock().now().date()
    digits = "".join(ch for ch in value if ch.isdigit())
    try:
        return date(int(digits[:4]), int(digits[4:6]), int(digits[6:8]))
    except (ValueError, IndexError):
        raise argparse.ArgumentTypeError(f"날짜 형식 오류: {value!r} (YYYY-MM-DD)")


def cmd_debug_running(args) -> int:
    """/running 과 같은 재구성을 수행하고 그리드에 드러나지 않는 과정을 출력한다."""
    from pathlib import Path

    from bushexa.data.constants import STOP_IDS, TRACKED_ROUTES
    from bushexa.db.connection import _sqlite_path, create_connection, is_sqlite
    from bushexa.db.repo import BusLogRepo
    from bushexa.domain.running import explain_runs

    if args.route not in TRACKED_ROUTES:
        print(f"알 수 없는 노선 ID: {args.route!r}. 사용 가능:")
        for rid, info in TRACKED_ROUTES.items():
            print(f"  {rid}  {info[0]}번 {info[1]}행")
        return 2
    try:
        day = _parse_cli_date(args.date)
    except argparse.ArgumentTypeError as exc:
        print(exc)
        return 2

    # --db 지정 시 config(API 키 등) 없이 스냅샷 DB만으로 동작
    dsn = args.db or _load_config().database_url
    # sqlite3.connect는 없는 파일을 빈 DB로 만들어 버리므로 경로 오타를 먼저 걸러낸다.
    if is_sqlite(dsn) and _sqlite_path(dsn) != ":memory:" and not Path(_sqlite_path(dsn)).exists():
        print(f"DB 파일 없음: {_sqlite_path(dsn)}")
        return 2
    conn = create_connection(dsn)
    with BusLogRepo(conn) as repo:
        rows = repo.get_by_route(args.route, day=day)
    ex = explain_runs(rows, args.route)

    busno, terminal, _dep, stops_order = TRACKED_ROUTES[args.route]

    print(f"route={args.route} ({busno}번 {terminal}행) date={day.isoformat()} "
          f"rows={ex.total_rows} runs={len(ex.runs)}")

    print(f"\n[제외] 노선 정류장 목록에 없는 stop_id: "
          f"{sum(d.count for d in ex.dropped_stops)}행")
    for d in ex.dropped_stops:
        print(f"  {d.stop_id}  {d.stop_name or '-'}  x{d.count}")

    if ex.unparsable_idx:
        print(f"\n[제외] 파싱 불가 idx: {len(ex.unparsable_idx)}행")
        for idx in ex.unparsable_idx[:10]:
            print(f"  {idx!r}")

    print(f"\n[운행] {len(ex.runs)}회 (그리드 열 순서)")
    for i, run in enumerate(ex.runs, 1):
        times = sorted(run.stops.values())
        print(f"  #{i:<3} {run.vehicle_no}  {times[0]}–{times[-1]}  "
              f"{len(run.stops)}/{len(stops_order)} 정류장")
        if args.verbose:
            for sid in stops_order:
                print(f"         {run.stops.get(sid, 'レ'):>5}  {STOP_IDS.get(sid, sid)}")

    print(f"\n[분리] 간격 초과로 나뉜 지점: {len(ex.splits)}")
    for s in ex.splits:
        print(f"  {s.vehicle_no}  {s.before_idx} → {s.after_idx}  ({s.gap_minutes:.0f}분)")

    print(f"\n[덮어쓰기] 같은 운행 내 재통과: {len(ex.overwrites)}")
    for o in ex.overwrites:
        print(f"  {o.vehicle_no}  {STOP_IDS.get(o.stop_id, o.stop_id)}  {o.dropped} → {o.kept}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Construct the argument parser with every subcommand registered."""
    parser = argparse.ArgumentParser(
        prog="bushexa",
        description="UNIST bus information system (web server + crawlers).",
    )
    sub = parser.add_subparsers(dest="command", required=True, metavar="<command>")

    p_serve = sub.add_parser("serve", help="Run the web server (gunicorn in production)")
    p_serve.add_argument("--host", default="0.0.0.0")
    p_serve.add_argument("--port", type=int, default=8000)
    p_serve.add_argument(
        "--workers", type=int, default=None,
        help="gunicorn 워커 수 (기본: $BUSHEXA_WEB_WORKERS 또는 2)",
    )
    p_serve.add_argument(
        "--dev", action="store_true",
        help="개발용 Werkzeug 서버(자동 리로드). 운영에서는 사용 금지.",
    )

    p_once = sub.add_parser("crawl-once", help="Run one govtrack crawl cycle and exit")
    p_once.add_argument("--route", required=True, help="TRACKED_ROUTES 키 (예: 195000177)")
    p_once.add_argument("--dry-run", action="store_true", help="INSERT 없이 결과만 출력")

    p_loop = sub.add_parser("crawl-loop", help="Run the govtrack crawl daemon")
    p_loop.add_argument("--poll", type=float, default=15.0,
                        help="버스 위치 폴링 간격 초 (default: 15)")
    p_loop.add_argument("--night-sleep", type=float, default=60.0,
                        help="새벽(01-05시) sleep 초 (default: 60)")

    p_arr = sub.add_parser(
        "arrival-loop", help="Poll Ulsan arrival info into the cache (ADR-010)"
    )
    p_arr.add_argument("--poll", type=float, default=7.0,
                       help="울산 도착정보 폴링 간격 초 (default: 7, 권장 5~10)")

    p_cache = sub.add_parser(
        "cache-refresh-loop",
        help="Refresh low-churn caches (holidays/timetable) in the idle window",
    )
    p_cache.add_argument("--check", type=float, default=600.0,
                         help="유휴 윈도 진입 확인 간격 초 (default: 600)")
    p_cache.add_argument("--no-run-on-start", action="store_true",
                         help="부팅 시 공휴일 즉시 갱신을 끔")

    p_init = sub.add_parser("init-db", help="Create the database schema")
    p_init.add_argument("--reset", action="store_true", help="bus_timelog 비우기")

    p_tt = sub.add_parser("crawl-timetable", help="Re-crawl Ulsan timetables")
    p_tt.add_argument("--vacation", action="store_true", help="방학 시간표 모드")

    p_rail = sub.add_parser("crawl-rail", help="Refresh KTX/동해선 rail timetables now")
    p_rail.add_argument("--days", type=int, default=None,
                        help="열차 수집 일수(오늘 포함, 기본: RAIL_HORIZON_DAYS=14)")

    p_dbg = sub.add_parser(
        "debug-running", help="Explain how /running reconstructs runs for a route/day",
    )
    p_dbg.add_argument("--route", required=True, help="TRACKED_ROUTES 키 (예: 195000178)")
    p_dbg.add_argument("--date", default=None, help="YYYY-MM-DD 또는 YYYYMMDD (기본: 오늘 KST)")
    p_dbg.add_argument("--db", default=None,
                       help="DB URL (예: sqlite:///data/debug/prod.db). 미지정 시 DATABASE_URL")
    p_dbg.add_argument("-v", "--verbose", action="store_true", help="운행별 정류장 통과 시각 출력")

    p_leg = sub.add_parser(
        "build-leg-profile", help="Build 513 leg travel-time profile for /ktx from passage logs",
    )
    p_leg.add_argument("--tsv", action="append", help="통과기록 logs.tsv (여러 번 지정 가능)")
    p_leg.add_argument("--db", default=None, help="bus_timelog DB URL (예: sqlite:///data/bushexa.db)")
    p_leg.add_argument("--out", default=None, help="저장 경로(기본: <data_dir>/ktx_leg_profile.json)")

    p_ktx = sub.add_parser("ktx-connections", help="Print the per-day KTX↔513 connection table")
    p_ktx.add_argument("--dir", choices=["out", "in"], default="out", help="out=UNIST→울산역, in=울산역→UNIST")
    p_ktx.add_argument("--to", choices=["busan", "seoul", "suseo"], default="busan")
    p_ktx.add_argument("--day", type=int, choices=[0, 1, 2], default=0, help="0 평일 / 1 토 / 2 일·공휴일")
    p_ktx.add_argument("--json", action="store_true", help="JSON 으로 출력")
    p_ktx.add_argument("--transfer-station", type=int, default=None,
                       help="울산역 버스 정류장 ↔ KTX 환승 최소 시간(분, 기본: 관리자 설정 또는 5)")
    p_ktx.add_argument("--transfer-jinmok", type=int, default=None,
                       help="진목회관 길 건너 버스 ↔ 버스 환승 최소 시간(분, 기본: 관리자 설정 또는 5)")

    return parser


def cmd_serve(args) -> int:
    """Web 서버 실행.

    - 운영(기본): gunicorn(WSGI) — create_app 팩토리를 워커마다 로드(포크 후 생성이라
      DB 핸들 공유 문제 없음).
    - ``--dev``: Werkzeug 개발 서버(자동 리로드). gunicorn 미설치 환경(예: Windows)도
      자동으로 Werkzeug로 폴백한다.
    """
    import os

    from bushexa.web.app import create_app

    config = _load_config()

    if not args.dev:
        try:
            from gunicorn.app.base import BaseApplication
        except ModuleNotFoundError:
            BaseApplication = None  # gunicorn 미설치 → 아래 Werkzeug 폴백
        if BaseApplication is not None:
            workers = args.workers or int(os.environ.get("BUSHEXA_WEB_WORKERS", "2"))

            class _GunicornApp(BaseApplication):
                def __init__(self, factory, options):
                    self._factory = factory
                    self._options = options
                    super().__init__()

                def load_config(self):
                    for key, value in self._options.items():
                        self.cfg.set(key, value)

                def load(self):
                    # 워커(포크 이후)에서 앱 생성 — 부모 프로세스 자원 공유 회피
                    return self._factory()

            options = {
                "bind": f"{args.host}:{args.port}",
                "workers": workers,
                "worker_class": "sync",
                "timeout": 60,
                "graceful_timeout": 30,
                "accesslog": "-",
                "errorlog": "-",
            }
            _GunicornApp(lambda: create_app(config), options).run()
            return 0

    # 개발 서버(또는 gunicorn 미설치 폴백)
    app = create_app(config)
    app.run(host=args.host, port=args.port, debug=args.dev)
    return 0


def main(argv: list[str] | None = None) -> int:
    """Entry point referenced by ``[project.scripts] bushexa``."""
    parser = build_parser()
    args = parser.parse_args(argv)
    handlers = {
        "init-db": cmd_init_db,
        "crawl-once": cmd_crawl_once,
        "crawl-loop": cmd_crawl_loop,
        "arrival-loop": cmd_arrival_loop,
        "cache-refresh-loop": cmd_cache_refresh_loop,
        "crawl-timetable": cmd_crawl_timetable,
        "crawl-rail": cmd_crawl_rail,
        "debug-running": cmd_debug_running,
        "build-leg-profile": cmd_build_leg_profile,
        "ktx-connections": cmd_ktx_connections,
        "serve": cmd_serve,
    }
    # argparse가 required=True + 등록된 subparser만 허용하므로 KeyError 도달 불가
    return handlers[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
