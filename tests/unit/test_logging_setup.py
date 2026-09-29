"""Unit tests for logging_setup (P0 / W5)."""

from __future__ import annotations

import logging
import logging.handlers

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


def test_setup_logging_custom_filename(tmp_path):
    """When filename='bushexa-crawl.log' is supplied, that file is created (not
    bushexa.log) and the emitted record contains the message text and '+09:00'
    KST offset from KSTFormatter.

    The RotatingFileHandler is explicitly closed after the test to avoid leaving
    an open file handle on the tmp_path, which would interfere with cleanup on
    some platforms.
    """
    setup_logging(level="INFO", log_dir=tmp_path, filename="bushexa-crawl.log")
    logger = logging.getLogger("bushexa")
    logger.info("crawl-daemon started")
    # Flush and close all file handlers to ensure the write is complete.
    handlers_to_close = []
    for handler in logger.handlers:
        handler.flush()
        if isinstance(handler, logging.handlers.RotatingFileHandler):
            handlers_to_close.append(handler)
    for handler in handlers_to_close:
        handler.close()
        logger.removeHandler(handler)

    crawl_log = tmp_path / "bushexa-crawl.log"
    default_log = tmp_path / "bushexa.log"

    assert crawl_log.exists(), "bushexa-crawl.log should be created"
    assert not default_log.exists(), "bushexa.log should NOT be created for filename='bushexa-crawl.log'"

    content = crawl_log.read_text(encoding="utf-8")
    assert "crawl-daemon started" in content
    assert "+09:00" in content


def test_log_file_never_contains_service_key(tmp_path):
    """API 요청 URL에 담긴 serviceKey 가 로그 파일에 기록되지 않는다 (PM-016).

    세 경로를 모두 막는지 본다: bushexa 로거의 메시지 인자(requests 예외 문자열),
    root 로 전파되는 서드파티 로거(urllib3 DEBUG 요청 줄), 예외 트레이스백(logger.exception).
    """
    secret = "AbCd%2BSecretKey%3D%3D"
    url = f"/UlsanAPI/getBusArrivalInfo.xo?serviceKey={secret}&pageNo=1&stopid=196020808"
    setup_logging(level="DEBUG", log_dir=tmp_path, filename="bushexa-arrival.log")
    try:
        logging.getLogger("bushexa.api_clients.ulsan_bis").error(
            "울산 도착정보 호출 실패 stop_id=%s: %s", "196020808",
            f"HTTPConnectionPool(host='openapi.its.ulsan.kr', port=80): Read timed out. (url: {url})")
        logging.getLogger("urllib3.connectionpool").debug('"GET %s HTTP/1.1" 200 2500', url)
        try:
            raise RuntimeError(f"Max retries exceeded with url: {url}")
        except RuntimeError:
            logging.getLogger("bushexa.crawler").exception("사이클 실패")
    finally:
        closing = []
        for name in ("bushexa", "bushexa.crawler", ""):
            for handler in logging.getLogger(name).handlers:
                handler.flush()
                if isinstance(handler, logging.handlers.RotatingFileHandler):
                    closing.append(handler)
        for handler in set(closing):
            handler.close()

    text = (tmp_path / "bushexa-arrival.log").read_text(encoding="utf-8")
    assert secret not in text
    assert text.count("serviceKey=***") >= 3  # 세 경로 모두 기록은 되되 값만 가려짐
    assert "stopid=196020808" in text          # 진단에 필요한 다른 파라미터는 보존
