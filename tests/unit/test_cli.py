"""bushexa CLI(argparse 배선·서브커맨드 핸들러) 단위 테스트.

각 서브커맨드의 실제 무거운 의존(데몬 루프·gunicorn·네트워크)은 monkeypatch로 대역 처리하고,
CLI 계층이 책임지는 것 — 인자 파싱/기본값, 핸들러 디스패치, 대역에 전달하는 인자, 종료 코드 —
만 검증한다. 기대값은 build_parser()의 선언과 주입한 대역 입력에서 직접 도출(E-13).
"""
from __future__ import annotations

import sqlite3

import pytest

from bushexa import cli
from bushexa.crawler.recorder import RouteStats


@pytest.fixture
def cfg(app_config_test, monkeypatch):
    """_load_config()가 env 대신 테스트 AppConfig를 돌려주고, 로깅 설정은 no-op으로 둔다."""
    monkeypatch.setattr(cli, "_load_config", lambda: app_config_test)
    monkeypatch.setattr("bushexa.logging_setup.setup_logging", lambda **kw: None)
    return app_config_test


# ── 파서 ─────────────────────────────────────────────────────────


def test_parser_requires_subcommand():
    """서브커맨드 없이 호출하면 argparse가 SystemExit(2)로 거부하는지 검증한다."""
    with pytest.raises(SystemExit) as ei:
        cli.build_parser().parse_args([])
    assert ei.value.code == 2


def test_parser_rejects_unknown_subcommand():
    """등록되지 않은 서브커맨드는 SystemExit(2) — main()의 handlers KeyError가 도달 불가함을 보장."""
    with pytest.raises(SystemExit) as ei:
        cli.build_parser().parse_args(["no-such-cmd"])
    assert ei.value.code == 2


@pytest.mark.parametrize("argv, expected", [
    (["crawl-loop"], {"poll": 15.0, "night_sleep": 60.0}),
    (["arrival-loop"], {"poll": 7.0}),
    (["cache-refresh-loop"], {"check": 600.0, "no_run_on_start": False}),
    (["serve"], {"host": "0.0.0.0", "port": 8000, "workers": None, "dev": False}),
    (["init-db"], {"reset": False}),
    (["crawl-timetable"], {"vacation": False}),
])
def test_parser_defaults(argv, expected):
    """각 서브커맨드의 인자 기본값이 문서화된 운영 기본값(crawl-loop --poll 15 등)과 일치하는지 검증한다."""
    ns = vars(cli.build_parser().parse_args(argv))
    for key, value in expected.items():
        assert ns[key] == value, key


def test_crawl_once_requires_route():
    """crawl-once는 --route가 필수 — 누락 시 SystemExit(2)."""
    with pytest.raises(SystemExit) as ei:
        cli.build_parser().parse_args(["crawl-once"])
    assert ei.value.code == 2


def test_main_dispatches_to_handler(monkeypatch):
    """main()이 파싱된 서브커맨드 이름에 대응하는 cmd_* 핸들러를 호출하고 그 반환값을 종료 코드로 돌려주는지 검증한다."""
    seen = []
    monkeypatch.setattr(cli, "cmd_init_db", lambda args: seen.append(args.reset) or 7)
    assert cli.main(["init-db", "--reset"]) == 7
    assert seen == [True]


# ── init-db ──────────────────────────────────────────────────────


def test_init_db_creates_schema_and_reset_clears_timelog(cfg, tmp_path, monkeypatch, capsys):
    """init-db는 스키마를 만들고, --reset은 bus_timelog 행을 비우는지 파일 SQLite로 검증한다."""
    from dataclasses import replace

    db = tmp_path / "cli.db"
    monkeypatch.setattr(cli, "_load_config", lambda: replace(cfg, database_url=f"sqlite:///{db}"))

    assert cli.main(["init-db"]) == 0
    con = sqlite3.connect(db)
    con.execute("INSERT INTO bus_timelog (idx, stop_id, route_id, vehicle_number, stop_name) "
                "VALUES ('2026-06-01 08:00:00', 's', 'r', 'v', 'n')")
    con.commit()
    con.close()

    assert cli.main(["init-db", "--reset"]) == 0
    con = sqlite3.connect(db)
    assert con.execute("SELECT COUNT(*) FROM bus_timelog").fetchone()[0] == 0
    con.close()
    assert "bus_timelog 비움" in capsys.readouterr().out


# ── crawl-once ───────────────────────────────────────────────────


def test_crawl_once_passes_route_and_dry_run(cfg, monkeypatch, capsys):
    """crawl-once가 --route/--dry-run을 daemon.crawl_once에 그대로 전달하고 요약 한 줄을 출력하는지 검증한다."""
    calls = []

    def fake_crawl_once(recorder, route_id, *, dry_run=False):
        calls.append((recorder, route_id, dry_run))
        return RouteStats(route_id=route_id, api_ok=True, parsed_count=3, inserts=2)

    monkeypatch.setattr("bushexa.crawler.daemon.crawl_once", fake_crawl_once)
    sentinel = object()
    args = cli.build_parser().parse_args(["crawl-once", "--route", "195000177", "--dry-run"])

    assert cli.cmd_crawl_once(args, recorder=sentinel) == 0
    assert calls == [(sentinel, "195000177", True)]
    out = capsys.readouterr().out
    assert "route=195000177" in out and "inserts=2" in out and "[dry-run]" in out


# ── 데몬 루프 서브커맨드 ────────────────────────────────────────────


def test_crawl_loop_wires_args_and_status_writer(cfg, monkeypatch):
    """crawl-loop가 --poll/--night-sleep을 run_daemon에 전달하고, stop_event와
    data_dir/govtrack_status.json에 쓰는 on_cycle 콜백을 주입하는지 검증한다."""
    captured = {}
    monkeypatch.setattr("signal.signal", lambda *a: None)  # 테스트 프로세스 핸들러 오염 방지
    monkeypatch.setattr("bushexa.crawler.daemon.run_daemon",
                        lambda config, **kw: captured.update(kw, config=config))

    assert cli.main(["crawl-loop", "--poll", "5", "--night-sleep", "30"]) == 0
    assert captured["config"] is cfg
    assert captured["poll_seconds"] == 5.0
    assert captured["night_sleep_seconds"] == 30.0
    assert not captured["stop_event"].is_set()
    writer = captured["on_cycle"].__self__
    assert writer.path == cfg.data_dir / "govtrack_status.json"


def test_arrival_loop_wires_args(cfg, monkeypatch):
    """arrival-loop가 --poll과 data_dir/arrival_status.json status writer를 run_arrival_poller에 전달하는지 검증한다."""
    captured = {}
    monkeypatch.setattr("signal.signal", lambda *a: None)
    monkeypatch.setattr("bushexa.crawler.arrival_poller.run_arrival_poller",
                        lambda config, **kw: captured.update(kw))

    assert cli.main(["arrival-loop", "--poll", "9"]) == 0
    assert captured["poll_seconds"] == 9.0
    assert captured["status_writer"].path == cfg.data_dir / "arrival_status.json"


def test_cache_refresh_loop_no_run_on_start(cfg, monkeypatch):
    """cache-refresh-loop의 --no-run-on-start가 run_on_start=False로 뒤집혀 전달되는지 검증한다."""
    captured = {}
    monkeypatch.setattr("signal.signal", lambda *a: None)
    monkeypatch.setattr("bushexa.crawler.cache_refresh.run_cache_refresh_loop",
                        lambda config, **kw: captured.update(kw))

    assert cli.main(["cache-refresh-loop", "--check", "30", "--no-run-on-start"]) == 0
    assert captured["check_seconds"] == 30.0
    assert captured["run_on_start"] is False


def test_signal_handler_sets_stop_event(cfg, monkeypatch):
    """SIGTERM/SIGINT 핸들러가 둘 다 등록되고, 호출 시 데몬에 넘긴 stop_event를 set하는지 검증한다(graceful 종료)."""
    import signal as _signal

    handlers = {}
    captured = {}
    monkeypatch.setattr("signal.signal", lambda sig, h: handlers.__setitem__(sig, h))
    monkeypatch.setattr("bushexa.crawler.daemon.run_daemon",
                        lambda config, **kw: captured.update(kw))

    cli.main(["crawl-loop"])
    assert set(handlers) == {_signal.SIGTERM, _signal.SIGINT}
    handlers[_signal.SIGTERM](_signal.SIGTERM, None)
    assert captured["stop_event"].is_set()


# ── crawl-timetable ──────────────────────────────────────────────


def test_crawl_timetable_success(cfg, monkeypatch, capsys):
    """전 노선 성공 시 종료 코드 0과 갱신 노선 목록을 출력하고, --vacation이 전달되는지 검증한다."""
    seen = {}

    def fake_crawl(client, *, vacation, on_progress):
        seen["vacation"] = vacation
        return {"133": "p1", "233": "p2"}

    monkeypatch.setattr("bushexa.crawler.timetable_crawl.crawl_all_timetables", fake_crawl)

    assert cli.main(["crawl-timetable", "--vacation"]) == 0
    assert seen["vacation"] is True
    assert "시간표 2개 노선 갱신" in capsys.readouterr().out


def test_crawl_timetable_partial_failure_returns_1(cfg, monkeypatch, capsys):
    """일부 노선 실패(TimetableCrawlError) 시 종료 코드 1과 성공/실패 노선을 구분 출력하는지 검증한다(ADR-013 격리)."""
    from bushexa.crawler.timetable_crawl import TimetableCrawlError

    def fake_crawl(client, *, vacation, on_progress):
        raise TimetableCrawlError(failed={"733": RuntimeError("x")}, written={"133": "p"})

    monkeypatch.setattr("bushexa.crawler.timetable_crawl.crawl_all_timetables", fake_crawl)

    assert cli.main(["crawl-timetable"]) == 1
    out = capsys.readouterr().out
    assert "1개 노선 갱신: 133" in out
    assert "실패 1개 노선" in out and "733" in out


# ── serve ────────────────────────────────────────────────────────


class _FakeApp:
    def __init__(self):
        self.run_kwargs = None

    def run(self, **kw):
        self.run_kwargs = kw


def test_serve_dev_uses_werkzeug(cfg, monkeypatch):
    """--dev면 gunicorn을 거치지 않고 create_app(config).run(debug=True)로 Werkzeug 서버를 띄우는지 검증한다."""
    app = _FakeApp()
    monkeypatch.setattr("bushexa.web.app.create_app", lambda config: app)

    assert cli.main(["serve", "--dev", "--port", "9000"]) == 0
    assert app.run_kwargs == {"host": "0.0.0.0", "port": 9000, "debug": True}


def test_serve_falls_back_without_gunicorn(cfg, monkeypatch):
    """gunicorn 미설치 환경에서는 --dev 없이도 Werkzeug(debug=False)로 폴백하는지 검증한다."""
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *a, **kw):
        if name.startswith("gunicorn"):
            raise ModuleNotFoundError(name)
        return real_import(name, *a, **kw)

    app = _FakeApp()
    monkeypatch.setattr(builtins, "__import__", fake_import)
    monkeypatch.setattr("bushexa.web.app.create_app", lambda config: app)

    assert cli.main(["serve"]) == 0
    assert app.run_kwargs["debug"] is False


def test_serve_gunicorn_options(cfg, monkeypatch):
    """gunicorn 경로에서 bind/workers 옵션이 인자와 BUSHEXA_WEB_WORKERS env로부터 구성되는지 검증한다."""
    base = pytest.importorskip("gunicorn.app.base")
    captured = {}

    def fake_run(self):
        captured["options"] = dict(self._options)
        captured["factory"] = self._factory

    monkeypatch.setattr(base.BaseApplication, "__init__", lambda self: None)
    monkeypatch.setattr(base.BaseApplication, "run", fake_run)
    monkeypatch.setenv("BUSHEXA_WEB_WORKERS", "4")

    assert cli.main(["serve", "--host", "127.0.0.1", "--port", "8123"]) == 0
    assert captured["options"]["bind"] == "127.0.0.1:8123"
    assert captured["options"]["workers"] == 4
    assert callable(captured["factory"])
