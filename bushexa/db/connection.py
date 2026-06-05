"""DB 연결 팩토리 — SQLite/PostgreSQL dual-backend (ADR-002).

DSN 형식 3종을 흡수한다:
- ``sqlite:///relative/path.db``  (상대 경로)
- ``sqlite:////abs/path.db``      (절대 경로)
- ``sqlite:///:memory:``          (인메모리, 테스트)
- ``postgresql://user:pw@host:port/db``

SQLite는 WAL + foreign_keys를 켜고, 백엔드별 파라미터 placeholder(``?`` vs ``%s``) 차이를
``placeholder(dsn)``으로 흡수한다. psycopg2는 deferred import — 미설치 환경에서도 SQLite는 동작한다.
"""
from __future__ import annotations

import sqlite3

_SQLITE_PREFIX = "sqlite://"
_PG_PREFIXES = ("postgresql://", "postgres://")


def is_sqlite(dsn: str) -> bool:
    return dsn.startswith(_SQLITE_PREFIX)


def placeholder(dsn: str) -> str:
    """파라미터 바인딩 placeholder. SQLite=``?``, PostgreSQL=``%s``."""
    return "?" if is_sqlite(dsn) else "%s"


def placeholder_for_conn(conn) -> str:
    """연결 객체로 placeholder 판정(repo는 dsn 대신 conn만 받으므로)."""
    return "?" if isinstance(conn, sqlite3.Connection) else "%s"


def _sqlite_path(dsn: str) -> str:
    # "sqlite://" 이후를 취하고, scheme 뒤 선행 '/' 하나를 제거.
    # sqlite:///:memory:  -> "/:memory:" -> ":memory:"
    # sqlite:///data/x.db -> "/data/x.db" -> "data/x.db" (상대)
    # sqlite:////abs/x.db -> "//abs/x.db" -> "/abs/x.db" (절대)
    rest = dsn[len(_SQLITE_PREFIX):]
    if rest.startswith("/"):
        rest = rest[1:]
    return rest or ":memory:"


def _connect_sqlite(dsn: str) -> sqlite3.Connection:
    conn = sqlite3.connect(_sqlite_path(dsn))
    # 단일 writer + 다중 reader 동시성. :memory:에선 무시되지만 무해.
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    # busy_timeout: 단일 컨테이너에서 web(reader) + crawl-loop/arrival-loop(writer 2개)가
    # 같은 파일을 공유한다(과거엔 postgres가 동시성 중재). SQLite는 writer가 1개뿐이라
    # 동시 쓰기 충돌 시 즉시 "database is locked"를 던진다. busy_timeout으로 5초간 락
    # 해제를 대기하게 해 충돌을 흡수한다.
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def _connect_postgres(dsn: str):
    try:
        import psycopg2  # deferred: 미설치 환경에서도 SQLite 경로는 동작
    except ImportError as exc:  # pragma: no cover - 환경 의존
        raise ImportError(
            "postgresql DSN을 쓰려면 psycopg2가 필요합니다. "
            "`uv sync --extra postgres`로 설치하거나 `sqlite:///...` DSN을 사용하세요."
        ) from exc
    return psycopg2.connect(dsn)


def create_connection(dsn: str):
    """DSN으로 DB 연결을 생성한다. 지원하지 않는 scheme이면 ValueError."""
    if is_sqlite(dsn):
        return _connect_sqlite(dsn)
    if dsn.startswith(_PG_PREFIXES):
        return _connect_postgres(dsn)
    raise ValueError(f"지원하지 않는 DSN scheme: {dsn!r}")


def operational_errors() -> tuple[type[BaseException], ...]:
    """'연결 끊김' 계열 예외 타입 튜플 (recorder 재연결 트리거용, F09 H5/AC-H5).

    SQLite는 ``sqlite3.OperationalError``, Postgres는 ``psycopg2.OperationalError``.
    psycopg2 미설치 환경에서는 SQLite 타입만 포함한다(deferred import).
    """
    errs: list[type[BaseException]] = [sqlite3.OperationalError]
    try:
        import psycopg2  # pragma: no cover - 환경 의존
        errs.append(psycopg2.OperationalError)
    except ImportError:
        pass
    return tuple(errs)
