"""bus_timelog 저장소 (W6a write / W6b read).

공개 메서드 surface는 F09 §4.4 + F04 §4.4의 합집합과 **정확히 일치**한다(EC-7):
insert_log, insert_batch, latest_node_per_vehicle, get_by_route, query_paged, count, export_csv.
legacy db.py의 get_by_stop_id/get_all/clear_table 등은 query_paged로 대체되어 추가하지 않는다.

idx 형식은 ``YYYYMMDD_HH:MM:SS`` (사전식 정렬=시간순). day 필터는 ``idx LIKE 'YYYYMMDD_%'``.
파라미터 placeholder는 backend(SQLite/Postgres)에 따라 흡수한다.
"""
from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import date, datetime
from typing import Generic, TypeVar

from bushexa.db.connection import placeholder_for_conn

T = TypeVar("T")

_COLS = "idx, stop_id, route_id, route_nm, vehicle_number, stop_name"
_FILTER_KEYS = {"route_id", "stop_id", "vehicle_no", "day"}

# CSV formula injection 방어 대상 선두 문자 (OWASP CSV-injection guidance, P5/ADR-009)
_CSV_INJECTION_CHARS = ("=", "+", "-", "@", "\t", "\r")


def _sanitize_csv_cell(value) -> str:
    """CSV formula injection 방어 (OWASP CSV-injection guidance, P5/ADR-009).

    None → 빈 문자열. 셀 값이 =, +, -, @, \\t, \\r 로 시작하면 선두에 ' 를 붙여
    스프레드시트가 수식으로 해석하지 못하게 한다. 기타 값은 그대로 반환.
    """
    if value is None:
        return ""
    s = str(value)
    if s and s[0] in _CSV_INJECTION_CHARS:
        return "'" + s
    return s


@dataclass(frozen=True)
class LogRow:
    idx: str
    stop_id: str
    route_id: str
    vehicle_no: str
    stop_name: str | None = None
    route_nm: str | None = None


@dataclass(frozen=True)
class PagedResult(Generic[T]):
    rows: list[T]
    total: int
    page: int
    size: int


class BusLogRepo:
    def __init__(self, conn):
        self.conn = conn
        self._ph = placeholder_for_conn(conn)

    # ---- context manager (H10) -----------------------------------------
    # legacy BUS_TIMELOG는 __del__에서 conn 먼저·cursor 나중 순으로 닫아 예외 위험이 있었다.
    # 본 repo는 메서드마다 transient cursor를 쓰므로 장수 cursor가 없고, __exit__에서 conn만
    # 안전하게 닫는다. dunder이므로 공개 표면(EC-7: 정확히 7개)에는 포함되지 않는다.
    def __enter__(self) -> "BusLogRepo":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        try:
            self.conn.close()
        except Exception:  # 종료 경로에서 close 실패가 새 예외를 만들지 않게(ADR-013)
            pass
        return False  # 블록 내부 예외를 삼키지 않는다

    # ---- 내부 헬퍼 -------------------------------------------------------
    def _row(self, r) -> LogRow:
        return LogRow(idx=r[0], stop_id=r[1], route_id=r[2], route_nm=r[3],
                      vehicle_no=r[4], stop_name=r[5])

    def _where(self, route_id, stop_id, vehicle_no, day) -> tuple[str, tuple]:
        ph = self._ph
        clauses: list[str] = []
        args: list = []
        if route_id is not None:
            clauses.append(f"route_id = {ph}")
            args.append(route_id)
        if stop_id is not None:
            clauses.append(f"stop_id = {ph}")
            args.append(stop_id)
        if vehicle_no is not None:
            clauses.append(f"vehicle_number = {ph}")
            args.append(vehicle_no)
        if day is not None:
            daystr = day.strftime("%Y%m%d") if hasattr(day, "strftime") else str(day)
            clauses.append(f"idx LIKE {ph}")
            args.append(f"{daystr}_%")
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        return where, tuple(args)

    @staticmethod
    def _check_filters(filters: dict) -> None:
        # **filters의 오타(예: routeid)가 조용히 '전체'로 집계되는 foot-gun 방지.
        unknown = set(filters) - _FILTER_KEYS
        if unknown:
            raise TypeError(f"알 수 없는 필터 키 {sorted(unknown)} (허용: {sorted(_FILTER_KEYS)})")

    def _count_where(self, where: str, args: tuple) -> int:
        cur = self.conn.cursor()
        cur.execute(f"SELECT COUNT(*) FROM bus_timelog{where}", args)
        return int(cur.fetchone()[0])

    # ---- Write (W6a) ----------------------------------------------------
    def insert_log(self, *, idx: str, stop_id: str, route_id: str, vehicle_no: str,
                   stop_name: str | None = None) -> None:
        ph = self._ph
        sql = (f"INSERT INTO bus_timelog (idx, stop_id, route_id, vehicle_number, stop_name) "
               f"VALUES ({ph}, {ph}, {ph}, {ph}, {ph})")
        cur = self.conn.cursor()
        cur.execute(sql, (idx, stop_id, route_id, vehicle_no, stop_name))
        self.conn.commit()

    def insert_batch(self, rows: Iterable[LogRow]) -> int:
        """한 트랜잭션으로 묶어 마지막에 1회 commit. 예외 시 rollback(부분 commit 방지, H5)."""
        ph = self._ph
        sql = (f"INSERT INTO bus_timelog (idx, stop_id, route_id, vehicle_number, stop_name) "
               f"VALUES ({ph}, {ph}, {ph}, {ph}, {ph})")
        cur = self.conn.cursor()
        count = 0
        try:
            for r in rows:
                cur.execute(sql, (r.idx, r.stop_id, r.route_id, r.vehicle_no, r.stop_name))
                count += 1
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        return count

    # ---- Read (W6b) -----------------------------------------------------
    def query_paged(self, *, route_id: str | None = None, stop_id: str | None = None,
                    vehicle_no: str | None = None, day: date | None = None,
                    page: int = 1, size: int = 100) -> PagedResult[LogRow]:
        where, args = self._where(route_id, stop_id, vehicle_no, day)
        total = self._count_where(where, args)
        ph = self._ph
        offset = (page - 1) * size
        sql = (f"SELECT {_COLS} FROM bus_timelog{where} ORDER BY idx "
               f"LIMIT {ph} OFFSET {ph}")
        cur = self.conn.cursor()
        cur.execute(sql, (*args, size, offset))
        rows = [self._row(r) for r in cur.fetchall()]
        return PagedResult(rows=rows, total=total, page=page, size=size)

    def count(self, **filters) -> int:
        self._check_filters(filters)
        where, args = self._where(filters.get("route_id"), filters.get("stop_id"),
                                  filters.get("vehicle_no"), filters.get("day"))
        return self._count_where(where, args)

    def get_by_route(self, route_id: str, *, day: date | None = None) -> list[LogRow]:
        where, args = self._where(route_id, None, None, day)
        sql = f"SELECT {_COLS} FROM bus_timelog{where} ORDER BY idx"
        cur = self.conn.cursor()
        cur.execute(sql, args)
        return [self._row(r) for r in cur.fetchall()]

    def latest_node_per_vehicle(self, *, since: datetime) -> dict[tuple[str, str], str]:
        """(route_id, vehicle_no) → 가장 최근 통과 stop_id. warm_from_repo가 사용(H2)."""
        ph = self._ph
        since_str = since.strftime("%Y%m%d_%H:%M:%S")
        sql = (f"SELECT route_id, vehicle_number, stop_id FROM bus_timelog "
               f"WHERE idx >= {ph} ORDER BY idx")
        cur = self.conn.cursor()
        cur.execute(sql, (since_str,))
        result: dict[tuple[str, str], str] = {}
        for route_id, vehicle_no, stop_id in cur.fetchall():
            result[(route_id, vehicle_no)] = stop_id  # 오름차순이라 마지막=최신
        return result

    def export_csv(self, *, max_rows: int = 10000, **filters) -> Iterator[bytes]:
        """UTF-8 BOM 선두 + 헤더 + 행. 엑셀 한글 깨짐 방지.

        NOTE(P5/ADR-009): 셀 선두 `=`/`+`/`-`/`@`/탭/CR 로 인한 CSV formula injection을
        선두 `'` 접두어로 무력화한다 (OWASP CSV-injection guidance, P1 §7 R4).
        """
        self._check_filters(filters)
        yield b"\xef\xbb\xbf"  # UTF-8 BOM
        yield (_COLS.replace(" ", "") + "\n").encode("utf-8")
        where, args = self._where(filters.get("route_id"), filters.get("stop_id"),
                                  filters.get("vehicle_no"), filters.get("day"))
        ph = self._ph
        sql = f"SELECT {_COLS} FROM bus_timelog{where} ORDER BY idx LIMIT {ph}"
        cur = self.conn.cursor()
        cur.execute(sql, (*args, max_rows))
        for r in cur.fetchall():
            line = ",".join(_sanitize_csv_cell(v) for v in r) + "\n"
            yield line.encode("utf-8")
