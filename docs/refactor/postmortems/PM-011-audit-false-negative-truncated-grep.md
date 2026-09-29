---
status: resolved
postmortem_id: PM-011
severity: low
discovered: 2026-06-05
phase: 2차 웨이브 감리 (프로세스 결함)
component: 감리 프로세스 / bushexa.web.app (CSRF)
related: [code-review-2026-06-05.md:14-18, "tests/web/test_csrf.py"]
auditor_status: n/a (프로세스)
---

# PM-011 — 잘린 grep 출력으로 "CSRF 미구현"이라는 잘못된 감리 결론

> 부검(postmortem)은 **비난이 아니라 재발 방지**를 위한 기록이다. 사람이 아니라 시스템·프로세스의 결함을 본다.

## 1. 요약 (3줄)

- **증상:** 2차 웨이브 감리가 "bushexa/ 어디에도 서버측 CSRF 생성·검증이 없다(죽은 패턴)"고 리뷰 문서에 기록했다.
- **근본 원인:** 검색 결과를 `| head` 로 잘랐고, `.py` 매치가 잘린 부분에 있었다. 실제로는 `web/app.py` 에 완전히 구현되어 있었고 `tests/web/test_csrf.py` 도 baseline 부터 존재했다.
- **재발 방지:** "없다"는 부정 주장은 잘리지 않은 검색(`grep -rl`, 개수) + 기존 테스트 확인 후에만 쓴다.

## 2. 영향 (Impact)

- 코드 결함은 없었다. 잘못된 결론으로 불필요한 재작업 지시가 나갈 뻔했다.
- 유효한 잔여 개선 1건: `!=` 비교를 `hmac.compare_digest`(UTF-8 bytes)로 교체(`86ad2ce`). bytes 로 비교하는 이유는 비-ASCII str 이 `TypeError` → 500 을 내기 때문.

## 3. 타임라인

- `8d5b30b`(2026-06-05) 리뷰 문서에 "CSRF 미구현" 기록.
- 3차 웨이브 감리(`6114da3`)에서 오류 발견, 문서에 취소선 + 정정.

## 4. 근본 원인 분석

- 검색 명령이 템플릿(`.html`) 매치로 출력 앞부분을 채웠고, `head` 가 나머지를 버렸다.
- 부재 주장에 대한 반증 절차(관련 테스트 파일 검색)가 없었다.

## 5. 재현

```bash
grep -rn csrf bushexa | head -5          # 템플릿만 보인다
grep -rln csrf bushexa --include=*.py    # app.py 가 보인다
```

## 6. 해결

- 리뷰 문서 정정(`code-review-2026-06-05.md:14-18`), `web/app.py` compare_digest 개선.

## 7. 재발 방지 (Prevention) — **필수**

- [x] **회귀 테스트**: `tests/web/test_csrf.py::test_csrf_missing_token_rejected`, `::test_csrf_wrong_token_rejected`, `::test_csrf_correct_token_passes`.
- [ ] 비-ASCII 토큰이 400(500 아님)을 내는 테스트는 아직 없다.
- [x] **프로세스**: `docs/guide/pitfalls.md` §7 "부재 주장 규칙". CLAUDE.md 작업 규칙에도 반영.

## 8. 교훈

- 존재 증명은 매치 1개로 충분하지만, **부재 증명은 전수 검색**이 필요하다. 출력 자르기(`head`, `tail`, 페이지 제한)는 부재 증명을 무효로 만든다.
- 파일 목록(`-l`)과 개수(`-c`)로 먼저 보고, `--include=*.py` 로 좁힌다.
- 결론 전에 "이 기능을 검증하는 테스트가 이미 있나?"를 찾는다.
