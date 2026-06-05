"""울산 BIS(openapi.its.ulsan.kr) 도착정보·시간표 XML API 클라이언트 + 순수 파서.

- ``getBusArrivalInfo.xo`` : 정류장 실시간 도착정보 (`<row>` 단위, arrivaltime=초)
- ``BusTimetable.xo``      : 노선 시간표 (`<row>`의 time=HHMM, direction=int)

ADR-010: 화면은 이 클라이언트를 직접 호출하지 않고 백업본(bus_arrival_cache)을 읽는다.
이 클라이언트는 arrival poller(P2)가 사용한다. ADR-013: 네트워크 오류는 로그 후 빈 리스트로
처리해 호출자 루프가 죽지 않게 한다(빈 결과와 오류 로그를 구분).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from urllib.parse import unquote

import requests
from bs4 import BeautifulSoup

from bushexa.api_clients.errors import ParseError, UlsanBisError

logger = logging.getLogger("bushexa.api_clients.ulsan_bis")

_ARRIVAL_URL = "http://openapi.its.ulsan.kr/UlsanAPI/getBusArrivalInfo.xo"
_TIMETABLE_URL = "http://openapi.its.ulsan.kr/UlsanAPI/BusTimetable.xo"


@dataclass(frozen=True)
class Arrival:
    route_id: str
    present_stop: str
    vehicle_no: str
    arrival_time: int  # 초


@dataclass(frozen=True)
class TimetableRow:
    time: str  # "HH:MM"
    direction: int


def _soup(xml: str | bytes) -> BeautifulSoup:
    # bytes를 받으면 BeautifulSoup이 XML 선언(encoding="UTF-8")으로 인코딩을 검출한다.
    # 응답 charset 헤더 누락 시 requests가 latin-1로 오역하는 문제를 피하려면 bytes를 넘긴다.
    return BeautifulSoup(xml, "html.parser")


def check_response(xml_text: str | bytes, *, http_status: int = 200) -> None:
    """응답이 정상인지 검사, 아니면 :class:`UlsanBisError` raise.

    BIS 명세(v4.2): 모든 정상 응답의 ``<tableInfo>``에 ``resultCode``(200=정상, 300=실패)가
    있다. 키/쿼터 오류는 data.go.kr 게이트웨이 형식(``returnReasonCode``)으로 올 수 있고
    둘 다 HTTP 200이므로 본문을 검사해야 '빈 결과(정상)'와 구분된다(2026-06-05 리뷰 —
    오류 응답이 빈 시간표로 파싱돼 기존 파일을 덮어쓰는 사고 방지). 알 수 없는 형태
    (resultCode·오류 마커 모두 부재)는 기존 동작대로 통과시킨다 — 과잉 차단 방지.
    """
    if http_status != 200:
        raise UlsanBisError(str(http_status), f"HTTP {http_status} 응답")
    soup = _soup(xml_text)
    code_tag = soup.find("resultcode")
    if code_tag is not None:
        code = code_tag.text.strip()
        if code != "200":
            msg_tag = soup.find("resultmsg")
            raise UlsanBisError(code, f"{code} {msg_tag.text.strip() if msg_tag else ''}".strip())
        return
    reason_tag = soup.find("returnreasoncode")
    auth_tag = soup.find("returnauthmsg")
    if reason_tag is not None or auth_tag is not None:
        code = reason_tag.text.strip() if reason_tag else "GATEWAY"
        msg = auth_tag.text.strip() if auth_tag else ""
        raise UlsanBisError(code, f"게이트웨이 오류 {code} {msg}".strip())


def parse_arrivals(xml_text: str | bytes) -> list[Arrival]:
    """도착정보 XML → Arrival 목록. `<row>`가 없으면 빈 리스트(정상)."""
    out: list[Arrival] = []
    for row in _soup(xml_text).find_all("row"):
        rid = row.find("routeid")
        present = row.find("presentstopnm")
        vno = row.find("vehicleno")
        atime = row.find("arrivaltime")
        if rid is None or present is None or vno is None or atime is None:
            logger.warning("arrival row에 필수 태그 누락, 건너뜀")  # silent swallow 금지(ADR-013)
            continue
        try:
            arrival_time = int(atime.text.strip())
        except ValueError:
            logger.warning("arrivaltime 정수 변환 실패: %r", atime.text)
            arrival_time = -1
        out.append(Arrival(route_id=rid.text.strip(), present_stop=present.text.strip(),
                           vehicle_no=vno.text.strip(), arrival_time=arrival_time))
    return out


def parse_timetable(xml_text: str | bytes) -> list[TimetableRow]:
    """시간표 XML → TimetableRow 목록. time "HHMM"→"HH:MM", direction은 int."""
    out: list[TimetableRow] = []
    for row in _soup(xml_text).find_all("row"):
        t = row.find("time")
        d = row.find("direction")
        if t is None or d is None:
            logger.warning("timetable row에 time/direction 누락, 건너뜀")
            continue
        raw = t.text.strip()
        hhmm = raw[:2] + ":" + raw[2:4]
        try:
            direction = int(d.text.strip())
        except ValueError as exc:
            raise ParseError(f"direction이 정수가 아님: {d.text!r}") from exc
        out.append(TimetableRow(time=hhmm, direction=direction))
    return out


def parse_timetable_page(xml_text: str | bytes) -> tuple[list[TimetableRow], int]:
    """시간표 XML → (행 목록, totalCnt). 페이지네이션 종료 조건 계산에 totalCnt를 쓴다(F10 off-by-one 수정)."""
    rows = parse_timetable(xml_text)
    tag = _soup(xml_text).find("totalcnt")
    raw = tag.text.strip() if tag is not None else ""
    total = int(raw) if raw.lstrip("-").isdigit() else len(rows)
    return rows, total


class UlsanBisClient:
    def __init__(self, api_key: str, *, arrival_url: str = _ARRIVAL_URL,
                 timetable_url: str = _TIMETABLE_URL, timeout: float = 10.0):
        self.api_key = api_key
        self.arrival_url = arrival_url
        self.timetable_url = timetable_url
        self.timeout = timeout

    def fetch_arrivals(self, stop_id: str, *, page: int = 1, rows: int = 50) -> list[Arrival]:
        params = {"serviceKey": unquote(self.api_key), "pageNo": page, "numOfRows": rows, "stopid": stop_id}
        try:
            resp = requests.get(self.arrival_url, params=params, timeout=self.timeout)
        except requests.exceptions.RequestException as exc:
            # ADR-013(의도된 비대칭): tago는 오류를 raise하지만, 도착정보 poller는 5~10초마다
            # 도는 루프이므로 일시적 네트워크 오류를 로그만 남기고 빈 결과로 흘려보내 '계속 돈다'.
            logger.error("울산 도착정보 호출 실패 stop_id=%s: %s", stop_id, exc)
            return []
        try:
            check_response(resp.content, http_status=resp.status_code)
        except UlsanBisError as exc:
            # 같은 비대칭: 오류 본문도 빈 결과로 강등하되, 침묵하지 않고 로그(ADR-013).
            logger.error("울산 도착정보 오류 응답 stop_id=%s: %s", stop_id, exc)
            return []
        return parse_arrivals(resp.content)  # bytes: XML 선언으로 인코딩 검출(charset 헤더 무관)

    def fetch_timetable(self, route_no, day_of_week: int, *, page: int = 1,
                        rows: int = 50) -> list[TimetableRow]:
        params = {"serviceKey": unquote(self.api_key), "pageNo": page, "numOfRows": rows,
                  "routeNo": route_no, "dayOfWeek": day_of_week}
        resp = requests.get(self.timetable_url, params=params, timeout=self.timeout)
        check_response(resp.content, http_status=resp.status_code)  # 오류 본문≠빈 시간표
        return parse_timetable(resp.content)

    def fetch_timetable_page(self, route_no, day_of_week: int, *, page: int = 1,
                             rows: int = 50) -> tuple[list[TimetableRow], int]:
        """한 페이지의 (행, totalCnt)를 반환. 시간표 크롤은 명시적 작업이므로 네트워크 오류·
        오류 응답은 raise한다(연속 도착 poller와 달리 — ADR-013 의도된 비대칭)."""
        params = {"serviceKey": unquote(self.api_key), "pageNo": page, "numOfRows": rows,
                  "routeNo": route_no, "dayOfWeek": day_of_week}
        resp = requests.get(self.timetable_url, params=params, timeout=self.timeout)
        check_response(resp.content, http_status=resp.status_code)  # 오류 본문≠빈 시간표
        return parse_timetable_page(resp.content)
