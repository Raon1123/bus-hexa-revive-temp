"""공휴일 API(B090041 SpcdeInfoService/getRestDeInfo) 클라이언트.

응답 XML의 ``<locdate>``(YYYYMMDD)를 ``datetime.date``로 변환한다. stateless —
캐시는 상위 service 책임(ADR-011/time_utils와 연계).

ADR-013: 호출 실패·오류 응답은 :class:`HolidayError` 등으로 **raise**한다(빈 리스트 반환
금지). data.go.kr는 키/쿼터 오류를 HTTP 200 XML 본문으로 주므로, 검사 없이 파싱하면
'공휴일 없는 달'과 구분되지 않아 HolidayCache가 정상 캐시를 빈 값으로 덮어쓴다
(2026-06-05 리뷰). 호출자(HolidayCache.refresh / admin sync / _fetch_api_holidays)는
모두 예외를 잡아 기존 캐시 보존·오류 표시로 강등한다.
"""
from __future__ import annotations

import datetime as _dt
import logging
from urllib.parse import unquote

import requests
from bs4 import BeautifulSoup

from bushexa.api_clients.errors import HolidayError

logger = logging.getLogger("bushexa.api_clients.holiday")

_HOLIDAY_URL = "http://apis.data.go.kr/B090041/openapi/service/SpcdeInfoService/getRestDeInfo"


def check_response(xml_text: str | bytes) -> None:
    """응답 본문이 정상(resultCode '00')인지 검사, 아니면 :class:`HolidayError` raise.

    오류 형태 2종을 모두 처리한다(둘 다 HTTP 200으로 옴):
    - 서비스 오류: ``<response><header><resultCode>NN</resultCode>`` (NN != 00)
    - 게이트웨이 오류: ``<OpenAPI_ServiceResponse><cmmMsgHeader><returnReasonCode>NN``
      (SERVICE_KEY_IS_NOT_REGISTERED_ERROR, LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS 등)
    """
    soup = BeautifulSoup(xml_text, "html.parser")
    code_tag = soup.find("resultcode")
    if code_tag is not None:
        code = code_tag.text.strip()
        if code == "00":
            return
        msg_tag = soup.find("resultmsg")
        raise HolidayError(code, f"{code} {msg_tag.text.strip() if msg_tag else ''}".strip())
    reason_tag = soup.find("returnreasoncode")
    auth_tag = soup.find("returnauthmsg")
    if reason_tag is not None or auth_tag is not None:
        code = reason_tag.text.strip() if reason_tag else "GATEWAY"
        msg = auth_tag.text.strip() if auth_tag else ""
        raise HolidayError(code, f"게이트웨이 오류 {code} {msg}".strip())
    raise HolidayError("NO_HEADER", f"응답에 resultCode 없음: {str(xml_text)[:120]!r}")


def parse_holidays(xml_text: str | bytes) -> list[_dt.date]:
    """공휴일 XML → date 목록. `<locdate>`가 없으면 빈 리스트."""
    out: list[_dt.date] = []
    for tag in BeautifulSoup(xml_text, "html.parser").find_all("locdate"):
        raw = tag.text.strip()  # "YYYYMMDD"
        try:
            out.append(_dt.datetime.strptime(raw, "%Y%m%d").date())
        except ValueError:
            logger.warning("locdate 형식 오류, 건너뜀: %r", raw)
    return out


class HolidayClient:
    def __init__(self, api_key: str, *, base_url: str = _HOLIDAY_URL, timeout: float = 10.0):
        self.api_key = api_key
        self.base_url = base_url
        self.timeout = timeout

    def fetch(self, year: int, month: int) -> list[_dt.date]:
        """해당 월의 공휴일 date 목록. 네트워크 오류·오류 응답은 raise(모듈 docstring 참조)."""
        # 서비스키 이중 인코딩 방지 — tago.py/ulsan_bis.py와 동일(unquote 후 requests가 1회
        # 인코딩). 이 클라이언트만 빠뜨려 Encoding 키에서 SERVICE_KEY 오류가 나던 회귀 수정.
        params = {"serviceKey": unquote(self.api_key), "solYear": year,
                  "solMonth": f"{month:02d}"}
        resp = requests.get(self.base_url, params=params, timeout=self.timeout)
        check_response(resp.content)
        return parse_holidays(resp.content)
