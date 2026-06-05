# Security Audit Criteria

> 구현(특히 P4 web) 후 보안 위협을 감리한다. ADR-009 결정에 따른 전용 기준.
> Auditor는 read-only로 코드·설정·템플릿을 검사하고 `reports/security-audit-<ts>.md`를 작성한다.

## 0. 진입

```
audit-security --scope {web|crawler|all}
```

응답 양식:

```
SCOPE: ...
VERDICT: PASS | FAIL  (high/critical 1건이라도 있으면 FAIL)
FINDINGS:
  - [SEV: critical|high|medium|low] <카테고리>/<id>: <무엇이 / 어디서(path:line) / 왜 위험 / 재현 / 수정 권고>
GATE: P5 진입 허용 | 차단 (high/critical 0건이어야 허용)
PM_REQUIRED:
  - <high/critical 발견은 postmortems/PM 등재 필요 목록>
```

## 1. 위협 카테고리 체크리스트

### S1 — 인증·세션
- [ ] 비밀번호는 PBKDF2 등 해시 저장, 평문 비교 없음(legacy 경로 포함 마이그레이션)
- [ ] 비밀번호 변경 시 현재 비밀번호 검증(F04 D8)
- [ ] 세션 쿠키 HttpOnly·SameSite·(가능 시) Secure
- [ ] 로그인 실패 레이트리밋/lockout 존재
- [ ] 숨김 진입(`?hexa=6` 등) 제거 확인

### S2 — 권한
- [ ] 모든 `/admin/*`가 `login_required`로 보호
- [ ] 직접 URL 접근으로 권한 우회 불가

### S3 — 인젝션
- [ ] SQL은 파라미터 바인딩만(문자열 포매팅 0건): `! grep -rEn 'execute\([^,]*%|f".*SELECT' bushexa/`
- [ ] 경로 traversal 차단(시간표 `<busno>`가 파일명에 안전, `..` 거부)
- [ ] 명령 실행(os.system/subprocess) 사용자 입력 0건

### S4 — XSS
- [ ] Jinja 자동이스케이프 활성, `|safe`/`Markup` 사용처 전수 검토
- [ ] HTMX partial 응답에 미이스케이프 사용자 입력 없음
- [ ] 구 코드의 `unsafe_allow_html` 패턴이 신규에서 안전 처리

### S5 — CSRF
- [ ] 상태 변경 POST(관리자 폼·시간표 저장·재크롤)에 CSRF 방어(토큰 또는 SameSite 의존 명시)

### S6 — SSRF / 외부 호출
- [ ] 외부 API URL이 사용자 입력으로 조립되지 않음(고정 base + 화이트리스트 파라미터)
- [ ] 타임아웃 설정(무한 대기 방지)

### S7 — 시크릿
- [ ] API 키·DB 비밀번호·세션 시크릿이 코드/추적 파일에 평문 0건
- [ ] compose에 `${VAR}` 참조만, `.env.example`만 더미값
- [ ] 로그·에러 응답에 시크릿/내부 경로 누출 없음

### S8 — 안전한 기본값·정보 노출
- [ ] 사용자 대면 에러가 stack trace/내부 경로 노출 안 함
- [ ] 디버그 모드 off 기본
- [ ] 파일 권한(secret 0600) 유지

### S9 — DoS / 자원
- [ ] CSV export·쿼리 결과 행 상한(max_rows)
- [ ] SSE 연결 수·재크롤 동시성 제한
- [ ] 외부 API 과호출 차단(ADR-010 백업본 구조)

### S10 — 의존성
- [ ] 알려진 취약점 스캔(`pip-audit`/`uv` 등) 수행, high 0건

## 2. 판정

- high/critical 1건이라도 → VERDICT FAIL + GATE 차단(P5 진입 불가)
- medium 이하 → 등록 + 기한 합의 후 PASS 가능
- 각 high/critical 발견은 `postmortems/`에 PM 등재 + 회귀(보안) 테스트 작성

## 3. Auditor 제약

- read-only. 코드 수정 금지.
- 발견은 반드시 `path:line` + 재현 + 수정 권고를 동반(자연어 설명, E-8 정신).
- 추측성 FAIL 금지 — 재현·근거 없는 항목은 medium 이하 권고로.
