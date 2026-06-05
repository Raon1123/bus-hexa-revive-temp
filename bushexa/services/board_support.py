"""board_support — 게시판·도착 라우트 공용 팩토리 (리뷰 E6/altitude, #8).

세 가지 책임을 한곳에서 해결한다:

1. **timetable_provider_for** — 특별편 지정일이면 edition provider(폴백: KeyError·
   FileNotFoundError 모두 평일 코드 0), 아니면 기본 get_timetable. 기존 board/busno/
   unist_timetable 3벌의 복제 래퍼를 제거하고 여기서 단 한 번 정의한다(리뷰 E6).
   D8 수정: 기존 래퍼는 KeyError만 잡았으나 edition_exists가 디렉터리 존재만 검사하므로
   부분 편성 edition에서 FileNotFoundError가 도메인 catch로 흘러 빈 행이 됐다.
   여기서는 KeyError와 FileNotFoundError 모두를 잡아 weekday 0 폴백을 보장한다.

2. **get_read_connection** — 프로세스(워커) 수명 재사용 read 연결.
   gunicorn sync 워커는 요청을 단일 스레드로 직렬 처리하므로 모듈 레벨 dict 캐시가
   안전하다(스레드 경합 없음). 매 요청마다 connect + PRAGMA 3회를 제거해 리뷰 #8에서
   지적한 cold 18.7초의 PRAGMA 비용을 없앤다. 크롤 데몬 writer와는 WAL로 공존한다.
   sqlite3 OperationalError 발생 시 1회 재연결한다. 연결을 닫지 않는 것이 의도이며
   워커 종료 시 OS가 정리한다.

3. **arrival_client** — 위 영속 연결로 BusArrivalRepo → CachedArrivalClient를 만드는
   일반 함수(contextmanager 아님 — 연결을 닫지 않으므로).
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import date
from typing import Callable

from bushexa.api_clients.cached_arrival import CachedArrivalClient
from bushexa.data.timetable import get_timetable, timetable_dir
from bushexa.db.connection import create_connection
from bushexa.db.repo_arrival import BusArrivalRepo
from bushexa.services.special_timetable import SpecialTimetableService, default_special_path

log = logging.getLogger("bushexa.services.board_support")

# ---------------------------------------------------------------------------
# 모듈 레벨 읽기 전용 연결 캐시 {database_url: sqlite3.Connection}
# gunicorn sync 워커는 단일 스레드 — 동시 접근 없어 dict 캐시 안전(리뷰 #8).
# ---------------------------------------------------------------------------
_READ_CONN_CACHE: dict[str, sqlite3.Connection] = {}


def get_read_connection(database_url: str):
    """프로세스(워커) 수명 재사용 SQLite read 연결을 반환한다.

    첫 호출에서 create_connection(database_url)로 연결을 생성·캐시한다.
    이후 호출은 캐시된 연결을 그대로 반환한다(PRAGMA 재실행 없음 — 리뷰 #8).

    sqlite3.OperationalError 발생 시 1회 재연결한다. 연결을 close하지 않는 것이
    의도이며, 워커 종료(gunicorn graceful shutdown) 시 OS가 파일 핸들을 정리한다.

    WAL 모드(create_connection에서 설정)로 크롤 데몬 writer와 동시 공존한다.
    """
    conn = _READ_CONN_CACHE.get(database_url)
    if conn is not None:
        # 연결 생존 여부 확인 — 깨진 연결은 재생성.
        # SQLite 닫힌 연결은 ProgrammingError, 잠금/파일 오류는 OperationalError.
        try:
            conn.execute("SELECT 1")
            return conn
        except (sqlite3.OperationalError, sqlite3.ProgrammingError):
            log.warning("read 연결이 끊겼습니다. 재연결합니다. url=%s", database_url)
            _READ_CONN_CACHE.pop(database_url, None)

    conn = create_connection(database_url)
    _READ_CONN_CACHE[database_url] = conn
    log.debug("read 연결 신규 생성 및 캐시. url=%s", database_url)
    return conn


def arrival_client(config) -> CachedArrivalClient:
    """config.database_url로 영속 read 연결을 얻어 CachedArrivalClient를 반환한다.

    연결은 get_read_connection으로 워커 수명 동안 재사용된다(close하지 않음).
    리뷰 E6: board/board_lite/unist_board/stops의 `create_connection→BusArrivalRepo
    →CachedArrivalClient→close` 배선 4벌을 여기서 단일화한다.
    """
    conn = get_read_connection(config.database_url)
    return CachedArrivalClient(BusArrivalRepo(conn))


def timetable_provider_for(
    config,
    today: date,
    holiday_set: set[str],
) -> Callable:
    """오늘 날짜에 맞는 시간표 provider를 반환한다.

    특별편 지정일이면 edition provider를 반환하고, 그렇지 않으면 기본 get_timetable을
    반환한다. 라우트별로 복제되던 3벌의 래퍼(board.py:57-64, busno.py:55-59,
    unist_timetable.py:56-60)를 단일화한다(리뷰 E6).

    D8 수정: 기존 래퍼는 KeyError만 잡았으나 edition_exists는 디렉터리 존재만 검사하므로
    부분 편성 edition에서 FileNotFoundError가 래퍼를 건너뛰었다. 여기서는 KeyError와
    FileNotFoundError 모두 잡아 weekday=0(평일) 폴백을 보장한다.

    Parameters
    ----------
    config :
        AppConfig. data_dir을 특별편 경로 탐색에 사용한다.
    today : date
        오늘 날짜. 특별편 배정 조회에 사용한다.
    holiday_set : set[str]
        공휴일 YYYYMMDD 문자열 집합. 현재 함수에서 직접 쓰지는 않지만 API 일관성을
        위해 시그니처에 포함한다(caller가 이미 읽은 집합을 전달하면 된다).
    """
    tt_dir = timetable_dir()
    svc = SpecialTimetableService(
        map_path=default_special_path(config.data_dir),
        timetable_dir=tt_dir,
    )
    date_str = today.strftime("%Y%m%d")
    edition_id = svc.get_edition_for_date(date_str)

    if edition_id and svc.edition_exists(edition_id):
        edition_dir = svc.edition_dir(edition_id)

        def _edition_provider(busno, weekday, departure, *, _dir=edition_dir):
            """특별편 provider.

            요청된 weekday 키를 먼저 시도하고 없으면 weekday=0(평일)으로 폴백한다.
            이로써 관리자가 평일 탭만 채운 에디션도 공휴일·토요일에 정상 작동한다.

            D8 수정(리뷰 D8): 폴백 분기를 두 가지로 구분한다.
            - KeyError: edition 디렉터리 내에 JSON은 있으나 weekday 키가 없음.
              → 동일 edition_dir에서 weekday=0(평일) 폴백 (기존 라우트 3벌의 동작 유지).
            - FileNotFoundError: edition 디렉터리에 해당 노선 JSON 자체가 없음 (부분 편성).
              → 기본 시간표 디렉터리(timetable_dir())의 weekday=0 데이터로 폴백.
              기존 래퍼(KeyError만 catch)에서 이 경로는 도메인까지 전파돼 빈 행이 됐다.
            """
            try:
                return get_timetable(busno, weekday, departure, dir=_dir)
            except KeyError:
                # edition 내 weekday 키 없음 → 같은 edition의 평일(0) 폴백 (기존 동작)
                return get_timetable(busno, 0, departure, dir=_dir)
            except FileNotFoundError:
                # D8: 노선 JSON이 edition에 없음 → 기본 시간표(publish된 평일-0) 폴백
                # dir 인자 미전달: timetable_dir() 기본값 사용 — 발행된 시간표 디렉터리
                return get_timetable(busno, 0, departure)

        log.debug(
            "특별편 provider 적용: date=%s edition=%s", date_str, edition_id
        )
        return _edition_provider

    return get_timetable
