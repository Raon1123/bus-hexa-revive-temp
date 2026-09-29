"""bushexa command-line interface.

전 서브커맨드 배선 완료:

* ``serve``              -> P4/P5 (gunicorn 운영, --dev 시 Werkzeug)
* ``crawl-once``         -> P2 (1회 폴링, --route/--dry-run)
* ``crawl-loop``         -> P2 (govtrack 데몬, PM-001 수정) --poll/--night-sleep
* ``arrival-loop``       -> P2 / ADR-010 (울산 도착 캐시 poller)
* ``cache-refresh-loop`` -> 유휴 윈도(02–03시) 공휴일·시간표 재크롤 워커
* ``init-db``            -> 스키마 생성(--reset 시 bus_timelog 비움)
* ``crawl-timetable``    -> P2 / F10 (시간표 재크롤)
* ``debug-running``      -> F05 운행 재구성 진단 (제외 정류장·분리·덮어쓰기 출력)

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

    from bushexa.data.constants import ROUTEID, STOP_IDS
    from bushexa.db.connection import _sqlite_path, create_connection, is_sqlite
    from bushexa.db.repo import BusLogRepo
    from bushexa.domain.running import explain_runs

    if args.route not in ROUTEID:
        print(f"알 수 없는 노선 ID: {args.route!r}. 사용 가능:")
        for rid, info in ROUTEID.items():
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

    busno, terminal, _dep, stops_order = ROUTEID[args.route]

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
    p_once.add_argument("--route", required=True, help="ROUTEID 키 (예: 195000177)")
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

    p_dbg = sub.add_parser(
        "debug-running", help="Explain how /running reconstructs runs for a route/day",
    )
    p_dbg.add_argument("--route", required=True, help="ROUTEID 키 (예: 195000178)")
    p_dbg.add_argument("--date", default=None, help="YYYY-MM-DD 또는 YYYYMMDD (기본: 오늘 KST)")
    p_dbg.add_argument("--db", default=None,
                       help="DB URL (예: sqlite:///data/debug/prod.db). 미지정 시 DATABASE_URL")
    p_dbg.add_argument("-v", "--verbose", action="store_true", help="운행별 정류장 통과 시각 출력")

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
        "debug-running": cmd_debug_running,
        "serve": cmd_serve,
    }
    # argparse가 required=True + 등록된 subparser만 허용하므로 KeyError 도달 불가
    return handlers[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
