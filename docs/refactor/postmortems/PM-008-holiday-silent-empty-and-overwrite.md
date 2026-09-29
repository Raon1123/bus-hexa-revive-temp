---
status: verified
postmortem_id: PM-008
severity: high
discovered: 2026-06-05
phase: 코드리뷰 (/code-review high, 전체 패키지)
component: bushexa.api_clients.holiday, bushexa.services.holiday_service, bushexa.crawler.timetable_crawl
related: [review #1 #2 #3 C1, ADR-013, "tests/api_clients/test_holiday.py", "tests/services/test_holiday_cache.py", "tests/crawler/test_timetable_crawl.py"]
auditor_status: pass (commit f2ecd93, 86ad2ce)
---

# PM-008 — 공휴일 API 오류가 "공휴일 없음"으로 삼켜지고, 실패 결과가 좋은 캐시·시간표를 덮어씀

> 부검(postmortem)은 **비난이 아니라 재발 방지**를 위한 기록이다. 사람이 아니라 시스템·프로세스의 결함을 본다.

## 1. 요약 (3줄)

- **증상:** 공휴일에도 평일 시간표가 표시될 수 있었다. 시간표 재크롤이 0행 결과로 멀쩡한 `data/timetable/<노선>.json` 을 비울 수 있었다.
- **근본 원인:** "빈 결과"와 "오류"를 구분하지 않았다. data.go.kr 계열 API는 **HTTP 200 + 오류 XML** 로 실패를 알리는데 본문을 검사하지 않았고, 실패 결과를 그대로 저장했다.
- **재발 방지:** 클라이언트별 `check_response()` 로 오류 XML을 예외로 올리고, 실패 시 기존 캐시·파일을 보존하는 가드와 serviceKey 공통 헬퍼(`get_with_service_key`)를 도입했다.

## 2. 영향 (Impact)

- 공휴일 판정 → 출발 게시판·UNIST 보드의 시간표 선택(요일 코드 2 대신 0).
- 시간표 JSON 전체 유실 가능(재크롤 시).
- 운영에서 관찰되기 전에 코드리뷰로 발견. 데이터 손상 기록 없음.

## 3. 타임라인 (발견 경위)

- 2026-06-05 전체 패키지 `/code-review`(high)에서 #1~#3 으로 보고. 같은 날 baseline 커밋 `f2ecd93` 에 긴급 수정 포함.
- 2026-06-06 `86ad2ce` 에서 serviceKey 보일러플레이트 4벌을 `_http.get_with_service_key` 로 통합(C1).
- 수정 전 코드는 root 커밋 이전이라 git 에 없다. "수정 전" 상태는 `docs/refactor/code-review-2026-06-05.md` 에만 남아 있다.

## 4. 근본 원인 분석 (Root Cause)

인과 사슬:

1. data.go.kr 인증키는 "Encoding" 판(`%2B` 등)으로 발급된다. `requests` 가 params 를 다시 인코딩하면 `%252B` 가 된다.
2. `tago.py`·`ulsan_bis.py` 는 `unquote()` 했지만 `holiday.py` 만 빠졌다(보일러플레이트 복제의 결과).
3. API는 `SERVICE_KEY_IS_NOT_REGISTERED_ERROR` 를 HTTP 200 XML로 반환한다.
4. `parse_holidays` 는 `<locdate>` 0개 → `[]` 반환. 호출자는 "이 달엔 공휴일 없음"으로 해석.
5. `HolidayCache.refresh` 가 `[]` 를 저장해 좋은 캐시 월을 덮어씀.
6. 같은 패턴으로 `crawl_all_timetables` 가 0행 결과를 그대로 원자 저장.

기존 테스트가 못 잡은 이유: 픽스처가 정상 응답만 있었고, 오류 XML 픽스처와 "실패 후 캐시 보존" 시나리오가 없었다.

## 5. 재현 (Reproduction)

```bash
uv run python -m pytest tests/api_clients/test_holiday.py -q -k "double_encoded or error_raises"
```

- 기대: 오류 XML → `HolidayError`. 실제(수정 전): `[]`.

## 6. 해결 (Resolution)

- `bushexa/api_clients/holiday.py` `check_response()` — resultCode≠00 또는 게이트웨이 오류 XML(`returnReasonCode`)이면 `HolidayError`.
- `bushexa/api_clients/ulsan_bis.py` `check_response()` + `errors.py` 에 `HolidayError`/`UlsanBisError`.
- `bushexa/services/holiday_service.py` — 예외 시 해당 월 캐시 유지.
- `bushexa/crawler/timetable_crawl.py` — `if not any(table.values())` 이면 실패로 집계하고 기존 파일 보존.
- `bushexa/api_clients/_http.py` `get_with_service_key` — unquote 를 한 곳에서.

## 7. 재발 방지 (Prevention) — **필수**

- [x] **회귀 테스트**:
  - `tests/api_clients/test_holiday.py::test_service_key_not_double_encoded` — 인코딩된 키가 이중 인코딩되지 않는다.
  - `tests/api_clients/test_holiday.py::test_gateway_error_raises`, `::test_result_code_error_raises` — 오류 XML 은 빈 리스트가 아니라 예외다.
  - `tests/api_clients/test_ulsan_bis.py::test_timetable_gateway_error_raises` — 울산 시간표도 동일.
  - `tests/services/test_holiday_cache.py::test_refresh_preserves_other_months_on_failure` — 실패는 좋은 캐시를 덮지 않는다.
  - `tests/crawler/test_timetable_crawl.py::test_all_empty_crawl_preserves_existing_file` — 전부 빈 크롤은 파일을 보존한다.
- [x] **코드 가드**: serviceKey 처리 단일화(`get_with_service_key`), 클라이언트별 `check_response`.
- [x] **프로세스**: `docs/guide/pitfalls.md` §1 "빈 결과 ≠ 오류" 항목.

## 8. 교훈 (Lessons)

- 공공 API는 실패를 HTTP 200 으로 준다. **상태 코드가 아니라 본문의 resultCode 를 검사**한다.
- 실패 결과로 "알려진 좋은 값"을 덮어쓰지 않는다. 캐시·파일 쓰기 전에 "비어 있으면 저장하지 않음" 가드.
- 교차 관심사(키 인코딩, timeout)는 클라이언트마다 복제하지 말고 헬퍼 하나로. 복제본 하나만 빠져도 이런 결함이 난다.
- 관련: [PM-003](PM-003-xml-response-encoding.md)(같은 XML 계층), [PM-001](PM-001-govtrack-missing-passage-logs.md)(resultCode 를 print 만 하던 결함).

## 9. 상태

- 수정 커밋: `f2ecd93`, `86ad2ce`
- 회귀 테스트 통과 확인: 2026-09-29 전체 563 passed
- Auditor 확인: 코드리뷰 문서 잔여 항목 종결 표기
