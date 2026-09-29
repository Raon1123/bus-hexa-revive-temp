"""국토부(TAGO) 열차정보·지하철정보 API 클라이언트 + 순수 파서 (부산 루트 안내).

- ``TrainInfo/GetStrtpntAlocFndTrainInfo`` : 출·도착역 + 날짜별 열차(KTX·KTX-이음·ITX-마음·무궁화)
- ``SubwayInfo/GetSubwaySttnAcctoSchdulList`` : 도시·광역철도 역별 시간표(동해선 광역전철)

2022년 이전 경로(``TrainInfoService/getStrtpntAlocFndTrainInfo``)는 폐기됐다(resultCode 12).
신규 GW 엔드포인트는 오퍼레이션 이름이 대문자로 시작하고 오류를 JSON 게이트웨이 봉투로 준다 —
본문 검사는 ``tago.get_tago_json`` 이 공용으로 한다.

실측 이상동작(2026-09-29):
- 열차정보는 ``numOfRows``/``pageNo`` 를 무시하고 매 페이지 전량을 준다. 반대로 지하철정보는
  페이지를 지킨다. 두 경우 모두 (식별키) 중복 제거 + ``totalCount`` 도달까지 페이지를 넘기고,
  끝내 모자라면 ``ParseError`` 로 올려 부분 결과가 저장되지 않게 한다.
- 지하철 시각은 ``HHMMSS`` 문자열이고 해당 없음은 ``"0"`` 이다.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime

from bushexa.api_clients._http import resolve_api_timeout
from bushexa.api_clients.errors import ParseError
from bushexa.api_clients.tago import _items_as_list, get_tago_json
from bushexa.time_utils import KST

logger = logging.getLogger("bushexa.api_clients.tago_rail")

_TRAIN_URL = "https://apis.data.go.kr/1613000/TrainInfo/GetStrtpntAlocFndTrainInfo"
_SUBWAY_URL = "https://apis.data.go.kr/1613000/SubwayInfo/GetSubwaySttnAcctoSchdulList"

_ROWS = 500
_MAX_PAGES = 10


@dataclass(frozen=True)
class Train:
    train_no: str
    grade: str             # traingradename (예: KTX, KTX-산천(A-type), KTX-이음, ITX-마음, 무궁화호)
    dep_station: str
    arr_station: str
    dep_at: datetime       # KST aware
    arr_at: datetime       # KST aware (자정을 넘기면 다음 날)
    adult_charge: int | None


@dataclass(frozen=True)
class MetroStopTime:
    station_id: str
    station_name: str
    route_id: str
    end_station_id: str
    end_station_name: str
    dep_time: str | None   # "HH:MM:SS" — 해당 역 출발 없음(종착)이면 None
    arr_time: str | None   # "HH:MM:SS" — 해당 역 도착 없음(기점)이면 None
    day_type: str          # 01 평일 / 02 토 / 03 일·공휴일
    direction: str         # U 상행 / D 하행


def _parse_plan_time(value) -> datetime:
    """``YYYYMMDDHHMMSS``(문자열 또는 정수) → KST aware datetime."""
    s = str(value).strip()
    if len(s) != 14 or not s.isdigit():
        raise ParseError(f"열차 시각 형식 오류: {value!r}")
    try:
        return datetime.strptime(s, "%Y%m%d%H%M%S").replace(tzinfo=KST)
    except ValueError as exc:
        raise ParseError(f"열차 시각 형식 오류: {value!r}") from exc


def _parse_hhmmss(value) -> str | None:
    """지하철 시각 ``HHMMSS`` → ``HH:MM:SS``. ``"0"``/빈 값은 None(해당 없음)."""
    s = str(value if value is not None else "").strip()
    if s in ("", "0"):
        return None
    if len(s) != 6 or not s.isdigit() or int(s[:2]) > 29 or int(s[2:4]) > 59 or int(s[4:]) > 59:
        raise ParseError(f"지하철 시각 형식 오류: {value!r}")
    return f"{s[:2]}:{s[2:4]}:{s[4:]}"


def parse_trains(resp_json: dict) -> list[Train]:
    """열차정보 응답 JSON → Train 목록. 필수 필드 누락·형식 오류는 ParseError."""
    out: list[Train] = []
    for item in _items_as_list(resp_json["response"]["body"]):
        try:
            charge = item.get("adultcharge")
            out.append(Train(
                train_no=str(item["trainno"]),
                grade=str(item["traingradename"]),
                dep_station=str(item["depplacename"]),
                arr_station=str(item["arrplacename"]),
                dep_at=_parse_plan_time(item["depplandtime"]),
                arr_at=_parse_plan_time(item["arrplandtime"]),
                adult_charge=int(charge) if str(charge or "").strip().isdigit() else None,
            ))
        except KeyError as exc:
            raise ParseError(f"열차 item에 필수 필드 누락: {exc}") from exc
    return out


def parse_metro_schedule(resp_json: dict) -> list[MetroStopTime]:
    """지하철 역별 시간표 응답 JSON → MetroStopTime 목록."""
    out: list[MetroStopTime] = []
    for item in _items_as_list(resp_json["response"]["body"]):
        try:
            out.append(MetroStopTime(
                station_id=str(item["subwayStationId"]),
                station_name=str(item.get("subwayStationNm", "")),
                route_id=str(item.get("subwayRouteId", "")),
                end_station_id=str(item.get("endSubwayStationId", "")),
                end_station_name=str(item.get("endSubwayStationNm", "")),
                dep_time=_parse_hhmmss(item.get("depTime")),
                arr_time=_parse_hhmmss(item.get("arrTime")),
                day_type=str(item["dailyTypeCode"]),
                direction=str(item["upDownTypeCode"]),
            ))
        except KeyError as exc:
            raise ParseError(f"지하철 시간표 item에 필수 필드 누락: {exc}") from exc
    return out


def _collect_pages(fetch_page, parse, key) -> list:
    """``totalCount`` 에 닿을 때까지 페이지를 모은다(중복 제거). 모자라면 ParseError.

    열차정보처럼 페이지 인자를 무시하고 전량을 주는 응답도, 지하철정보처럼 페이지를 지키는
    응답도 같은 경로로 처리한다. 새 항목이 없는 페이지가 오면 더 넘기지 않는다.
    완결성은 중복 제거 전 행 수로 판정한다 — 열차정보는 같은 열차를 도착시각만 1분 다르게
    두 번 주기도 한다(2026-10-09 태화강→부전 00705, totalCount 24 = 고유 23 + 중복 1).
    중복이면 먼저 온 행을 쓴다.
    """
    seen: dict = {}
    total = 0
    raw = 0
    for page in range(1, _MAX_PAGES + 1):
        data = fetch_page(page)
        total = int(data["response"]["body"].get("totalCount", 0) or 0)
        rows = parse(data)
        fresh = 0
        for row in rows:
            k = key(row)
            if k not in seen:
                seen[k] = row
                fresh += 1
        if fresh == 0:
            break
        raw += len(rows)
        if raw >= total:
            break
    if raw < total:
        raise ParseError(f"페이지 수집 불완전: {raw}/{total}건")
    if len(seen) < raw:
        logger.info("중복 행 %d건 제거(고유 %d건)", raw - len(seen), len(seen))
    return list(seen.values())


class TrainInfoClient:
    """TAGO 열차정보. 호출자는 워커여야 한다(공개 화면 금지 — ADR-010)."""

    def __init__(self, api_key: str, *, url: str = _TRAIN_URL, timeout: float | None = None):
        self.api_key = api_key
        self.url = url
        self.timeout = resolve_api_timeout(timeout)

    def fetch_trains(self, dep_id: str, arr_id: str, day: date) -> list[Train]:
        """``day`` 에 ``dep_id`` → ``arr_id`` 로 가는 열차 전체(출발시각순)."""
        def fetch_page(page: int) -> dict:
            return get_tago_json(self.url, self.api_key, {
                "_type": "json", "numOfRows": _ROWS, "pageNo": page,
                "depPlaceId": dep_id, "arrPlaceId": arr_id,
                "depPlandTime": day.strftime("%Y%m%d"),
            }, timeout=self.timeout)

        trains = _collect_pages(fetch_page, parse_trains, lambda t: (t.train_no, t.dep_at))
        return sorted(trains, key=lambda t: t.dep_at)


class SubwayInfoClient:
    """TAGO 지하철정보(동해선 광역전철 포함)."""

    def __init__(self, api_key: str, *, url: str = _SUBWAY_URL, timeout: float | None = None):
        self.api_key = api_key
        self.url = url
        self.timeout = resolve_api_timeout(timeout)

    def fetch_station_schedule(self, station_id: str, day_type: str,
                               direction: str) -> list[MetroStopTime]:
        """역·요일구분·방향별 시간표 전체(응답 순서 유지)."""
        def fetch_page(page: int) -> dict:
            return get_tago_json(self.url, self.api_key, {
                "_type": "json", "numOfRows": _ROWS, "pageNo": page,
                "subwayStationId": station_id, "dailyTypeCode": day_type,
                "upDownTypeCode": direction,
            }, timeout=self.timeout)

        return _collect_pages(
            fetch_page, parse_metro_schedule,
            lambda m: (m.dep_time, m.arr_time, m.end_station_id),
        )
