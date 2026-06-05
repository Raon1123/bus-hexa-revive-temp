---
status: designed
adr_id: ADR-001
designer: opus
auditor_status: pending
last_updated: 2026-06-01
supersedes: null
superseded_by: null
---

# ADR-001 — Web Framework: Flask + Jinja2 + Vanilla JS + HTMX

## 컨텍스트

- Streamlit 1.40을 사용 중. UI 모든 페이지가 7개, 차트/업로드/스트리밍 같은 Streamlit 특화 기능 없음.
- 사용 중인 UI 프리미티브는 테이블, 드롭다운, 폼, 카드 그리드, 색상 코드 시간표 정도.
- 사용자 측 요구: 로컬 실행을 가볍게 (Streamlit 제거), 실시간 부분 갱신 (출발 게시판, 정류장 도착정보) 도입.
- 관련 feature docs: F01~F08 (UI 전부)

## 결정

웹 프레임워크는 **Flask 3.x**, 템플릿은 **Jinja2**, 동적 부분 갱신은 **HTMX 1.9+** + **Vanilla JS**로 한다. SPA 프레임워크/번들러를 도입하지 않는다.

## 대안

### 대안 A — FastAPI + Jinja2 + HTMX
- 장점: async I/O가 SSE에 자연스러움. 타입 힌트 친화적.
- 단점: 서버사이드 폼/세션 ergonomics가 Flask 대비 약함. 본 앱은 I/O bound가 아니라 외부 API 단일 호출 위주.
- 기각 사유: 본 앱의 동시성 부담이 낮고 Flask의 통상적인 sync 모델로도 SSE 처리 충분 (`Response(stream_with_context)`). 도입 복잡도 감소 우선.

### 대안 B — FastAPI + React/Vue SPA
- 장점: 향후 모바일 앱 / 풍부한 인터랙션 시 확장 용이.
- 단점: Node.js 빌드 파이프라인 추가. uv 단일 도구로 끝나지 않음. 본 리팩토링 비-목표.
- 기각 사유: 비-목표 (overview 참조).

### 대안 C — Streamlit 유지 + conda 제거만
- 장점: 가장 적은 변경.
- 단점: 사용자 요구사항 "streamlit dependency 없이 재구현"과 충돌.
- 기각 사유: 요구사항 위반.

## 결과

### 긍정적 영향
- 페이지 라우팅·세션·테스트 클라이언트 모두 Flask 표준 도구로 처리.
- HTMX로 SPA 없이 부분 갱신 — JS 코드 50~100 LOC 수준 유지 가능.
- 서버 사이드 렌더링이라 SEO 및 초기 로드 빠름.
- 단일 프로세스 모델로 govtrack 데몬과 같은 Python 환경 공유.

### 부정적 영향 / 비용
- Jinja2 템플릿 8개 + 부분 partial 신규 작성 필요 (각 feature doc에 명시됨).
- 클라이언트 측 인터랙션이 복잡해지면 vanilla JS 코드가 증가. 본 앱 범위에서는 위험 낮음.
- HTMX 학습 곡선이 팀원에게 있을 수 있음 (작음).

### 따라오는 작업
- ADR-004 realtime 패턴 (HTMX 폴링 vs SSE 사용처 분리)
- ADR-007 디렉토리 레이아웃 (Flask blueprint 구조)
- 모든 F01~F08 feature doc의 4.2/4.3 섹션이 Flask + Jinja2 가정 위에 작성됨

## 검증 방법

```bash
# 의존성 확인
uv run python -c "import flask, jinja2; print(flask.__version__, jinja2.__version__)"
# Smoke 라우트
curl -sf http://localhost:5000/ | grep -i hexa
# HTMX 정적 자원
test -f bushexa/web/static/vendor/htmx.min.js
```

## 미해결 / 후속 결정

- 정적 자원 번들링 전략 — 본 ADR은 HTMX를 `static/vendor/`에 직접 두는 것으로 결정. CDN 사용 여부는 ADR-006(deployment)에서 결정.
