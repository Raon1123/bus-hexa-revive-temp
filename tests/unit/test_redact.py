"""bushexa.redact — API 인증키(serviceKey) 가림 규칙 (PM-016)."""

from __future__ import annotations

from bushexa.redact import REDACTED, redact_secrets

KEY = "AbCd%2BEf%2F123%3D%3D"


def test_redacts_service_key_in_request_url():
    """requests 예외 메시지 속 URL의 serviceKey 값만 가리고 나머지 파라미터는 보존한다 (PM-016)."""
    msg = ("HTTPConnectionPool(host='apis.data.go.kr', port=80): Max retries exceeded with url: "
           f"/B090041/openapi/service/SpcdeInfoService/getRestDeInfo?serviceKey={KEY}&solYear=2026&solMonth=06 "
           "(Caused by ReadTimeoutError)")
    out = redact_secrets(msg)
    assert KEY not in out
    assert f"serviceKey={REDACTED}&solYear=2026&solMonth=06" in out


def test_redacts_key_at_end_and_before_quote_or_paren():
    """값이 문자열 끝·따옴표·괄호에서 끝나는 경우도 값만 가린다 (urllib3 DEBUG 요청 줄 형태 포함)."""
    assert redact_secrets(f"GET /x?serviceKey={KEY}") == f"GET /x?serviceKey={REDACTED}"
    assert redact_secrets(f"'url?serviceKey={KEY}'") == f"'url?serviceKey={REDACTED}'"
    assert redact_secrets(f"(url?serviceKey={KEY})") == f"(url?serviceKey={REDACTED})"
    line = f'"GET /UlsanAPI/getBusArrivalInfo.xo?serviceKey={KEY}&pageNo=1 HTTP/1.1" 200 2500'
    assert KEY not in redact_secrets(line)


def test_case_and_underscore_variants():
    """ServiceKey·SERVICEKEY·service_key 표기 변형도 가린다."""
    for name in ("ServiceKey", "SERVICEKEY", "service_key"):
        assert KEY not in redact_secrets(f"?{name}={KEY}&a=1")


def test_multiple_occurrences_and_noop():
    """한 문자열의 여러 키를 모두 가리고, 키가 없는 문자열·빈 값은 그대로 둔다."""
    out = redact_secrets(f"a?serviceKey={KEY} b?serviceKey={KEY}")
    assert KEY not in out and out.count(REDACTED) == 2
    assert redact_secrets("plain message stop_id=196040234") == "plain message stop_id=196040234"
    assert redact_secrets("") == ""
