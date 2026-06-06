"""원자적 파일 쓰기 + 생성/수정 감사 로깅 (ADR-012) + 관용적 JSON 읽기.

bushexa 내에서 디스크 파일을 쓰는 **유일한 합법 경로**다. 직접 ``open(..., "w")`` /
``json.dump(..., 파일)`` / ``Path.write_*`` 대신 이 헬퍼를 사용한다. 모든 쓰기는
임시파일 → fsync → 원자적 rename으로 손상을 막고, 생성/수정을 구분해 INFO 로그를
``bushexa.fileio`` 로거(= ``logs/bushexa.log`` sink, 관리자 로그 뷰어 F04 §4.6이 읽음)에 남긴다.
파일 **내용은 절대 로그하지 않는다**(시크릿 유출 방지).

읽기는 ``read_json``이 공용 경로다(리뷰 reuse 항목 — '부재·파손이면 default' 패턴
~12벌 제각각 구현을 단일화). 파일 부재 시 예외를 던져야 하는 계약(예:
data/timetable.get_timetable)은 해당 모듈이 직접 읽는다.
"""
from __future__ import annotations

import fcntl
import json
import logging
import os
from pathlib import Path
from typing import Any, Callable

_DEFAULT_LOGGER = logging.getLogger("bushexa.fileio")


def _atomic_write(path: Path, data: bytes, *, logger: logging.Logger | None = None) -> None:
    """``data``를 ``path``에 원자적으로 쓰고 생성/수정 여부를 INFO 로그로 남긴다."""
    log = logger or _DEFAULT_LOGGER
    path = Path(path)
    verb = "modified" if path.exists() else "created"  # 쓰기 '직전' 판정 (ADR-012)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp.{os.getpid()}")
    try:
        with open(tmp, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)  # 원자적 rename
    except BaseException:
        # 실패 시 tmp만 정리 — 기존 path 내용은 건드리지 않는다(원자성).
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
        raise
    # 경로·크기·동사만 기록한다. 내용 미기록(ADR-012 / ADR-009 시크릿 보호).
    log.info("file %s: %s (%dB)", verb, path.resolve(), len(data))


def atomic_write_bytes(path, data: bytes, *, logger: logging.Logger | None = None) -> None:
    _atomic_write(Path(path), data, logger=logger)


def atomic_write_text(path, text: str, *, encoding: str = "utf-8",
                      logger: logging.Logger | None = None) -> None:
    _atomic_write(Path(path), text.encode(encoding), logger=logger)


def atomic_write_json(path, obj: Any, *, ensure_ascii: bool = False, indent: int | None = None,
                      logger: logging.Logger | None = None) -> None:
    # 직렬화 실패(예: set)는 파일을 만들기 '전'에 발생 → 기존 파일 무손상.
    text = json.dumps(obj, ensure_ascii=ensure_ascii, indent=indent)
    _atomic_write(Path(path), text.encode("utf-8"), logger=logger)


def read_json(path, default: Any, *,
              expect: type | tuple[type, ...] | None = None,
              warn_label: str | None = None,
              logger: logging.Logger | None = None) -> Any:
    """JSON 파일을 읽어 반환. 부재·파손·최상위 형식 불일치 시 ``default``.

    ``warn_label``을 주면 파손·형식 오류를 WARNING으로 남긴다(데몬 상태·설정 등
    침묵하면 안 되는 경로 — ADR-013 준용). 부재는 정상 초기 상태라 로그하지 않는다.
    ``expect``는 최상위 타입(list/dict)만 거른다 — 상세 형태 검증·정규화는 호출자 책임.
    """
    log = logger or _DEFAULT_LOGGER
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except (OSError, ValueError) as exc:
        if warn_label:
            log.warning("%s 로드 실패(기본값 사용) %s: %s", warn_label, path, exc)
        return default
    if expect is not None and not isinstance(data, expect):
        if warn_label:
            log.warning("%s 형식 오류(기본값 사용) %s", warn_label, path)
        return default
    return data


_SENTINEL = object()


def locked_update_json(
    path,
    mutate: Callable[[Any], Any],
    *,
    default: Any = _SENTINEL,
    logger: logging.Logger | None = None,
) -> None:
    """fcntl.flock 으로 보호된 read-modify-write → atomic_write_json.

    **Linux 전제** — fcntl.flock는 Linux/macOS POSIX API이며 Windows에서는
    동작하지 않는다. 배포 환경이 Linux 컨테이너임을 가정하고 사용한다.

    동작 순서:
      1. ``<path>.lock`` 파일에 LOCK_EX(배타 잠금)를 획득한다.
      2. ``path``가 존재하면 JSON 파싱; 부재·파손이면 ``default`` 사용.
         ``default``가 지정되지 않은 상태에서 파일이 없으면 FileNotFoundError.
      3. ``mutate(obj)``를 호출해 갱신된 객체를 얻는다.
      4. ``atomic_write_json``으로 저장 후 잠금 해제.

    기존 ``atomic_write_json`` 의미는 불변(이 함수가 내부적으로 호출).

    Parameters
    ----------
    path:
        쓸 JSON 파일 경로.
    mutate:
        현재 오브젝트를 받아 갱신된 오브젝트를 반환하는 callable.
    default:
        파일 부재·파손 시 초기값. 미지정이면 파일 부재 시 FileNotFoundError.
    logger:
        fileio 감사 로거 오버라이드. None이면 기본 로거.
    """
    path = Path(path)
    # 잠금 파일은 대상 파일의 형제 .lock 파일 (부모 디렉터리가 없으면 생성)
    lock_path = path.with_suffix(path.suffix + ".lock")
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(lock_path, "w") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        try:
            # 현재 데이터 로드
            if path.exists():
                try:
                    obj = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    if default is _SENTINEL:
                        raise
                    obj = default
            else:
                if default is _SENTINEL:
                    raise FileNotFoundError(f"locked_update_json: 파일 없음: {path}")
                obj = default

            # mutate 적용 후 원자적 저장
            updated = mutate(obj)
            atomic_write_json(path, updated, logger=logger)
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)
