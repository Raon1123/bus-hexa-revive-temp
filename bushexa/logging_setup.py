"""Central logging configuration.

Provides :func:`setup_logging`, used by the CLI and the web app factory, plus
:class:`KSTFormatter` which renders timestamps in Asia/Seoul (KST) regardless of
the host timezone. KST is mandatory because every operational log line is
correlated against bus timetables that are themselves in KST.
"""

from __future__ import annotations

import logging
import logging.config
from datetime import datetime
from pathlib import Path

from bushexa.time_utils import KST  # ADR-008: KST 단일 출처

LOG_FORMAT = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"

_LOGGER_NAMES = ("bushexa", "bushexa.crawler", "bushexa.web")


class KSTFormatter(logging.Formatter):
    """Formatter whose ``asctime`` is rendered in KST with a ``+09:00`` offset."""

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        dt = datetime.fromtimestamp(record.created, tz=KST)
        if datefmt:
            return dt.strftime(datefmt)
        return dt.isoformat(timespec="seconds")


def setup_logging(
    level: str = "INFO",
    log_dir: Path | None = None,
    filename: str = "bushexa.log",
) -> None:
    """Configure console (and optionally rotating-file) logging in KST.

    Args:
        level: Root/handler log level name (e.g. ``"INFO"``, ``"DEBUG"``).
        log_dir: If given, also write a rotating log file (10 MB x 5 backups)
            into this directory.
        filename: Name of the log file written inside *log_dir*.  Defaults to
            ``"bushexa.log"`` (the web-app default).  Pass a role-specific name
            for daemon processes (e.g. ``"bushexa-crawl.log"``) so that each
            process writes to its own file — sharing one RotatingFileHandler
            across processes causes rotation-race issues, and the admin log
            view (``LOG_SOURCES``) expects per-role filenames.
    """
    handlers: dict[str, dict] = {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "kst",
            "level": level,
        }
    }
    if log_dir is not None:
        log_dir = Path(log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        handlers["file"] = {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "kst",
            "level": level,
            "filename": str(log_dir / filename),
            "maxBytes": 10 * 1024 * 1024,
            "backupCount": 5,
            "encoding": "utf-8",
        }

    handler_names = list(handlers)
    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "kst": {
                "()": "bushexa.logging_setup.KSTFormatter",
                "format": LOG_FORMAT,
            }
        },
        "handlers": handlers,
        "loggers": {
            name: {"level": level, "handlers": handler_names, "propagate": False}
            for name in _LOGGER_NAMES
        },
        "root": {"level": level, "handlers": handler_names},
    }
    logging.config.dictConfig(config)
