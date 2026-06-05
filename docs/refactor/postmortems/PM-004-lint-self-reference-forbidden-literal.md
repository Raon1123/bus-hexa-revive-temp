---
status: resolved
postmortem_id: PM-004
severity: low
discovered: 2026-06-01
resolved: 2026-06-01
phase: P2 구현
component: bushexa.crawler (docstring) / tests lint
related: [P2, F09, F10]
---

# PM-004 — 금지 리터럴 lint가 "제거했다"는 설명 docstring을 오탐

## 1. 요약 (3줄)

- **증상:** "컨테이너 경로/streamlit 의존이 0건"을 단언하는 grep lint 테스트가, 그 의존을 **제거했다고
  설명하는 docstring** 안의 리터럴(`/app/logs`, `import streamlit`)에 매칭되어 실패했다.
- **근본 원인:** 금지 토큰을 substring 매칭하는 lint는 코드의 '사용'과 문서의 '언급'을 구분하지 못한다.
- **재발 방지:** lint 본문은 리터럴을 분할 구성하고, 소스 docstring은 금지 토큰의 정확한 형태를 피한다.

## 2. 영향

- 기능 영향 없음(런타임 코드는 정상). P2 구현 중 전체 스위트가 2회 적색 → 즉시 수정.
- 같은 패턴이 **두 번 재발**(H9 `/app/logs`, EC-6 `import streamlit`)하여 부검 가치가 있음.

## 3. 타임라인

- H9 lint 작성 직전, daemon.py 모듈 docstring에 `/app/logs` 리터럴이 있어 선제 발견·리워드.
- 이후 EC-6 streamlit lint 실행 시 timetable_crawl.py docstring의 `import streamlit`(제거 설명)이
  적발되어 전체 스위트 1 fail. 리워드 후 104 pass.

## 4. 근본 원인

`"<금지토큰>" in file_text` 형태의 lint는 의미가 아니라 바이트열을 본다. 결함을 회복하면서 그 결함을
docstring으로 설명하면(좋은 관행) 토큰이 그대로 남아 자기 자신을 적발한다. 테스트 파일이 자신을
스캔 대상에 넣으면 더 흔하다(본 건은 `bushexa/`만 스캔해 테스트 자기적발은 회피).

## 5. 재현

```bash
# (수정 전) bushexa/crawler/timetable_crawl.py docstring에 'import streamlit'(제거 설명) 존재
uv run pytest tests/crawler/test_no_hardcoded_paths.py::test_no_streamlit_in_crawler
# → FAIL (docstring 매칭)
```

## 6. 해결

- lint 본문의 비교 리터럴은 **분할 구성**: `_HARDCODED = "/app/" + "logs"` → lint 파일 자신이 토큰을
  통째로 담지 않게 한다.
- 소스 docstring은 금지 토큰의 **정확한 형태를 피해** 서술: "컨테이너 경로 하드코딩 제거",
  "streamlit 의존 제거(legacy `st.*` 호출과 그 import)".

## 7. 재발 방지 (Prevention)

- [x] **규약 D-4:** 금지-토큰 grep lint를 작성할 때 (a) 비교 리터럴을 분할 구성하고, (b) 스캔 범위에서
  테스트 디렉터리를 제외하며, (c) 제거한 의존을 문서화할 때 토큰의 정확한 형태를 쓰지 않는다.
- [x] 회귀: `tests/crawler/test_no_hardcoded_paths.py` (H9/EC-6) 자체가 가드로 상주 — 누군가 토큰을
  다시 넣으면(코드든 docstring이든) 적색.

## 8. 교훈

- substring lint는 값싸고 강력하지만 "사용 vs 언급"을 구분 못 한다. 분할 리터럴 + 범위 한정이 정석.
- 결함을 봉인하는 문서가 그 결함의 토큰을 그대로 담으면 가드가 문서를 때린다 — 서술을 우회 표기한다.

## 9. 상태

- 수정 커밋: P2 구현 (2026-06-01)
- 회귀 테스트 통과 확인: ✅ 전체 104 pass
- Auditor 확인: resolved
