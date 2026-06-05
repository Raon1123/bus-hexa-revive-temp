"""F10 시간표 재크롤 백엔드 (W4).

legacy ``src/crawl.py``의 ``crawl_target_timetable``/``crawl_timetable``/``request_timetable``을
이전하면서 결함을 수정한다:
- **streamlit 의존 제거**: legacy의 ``st.*`` 호출과 그 import를 모두 걷어내고 진행 보고를
  ``on_progress`` 콜백으로 추상화한다(UI는 SSE, CLI는 stdout). — F10 결함
- **페이지네이션 off-by-one 수정**: 종료 페이지를 ``ceil(total/rows)``로 계산해 totalCount가
  페이지 크기의 정확한 배수일 때 빈 페이지를 추가 요청하지 않는다. — F10 결함5
- **중복 status_code 분기 정리**: client가 파싱·재시도를 담당하므로 크롤 루프는 단순해진다. — 결함4
- **원자적 쓰기**: ``fileio.atomic_write_json``(임시파일+rename, ADR-012)로 기존 JSON 손상 방지.

장애 복원력(ADR-013 결정 2·4의 시간표 크롤 적용, 2026-06-05 울산 API 간헐 무응답 실측 후):
- **요청별 재시도**: 일시 네트워크 오류는 백오프(1s, 2s) 후 ≤3회 재시도, 상한 초과 시 raise.
- **노선 단위 격리**: 한 노선 수집 실패가 나머지 노선 기록을 막지 않는다. 실패 노선은
  파일을 쓰지 않아(부분 시간표로 덮어쓰기 금지) 기존 데이터가 보존되고, 전체 종료 시
  :class:`TimetableCrawlError` 로 집계 보고한다(호출자 — CLI 종료코드/SSE error/
  cache-refresh 윈도 내 재시도 — 가 실패를 관찰).
"""
from __future__ import annotations

import logging
import time as _time
from dataclasses import dataclass
from pathlib import Path

import requests

from bushexa import fileio
from bushexa.data.constants import ROUTEID
from bushexa.data.timetable import timetable_dir

logger = logging.getLogger("bushexa.crawler.timetable_crawl")


class TimetableCrawlError(RuntimeError):
    """일부 노선 수집 실패. 성공 노선은 이미 기록됨 — ``written``/``failed``로 구분."""

    def __init__(self, failed: dict[str, Exception], written: dict[str, Path]):
        self.failed = failed
        self.written = written
        super().__init__(
            f"시간표 재크롤 부분 실패: 실패 {sorted(failed)} / 성공 {sorted(written)}"
        )


def _fetch_page_with_retry(client, route_no, day_of_week, *, page, rows,
                           attempts=3, sleep=_time.sleep):
    """일시 네트워크 오류를 백오프 재시도(ADR-013 결정 4). 상한 초과 시 마지막 예외 raise."""
    for attempt in range(1, attempts + 1):
        try:
            return client.fetch_timetable_page(route_no, day_of_week, page=page, rows=rows)
        except requests.exceptions.RequestException as exc:
            if attempt == attempts:
                raise
            wait = 2 ** (attempt - 1)  # 1s, 2s — 무한 즉시 재시도 금지(ADR-013)
            logger.warning("시간표 요청 실패 route=%s day=%s page=%s (시도 %d/%d, %ds 후 재시도): %s",
                           route_no, day_of_week, page, attempt, attempts, wait, exc)
            sleep(wait)


@dataclass(frozen=True)
class ProgressEvent:
    """재크롤 진행 1건(페이지 단위). UI/CLI가 표시한다."""

    route: str
    day: int
    page: int
    message: str = ""


def crawl_route_day(client, route_no, day_of_week, *, rows: int = 50, on_progress=None,
                    attempts: int = 3, sleep=_time.sleep):
    """한 노선·요일의 시간표를 페이지네이션으로 모두 수집해 TimetableRow 목록을 반환한다.

    종료 페이지 = ``ceil(total/rows)`` (off-by-one 수정). 페이지마다 on_progress 호출.
    일시 네트워크 오류는 페이지 단위로 ``attempts``회까지 백오프 재시도(ADR-013).
    """
    first_rows, total = _fetch_page_with_retry(client, route_no, day_of_week,
                                               page=1, rows=rows, attempts=attempts, sleep=sleep)
    if on_progress is not None:
        on_progress(ProgressEvent(str(route_no), day_of_week, 1))
    if total <= 0:
        return list(first_rows)

    pages = (total + rows - 1) // rows  # ceil — 정확한 배수면 빈 페이지를 요청하지 않는다
    out = list(first_rows)
    for page in range(2, pages + 1):
        page_rows, _ = _fetch_page_with_retry(client, route_no, day_of_week,
                                              page=page, rows=rows, attempts=attempts, sleep=sleep)
        out.extend(page_rows)
        if on_progress is not None:
            on_progress(ProgressEvent(str(route_no), day_of_week, page))
    return out


def _busno_directions() -> dict[str, list[tuple[str, str, int]]]:
    """ROUTEID에서 busno → [(route_id, departure, direction)] 매핑 생성(legacy 로직 동일).

    같은 busno의 route_id를 정렬해 더 작은 쪽을 direction 1, 다른 쪽을 2로 둔다.
    """
    by_bus: dict[str, list[tuple[str, str]]] = {}
    for route_id, value in ROUTEID.items():
        busno, departure = value[0], value[2]
        by_bus.setdefault(busno, []).append((route_id, departure))
    result: dict[str, list[tuple[str, str, int]]] = {}
    for busno, infos in by_bus.items():
        infos.sort(key=lambda x: x[0])
        result[busno] = [(rid, dep, 1 if i == 0 else 2) for i, (rid, dep) in enumerate(infos)]
    return result


def crawl_all_timetables(client, *, vacation: bool = False, out_dir=None,
                         on_progress=None, days=(0, 1, 2), attempts: int = 3,
                         sleep=_time.sleep) -> dict[str, Path]:
    """전 노선 시간표를 재크롤해 ``{busno}.json`` 5개를 atomic하게 기록한다. {busno: path} 반환.

    노선 단위 격리(ADR-013 결정 2): 한 노선의 *수집* 실패는 로그 후 다음 노선으로 계속하고,
    그 노선 파일은 쓰지 않는다(부분 시간표로 기존 데이터 덮어쓰기 금지). 전부 끝난 뒤 실패가
    있으면 :class:`TimetableCrawlError` 를 raise해 호출자가 부분 실패를 관찰한다.
    파일 *쓰기* 오류(디스크 등 시스템 문제)는 격리하지 않고 즉시 전파한다.
    """
    out_dir = Path(out_dir) if out_dir is not None else timetable_dir()
    offset = 3 if vacation else 0
    directions = _busno_directions()
    written: dict[str, Path] = {}
    failed: dict[str, Exception] = {}

    for busno, route_info in directions.items():
        table: dict[str, dict[str, list[str]]] = {}
        try:
            for week in days:
                table[str(week)] = {}
                tt_rows = crawl_route_day(client, busno, week + offset,
                                          on_progress=on_progress, attempts=attempts, sleep=sleep)
                for row in tt_rows:
                    for (_rid, departure, route_direction) in route_info:
                        if row.direction == route_direction:
                            table[str(week)].setdefault(departure, []).append(row.time)
        except Exception as exc:  # 노선 격리 — 로그 필수(ADR-013: silent swallow 금지)
            logger.error("시간표 수집 실패 — 노선 %s 건너뜀(기존 파일 보존): %s",
                         busno, exc, exc_info=True)
            failed[busno] = exc
            continue
        if not any(table.values()):
            # 전 요일 0행 — 클라이언트의 오류 검사를 통과한 알 수 없는 오류 형태(또는 빈
            # 페이지)일 가능성이 높다. 운행 중 노선이 전 요일 무시간표일 수는 없으므로
            # 빈 데이터로 기존 파일을 덮어쓰지 않고 실패로 집계한다(2026-06-05 리뷰).
            exc = RuntimeError(f"노선 {busno} 수집 결과가 전 요일 비어 있음 — 기존 파일 보존")
            logger.error("%s", exc)
            failed[busno] = exc
            continue
        path = out_dir / f"{busno}.json"
        fileio.atomic_write_json(path, table)  # ADR-012: 원자적 + 감사 로그
        written[busno] = path
        logger.info("시간표 기록: %s (%d일치)", path, len(days))

    if failed:
        raise TimetableCrawlError(failed, written)
    return written
