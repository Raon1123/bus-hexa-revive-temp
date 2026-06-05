---
status: resolved
pm_id: PM-003
phase: P1
author: opus
last_updated: 2026-06-01
severity: low
related: [P1-data-layer, ADR-013]
---

# PM-003 — 울산/공휴일 XML 응답의 한글이 깨짐 (requests `resp.text` latin-1 기본값)

P1 W8(UlsanBisClient) 실행 감리 중 `test_parse_arrivals`가 실패하며 발견. 외부 XML API
응답의 한글이 mojibake로 디코딩되던 문제. 즉시 수정·회귀 테스트 확보. **P2(arrival poller)와
이후 모든 외부 XML 파싱에 동일 함정이 재현되지 않도록** 규약화한다.

## 요약

| 증상 | 근본 원인 | 수정 | 재발 방지 |
|---|---|---|---|
| `arrivals[0].present_stop`이 `다운동` 대신 `ë¤ì´ë`로 나와 단언 실패 | `requests`는 `Content-Type`이 `text/*`이고 **charset이 없으면 RFC 2616에 따라 ISO-8859-1**로 본문을 디코딩한다. `resp.text`가 UTF-8 한글을 latin-1로 오역 | 클라이언트가 `resp.text` 대신 **`resp.content`(bytes)** 를 파서에 전달 → BeautifulSoup이 XML 선언(`encoding="UTF-8"`)으로 인코딩을 검출 | **규약 D-3** |

## 상세

- **기대:** 도착정보 XML의 `<presentstopnm>다운동</presentstopnm>`이 그대로 `다운동`으로 파싱.
- **실제:** `다운동`(UTF-8 9바이트)이 latin-1로 디코딩되어 `ë¤ì´ë`. 테스트 fixture는 정상 UTF-8이었고, 코드 경로(`resp.text`)가 문제.
- **근본 원인:** 울산/공휴일 API mock 응답이 `charset`를 헤더에 싣지 않음(실 API도 자주 누락). `requests`는 이때 latin-1을 가정. XML은 **자체 인코딩 선언**을 가지므로 헤더 charset에 의존하면 안 된다.
- **왜 legacy는 안 터졌나:** 실 API가 charset 헤더를 주거나, 운영 환경 차이로 가려졌을 뿐 동일 잠재 결함. 리팩토링 테스트(charset 없는 fixture)가 이를 드러냈다.

## 재발 방지 규약 (P1~P5 적용)

- **D-3 (외부 XML 디코딩):** 외부 XML API 응답은 `resp.text`가 아니라 **`resp.content`(bytes)** 로 파서에 넘긴다. XML은 자체 인코딩 선언으로 디코딩하므로 HTTP charset 헤더 유무에 무관하게 안전하다. 테스트는 fixture를 `read_bytes()`로 제공해 결정적으로 만든다.
  - (참고) `html.parser` 사용 시 뜨는 `XMLParsedAsHTMLWarning`은 무해하며 `pyproject` `[tool.pytest.ini_options] filterwarnings`로 억제(legacy와 동일하게 lxml 의존 회피).

## 회귀 테스트 매핑

- D-3: `tests/api_clients/test_ulsan_bis.py::test_parse_arrivals` 가 한글 정류장명(`다운동`)·차량번호(`울산70바1234`)를 직접 비교 → latin-1 회귀 시 즉시 FAIL.
- 동일 규약을 `holiday.py`(`resp.content`)에도 선반영(현재 locdate는 ASCII라 무증상이나 일관성·안전).
