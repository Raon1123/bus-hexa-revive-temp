"""api_clients 계층 공통 예외.

ADR-013: 외부 호출은 "빈 결과(정상)"와 "오류"를 구분해 신호한다. 오류는 삼키지 말고
타입이 있는 예외로 올리거나 로그한다 — 호출자(데몬)가 격리·계속을 판단할 수 있도록.
"""
from __future__ import annotations


class ApiError(RuntimeError):
    """외부 API 호출/응답 관련 오류의 기반."""


class TagoError(ApiError):
    """국토부 TAGO 응답 resultCode가 정상('00')이 아님."""

    def __init__(self, result_code: str, message: str | None = None):
        self.result_code = result_code
        super().__init__(message or f"TAGO resultCode != '00': {result_code}")


class UlsanBisError(ApiError):
    """울산 BIS 응답 resultCode가 정상('200')이 아니거나 게이트웨이 오류 XML.

    오류 본문도 HTTP 200으로 오므로(키/쿼터 오류 등) 본문 검사 없이는 '빈 결과(정상)'와
    구분되지 않는다 — 빈 시간표로 기존 데이터를 덮어쓰는 사고의 근본 원인(2026-06-05 리뷰).
    """

    def __init__(self, result_code: str, message: str | None = None):
        self.result_code = result_code
        super().__init__(message or f"울산 BIS resultCode != '200': {result_code}")


class HolidayError(ApiError):
    """공휴일 API(data.go.kr) 응답 resultCode가 정상('00')이 아니거나 게이트웨이 오류 XML.

    키/쿼터 오류가 HTTP 200 XML로 오므로, 검사 없이 파싱하면 '공휴일 없는 달'과 구분되지
    않아 캐시가 빈 값으로 오염된다(2026-06-05 리뷰). 오류는 raise — 호출자(HolidayCache.refresh
    등)가 기존 캐시를 보존한다.
    """

    def __init__(self, result_code: str, message: str | None = None):
        self.result_code = result_code
        super().__init__(message or f"공휴일 API resultCode != '00': {result_code}")


class ParseError(ApiError):
    """응답 파싱 중 필수 필드 누락/형식 불일치."""
