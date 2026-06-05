"""Unit tests for logging_setup (P0 / W5)."""

from __future__ import annotations

import logging

from bushexa.logging_setup import KSTFormatter, setup_logging


def test_kst_timestamp():
    """A formatted record's timestamp is rendered in KST: given a record at a
    fixed epoch, the formatted asctime must carry the '+09:00' offset regardless
    of the host machine's timezone."""
    fmt = KSTFormatter("%(asctime)s %(message)s")
    record = logging.LogRecord(
        name="bushexa", level=logging.INFO, pathname=__file__, lineno=1,
        msg="hello", args=None, exc_info=None,
    )
    record.created = 1_717_200_000  # fixed epoch
    out = fmt.format(record)
    assert "+09:00" in out


def test_setup_logging_is_idempotent_and_emits():
    """setup_logging() can be called twice without error and the configured
    'bushexa' logger then emits a record. The record is captured via a handler
    we attach directly, because the bushexa logger sets propagate=False by
    design (which makes pytest's caplog, a root-logger handler, miss it)."""
    setup_logging(level="DEBUG")
    setup_logging(level="INFO")  # idempotent: reconfiguring must not raise

    logger = logging.getLogger("bushexa")
    seen: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            seen.append(record)

    handler = _Capture()
    logger.addHandler(handler)
    try:
        logger.info("startup ok")
    finally:
        logger.removeHandler(handler)

    assert any("startup ok" in r.getMessage() for r in seen)


def test_setup_logging_writes_file(tmp_path):
    """When a log_dir is supplied, setup_logging() creates bushexa.log there and
    a subsequent log call results in a non-empty file on disk."""
    setup_logging(level="INFO", log_dir=tmp_path)
    logging.getLogger("bushexa").info("to file")
    for handler in logging.getLogger("bushexa").handlers:
        handler.flush()
    log_file = tmp_path / "bushexa.log"
    assert log_file.exists() and log_file.stat().st_size > 0
