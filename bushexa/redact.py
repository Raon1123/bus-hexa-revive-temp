"""시크릿 가림(redaction) 단일 출처 — PM-016.

data.go.kr·울산 BIS API는 인증키를 쿼리스트링 ``serviceKey=`` 로 받는다. 그래서 요청 URL이
들어가는 모든 문자열(requests 예외 메시지 ``Max retries exceeded with url: ...?serviceKey=...``,
urllib3 DEBUG 요청 줄, 그 예외를 ``str(exc)`` 로 저장한 상태 파일)에 키가 섞인다.

이 모듈의 :func:`redact_secrets` 를 **기록 시점**에 적용한다.

- 로그: :class:`bushexa.logging_setup.KSTFormatter` 가 모든 출력(메시지·예외 트레이스백)에 적용
- 상태·진행 파일: ``services/arrival_status``, ``services/recrawl_job``
- 표시 계층 이중 방어: 관리자 로그 뷰어 ``_mask_secrets`` (이미 기록된 옛 로그 대비)
"""

from __future__ import annotations

import re

REDACTED = "***"

# serviceKey / ServiceKey / service_key = 값. 값은 쿼리 구분자(&)·공백·따옴표·괄호·꺾쇠에서 끝난다.
# 키 이름은 보존하고 값만 가려, 로그를 읽는 사람이 "키가 있었다"는 사실은 알 수 있게 한다.
_SERVICE_KEY_RE = re.compile(r"(?i)\b(service_?key)=[^&\s'\"()<>\]]+")


def redact_secrets(text: str) -> str:
    """문자열 안의 API 인증키 값을 ``***`` 로 치환한다. 해당 패턴이 없으면 원문 그대로."""
    if not text:
        return text
    return _SERVICE_KEY_RE.sub(lambda m: f"{m.group(1)}={REDACTED}", text)
