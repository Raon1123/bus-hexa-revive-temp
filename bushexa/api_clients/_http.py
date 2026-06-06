"""data.go.kr 계열 OpenAPI HTTP GET 공용 헬퍼.

serviceKey 이중 인코딩 방지를 단일 지점에서 보장한다(리뷰 reuse 항목 — holiday.py
회귀(C1)의 근본 원인 제거). secret/key.txt가 'Encoding 키'(%2B 등 %-인코딩 포함)면
requests가 다시 인코딩해 %25..가 되어 SERVICE_KEY_IS_NOT_REGISTERED_ERROR가 난다.
unquote로 먼저 디코딩하면 Encoding/Decoding 키 양쪽 모두 requests가 1회만 인코딩해
올바른 키가 전송된다.

오류 본문 검사는 API마다 포맷이 달라(TAGO JSON+XML 폴백, 울산 BIS·공휴일 XML)
호출자가 수행한다 — 이 모듈은 전송 계층만 책임진다.
"""
from __future__ import annotations

import os
from urllib.parse import unquote

import requests

# 울산 API 간헐 무응답·느린 응답 실측(2026-06-05)에 맞춰 기본 15초.
# env BUSHEXA_API_TIMEOUT_SECONDS로 운영자가 조정한다(예: 10).
_DEFAULT_TIMEOUT = 15.0


def resolve_api_timeout(explicit=None) -> float:
    """API HTTP timeout 해석: 명시 인자 > env ``BUSHEXA_API_TIMEOUT_SECONDS`` > 15초."""
    if explicit is not None:
        return float(explicit)
    return float(os.environ.get("BUSHEXA_API_TIMEOUT_SECONDS", _DEFAULT_TIMEOUT))


def get_with_service_key(url: str, api_key: str, params: dict, *,
                         timeout: float) -> requests.Response:
    """serviceKey를 안전하게(1회 인코딩) 실어 GET. 네트워크 예외는 그대로 전파."""
    merged = {"serviceKey": unquote(api_key), **params}
    return requests.get(url, params=merged, timeout=timeout)
