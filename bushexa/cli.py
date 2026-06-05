"""bushexa command-line interface.

P2에서 govtrack 크롤러 명령 본체를 배선한다:

* ``serve``            -> P4 (Flask web server) — 아직 stub
* ``crawl-once``       -> P2 (1회 폴링, --route/--dry-run)
* ``crawl-loop``       -> P2 (govtrack 데몬, PM-001 수정) --poll/--night-sleep
* ``arrival-loop``     -> P2 / ADR-010 (울산 도착 캐시 poller) — W9에서 배선
* ``init-db``          -> 스키마 생성(--reset 시 bus_timelog 비움)
* ``crawl-timetable``  -> P2 / F10 (시간표 재크롤) — W4에서 배선

설계(F09 §4.1)에 맞춰 ``crawl-loop``의 폴링 인자는 ``--poll``(기본 10초)이다. 신호 핸들러는
메인 스레드에서만 등록하고, 데몬 루프는 stop_event로 graceful 종료한다.
"""

from __future__ import annotations

import argparse


def _todo(command: str) -> int:
    """아직 배선되지 않은 서브커맨드(후속 phase)."""
    print(f"TODO: '{command}' is not implemented yet.")
    return 0


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

    setup_logging()
    if recorder is None:
        recorder = build_recorder(_load_config())
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

    setup_logging()
    config = _load_config()
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

    setup_logging()
    config = _load_config()
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

    setup_logging()
    config = _load_config()
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

    setup_logging()
    config = _load_config()
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
    p_loop.add_argument("--poll", type=float, default=10.0,
                        help="버스 위치 폴링 간격 초 (default: 10)")
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
        "serve": cmd_serve,
    }
    handler = handlers.get(args.command)
    if handler is not None:
        return handler(args)
    return _todo(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
