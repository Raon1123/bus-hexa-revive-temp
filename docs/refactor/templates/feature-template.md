---
status: draft
designer: opus
auditor_status: pending
last_updated: YYYY-MM-DD
feature_id: F00
---

# F00 — {{Feature Name}}

> 이 템플릿의 **모든 섹션**은 필수다. Executor는 슬롯을 채우되 섹션을 삭제하지 않는다. "해당 없음"은 명시적으로 적는다.

## 0. 한 줄 요약

기존 동작과 새 동작을 한 문장씩.

- **As-is:** ...
- **To-be:** ...

## 1. 사용자 시나리오

- 누가, 어떤 의도로, 어떤 화면을 보는가?
- 정상 흐름 (Happy path) — 단계별 4-7줄
- 엣지 케이스 ≥ 3건 (빈 데이터, API 실패, 권한 없음, 부정 입력 등)

## 2. 현재 구현 분석 (As-Is)

### 2.1 진입점 / 파일 / 라인 참조
- 라우팅: `app.py:NN` 또는 `infopages/X.py`
- 핵심 함수와 그 위치

### 2.2 사용된 Streamlit API 전수 목록
| API | 위치 | 용도 |
|---|---|---|
| `st.dataframe(...)` | infopages/X.py:NN | ... |

### 2.3 데이터 흐름
- 호출하는 백엔드 함수와 그 시그니처
- 가져오는 데이터의 shape (예: `list[(str, str, str)]`)
- 캐싱·세션 상태 사용 여부

### 2.4 의존 모듈 그래프
```text
infopages/X.py
  ├── src.constants.ROUTEID
  ├── src.crawl.crawl_busstop()
  └── src.tools.get_timetable()
```

### 2.5 관찰된 결함·악취 (있다면)
- 명확한 버그
- 안티패턴
- 누락된 예외처리

## 3. 외부 의존성

### 3.1 외부 API
- 엔드포인트 URL, 메서드, 파라미터, 응답 형식 (JSON/XML)
- 응답 예시 (api-manual DOCX 참조시 명시)
- 오류 응답·상태코드

### 3.2 데이터베이스
- 읽는/쓰는 테이블·컬럼
- 쿼리 패턴

### 3.3 정적 파일
- 읽는 timetable/*.json, media/*, secret/* 등

## 4. 새 구현 매핑 (To-Be)

### 4.1 URL & HTTP 메서드
- `GET /board` → ...
- `POST /admin/timetable` → ...

### 4.2 Flask 라우트 / 핸들러 시그니처
```python
@bp.route("/board")
def departure_board() -> str:
    ...
```

### 4.3 템플릿 & 정적 자원
- `bushexa/web/templates/board.html`
- 사용하는 partial / 매크로
- 필요한 정적 JS/CSS

### 4.4 도메인 서비스 호출
- `bushexa.services.board.upcoming_departures(stop_id)` → 반환 shape

### 4.5 HTMX/SSE 동작 (실시간 화면만)
- 폴링 간격 또는 SSE 토픽
- 부분 갱신 대상 selector
- 실패시 fallback 동작

## 5. 데이터 모델 변경 (있는 경우만)

- 신규 테이블/컬럼/인덱스
- 마이그레이션 스크립트 위치
- 기존 데이터 보존 전략

## 6. 인터페이스 계약

### 6.1 함수 시그니처 (신규)
```python
def upcoming_departures(stop_id: str, *, now: datetime | None = None) -> list[Departure]: ...
```

### 6.2 데이터 타입 (dataclass / TypedDict)
```python
@dataclass(frozen=True)
class Departure:
    bus_no: str
    arrival_seconds: int | None  # None = scheduled-only
    source: Literal["live", "timetable"]
    ...
```

## 7. Acceptance Checklist (Executor가 사용)

- [ ] AC-1: ... (검증 방법: ...)
- [ ] AC-2: ...
- [ ] AC-3: ...
- [ ] AC-N: ...

> Executor는 모든 AC를 ✅로 만들 때까지 task in-progress 유지. 보고 시 항목별 한 줄 근거 첨부.

## 8. 테스트 계획

### 8.1 단위 테스트 (pytest)
- `tests/unit/test_<feature>.py`에 추가
- 각 테스트 케이스 ≥ 3건. **각 케이스는 반드시 (a) 케이스 이름 + (b) 검증 의도 자연어 1줄**로 적는다. 감리가 이 설명만 읽고 "무엇을, 어떤 입력/조건에서, 무엇이 참이어야 통과하는지"를 설명할 수 있어야 한다.
  - 예: `test_merge_marks_first_and_second`: live·timetable 병합 결과에서 가장 이른 2건이 각각 FIRST/SECOND로 표시되는지 검증한다.
  - 함수명만 나열 (예: `test_merge`, `test_edge`)하면 감리 FAIL.

### 8.2 통합 테스트
- Flask test_client 시나리오
- DB fixture (in-memory SQLite)

### 8.3 수동 검증 시나리오
- 어떤 페이지에서 어떤 입력으로 어떤 결과를 확인하는지 step-by-step
- 스크린샷 캡처 위치 (있으면)

## 9. 변경 영향 범위

- 영향 받는 다른 feature doc 번호
- breaking change 여부 (Yes/No + 사유)

## 10. 미해결 질문 (있다면)

- 모호한 요구사항 — 별도 PR 또는 사용자 확인 필요
