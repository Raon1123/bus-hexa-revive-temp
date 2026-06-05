---
status: designed
designer: opus
auditor_status: design-pass (T02 2026-06-01, F-8 fixed §8.1 Flask-독립 단위 5건; 잔여 C-3는 FROZEN 면제)
last_updated: 2026-06-02
feature_id: F03
---

# F03 — 정보 페이지 (Info Page)

> 이 템플릿의 **모든 섹션**은 필수다. Executor는 슬롯을 채우되 섹션을 삭제하지 않는다. "해당 없음"은 명시적으로 적는다.

## 0. 한 줄 요약

- **As-is:** `infopages/info.py`가 Streamlit API로 안내 텍스트·노선표·변경이력을 렌더링하고, `?hexa=6` 쿼리 파라미터로 관리자 페이지를 숨김 진입시킨다.
- **To-be:** `bushexa/web/routes/info.py` Flask 라우트가 Jinja2 템플릿으로 동일 정적 콘텐츠를 렌더링한다. 숨김 진입 패턴은 완전히 제거되고 관리자 진입은 F04 `/admin` 라우트로 대체된다.

## 1. 사용자 시나리오

**대상:** 버스 노선·운행 정보가 필요한 일반 이용자.

**정상 흐름 (Happy path):**
1. 이용자가 `/info` URL에 접근한다.
2. 서버는 `info.html` 템플릿을 렌더링하여 200 응답을 반환한다.
3. 이용자는 "Bus Route Map" 이미지(`graphisnotmap.png`)를 확인한다.
4. 이용자는 목적지별·노선번호별 표를 확인한다.
5. 이용자는 Tips 섹션과 변경이력을 확인한다.
6. 페이지는 추가 API 호출 없이 완전히 표시된다.

**엣지 케이스:**
1. **이미지 파일 누락:** `static/media/graphisnotmap.png`가 없으면 브라우저가 alt 텍스트("Graph route")를 표시한다. Flask는 404를 반환하지 않고 템플릿 렌더링은 정상 완료된다.
2. **`?hexa=6` 쿼리 파라미터 전달:** 새 구현은 해당 파라미터를 무시한다. 관리자 기능은 표시되지 않는다.
3. **`changelog.json` 파일 누락 (선택 구현 시):** 변경이력 데이터 파일이 없으면 빈 목록으로 폴백하고 500 에러를 발생시키지 않는다.
4. **로그인하지 않은 관리자 접근 시도:** `/info?hexa=6`으로 접근해도 관리자 UI가 노출되지 않는다. 관리자는 `/admin/login`을 사용한다.

## 2. 현재 구현 분석 (As-Is)

### 2.1 진입점 / 파일 / 라인 참조

- 라우팅: `app.py` 의 Streamlit multipage 진입 (페이지 파일 직접 실행)
- 핵심 함수: `infopages/info.py:4` — `info_page()`
- 진입: `infopages/info.py:104` — `if __name__ == "__page__": info_page()`

### 2.2 사용된 Streamlit API 전수 목록

| API | 위치 | 용도 |
|---|---|---|
| `st.title(...)` | `infopages/info.py:5` | 페이지 제목 "Bus HeXA Information" 출력 |
| `st.write(...)` | `infopages/info.py:7` | 서비스 소개 텍스트 출력 |
| `st.write("# Bus Route Map")` | `infopages/info.py:14` | 노선 지도 섹션 헤딩 |
| `st.image(...)` | `infopages/info.py:15` | `media/graphisnotmap.png` 이미지 표시 |
| `st.write("## For Destination")` | `infopages/info.py:17` | 목적지 섹션 헤딩 |
| `st.write(...)` (markdown table) | `infopages/info.py:20` | 목적지-노선번호 표 |
| `st.write("## For Bus Number")` | `infopages/info.py:39` | 노선번호 섹션 헤딩 |
| `st.warning(...)` | `infopages/info.py:41` | 713/1115 경유 안내 경고 박스 |
| `st.write(...)` (markdown table) | `infopages/info.py:46` | 노선번호-목적지 표 |
| `st.write("# Tips")` | `infopages/info.py:56` | Tips 섹션 헤딩 |
| `st.error(...)` | `infopages/info.py:58` | 513 방향 주의 경고 |
| `st.markdown(...)` | `infopages/info.py:60` | Tips 목록 |
| `st.markdown(...)` | `infopages/info.py:68` | 변경이력(Update) 섹션 |
| `st.query_params` | `infopages/info.py:79` | `?hexa` 쿼리 파라미터 읽기 |
| `st.experimental_get_query_params()` | `infopages/info.py:87` | 구버전 Streamlit 폴백 쿼리 파라미터 읽기 |
| `st.error(...)` | `infopages/info.py:101` | 관리자 페이지 로드 실패 에러 메시지 |

### 2.3 데이터 흐름

- 외부 백엔드 함수 호출: **없음**. 모든 콘텐츠가 소스 코드에 하드코딩된 리터럴 문자열이다.
- 데이터 shape: 해당 없음 (런타임 데이터 없음).
- 캐싱: 해당 없음.
- 세션 상태: 해당 없음. `st.query_params` 읽기만 수행한다.
- 이미지: `media/graphisnotmap.png` 정적 파일을 직접 경로로 참조한다.

### 2.4 의존 모듈 그래프

```text
infopages/info.py
  ├── streamlit (st)
  └── infopages.manager.manager_page  (조건부, hexa_count == 6 시)
```

### 2.5 관찰된 결함·악취

- **결함 1 — `?hexa=6` 숨김 관리자 진입 패턴:** `infopages/info.py:78-102`. 쿼리 파라미터로 관리자 기능을 활성화하는 패턴은 인증이 없으며 URL만 알면 누구나 진입 가능하다. 새 구현에서 이 패턴은 완전히 제거한다. 관리자 진입은 F04에서 정의하는 `/admin/login` 인증 경로로 대체된다.
- **결함 2 — `st.experimental_get_query_params()` 폴백:** `infopages/info.py:87`. Streamlit 공식 deprecated API를 사용한다. 새 구현과 무관하나, 기존 코드의 유지보수 부채다.
- **악취 1 — 모든 콘텐츠 하드코딩:** 변경이력(Update 섹션)이 소스 코드 내 리터럴 문자열로 관리된다. 비개발자가 수정 불가하고, 배포 없이 내용 변경이 불가능하다. 새 구현에서 `static/data/changelog.json` 분리를 선택적으로 적용한다.
- **악취 2 — 이미지 경로 하드코딩:** `media/graphisnotmap.png`가 작업 디렉토리 기준 상대 경로로 하드코딩되어 있다. Flask `url_for`로 대체 필요하다.

## 3. 외부 의존성

### 3.1 외부 API

해당 없음. 이 페이지는 외부 API를 호출하지 않는다.

### 3.2 데이터베이스

해당 없음. 이 페이지는 DB를 읽거나 쓰지 않는다.

### 3.3 정적 파일

- `media/graphisnotmap.png` — 노선 그래프 이미지. 새 구현에서는 `bushexa/web/static/media/graphisnotmap.png`로 이동한다.
- `static/data/changelog.json` — (선택 구현) 변경이력 데이터. 소스에서 분리 시 신규 생성하며, 스키마는 `[{"date": "YYYY-MM-DD", "description": "..."}]`다.

## 4. 새 구현 매핑 (To-Be)

### 4.1 URL & HTTP 메서드

- `GET /info` → 정보 페이지 렌더링

### 4.2 Flask 라우트 / 핸들러 시그니처

```python
# bushexa/web/routes/info.py
from flask import Blueprint, render_template

bp = Blueprint("info", __name__)

@bp.route("/info")
def info_page() -> str:
    return render_template("info.html")
```

변경이력을 `changelog.json`으로 분리하는 경우:

```python
# bushexa/web/routes/info.py
import json
from pathlib import Path
from flask import Blueprint, render_template, current_app

bp = Blueprint("info", __name__)

@bp.route("/info")
def info_page() -> str:
    changelog_path = Path(current_app.static_folder) / "data" / "changelog.json"
    if changelog_path.exists():
        changelog = json.loads(changelog_path.read_text(encoding="utf-8"))
    else:
        changelog = []
    return render_template("info.html", changelog=changelog)
```

### 4.3 템플릿 & 정적 자원

- `bushexa/web/templates/info.html` — 메인 템플릿. `base.html`을 상속(`extends`)한다.
- `bushexa/web/templates/base.html` — 공통 레이아웃 partial.
- `bushexa/web/static/media/graphisnotmap.png` — 이미지. `url_for("static", filename="media/graphisnotmap.png")`로 참조한다.
- `bushexa/web/static/data/changelog.json` — (선택) 변경이력 데이터 파일.
- 추가 JS/CSS: 해당 없음. 정적 콘텐츠 페이지로 JS 없이 렌더링한다.

### 4.4 도메인 서비스 호출

해당 없음. 이 페이지는 도메인 서비스를 호출하지 않는다. 모든 콘텐츠는 템플릿에 정적으로 포함되거나 `changelog.json`에서 로드된다.

### 4.5 HTMX/SSE 동작 (실시간 화면만)

해당 없음. 이 페이지는 정적 콘텐츠이며 실시간 갱신이 필요 없다.

## 5. 데이터 모델 변경 (있는 경우만)

해당 없음. DB 변경 없음.

`changelog.json` 선택 구현 시 신규 파일 스키마:

```json
[
  {"date": "2025-08-11", "description": "버스 1115 시간표 업데이트"},
  {"date": "2025-02-28", "description": "버스 713, 743 시간표 업데이트"}
]
```

마이그레이션 스크립트: 해당 없음 (DB 변경 없음).

## 6. 인터페이스 계약

### 6.1 함수 시그니처 (신규)

```python
def info_page() -> str:
    """
    GET /info 핸들러. info.html 렌더링 결과 문자열을 반환한다.
    changelog.json 존재 시 변경이력을 템플릿 컨텍스트로 전달한다.
    changelog.json 부재 시 빈 리스트로 폴백하며 예외를 발생시키지 않는다.
    """
    ...
```

### 6.2 데이터 타입 (dataclass / TypedDict)

```python
# changelog.json 선택 구현 시
from typing import TypedDict

class ChangelogEntry(TypedDict):
    date: str          # "YYYY-MM-DD" 형식 문자열
    description: str   # 한국어 변경 내용 설명
```

## 7. Acceptance Checklist (Executor가 사용)

- [ ] AC-1: `GET /info` 가 HTTP 200을 반환한다. (검증 방법: `pytest tests/integration/test_routes.py::test_info_returns_200` 또는 `curl -s -o /dev/null -w "%{http_code}" http://localhost:5000/info` 결과 200 확인)
- [ ] AC-2: 응답 HTML에 노선번호 513, 713, 743, 753, 1115가 모두 포함된다. (검증 방법: `curl -s http://localhost:5000/info | grep -c "513\|713\|743\|753\|1115"` 결과 ≥5 확인)
- [ ] AC-3: `graphisnotmap.png` 이미지가 `url_for("static", ...)` 경로로 참조된다. (검증 방법: 응답 HTML에서 `src="/static/media/graphisnotmap.png"` 패턴 존재 확인 — `curl -s http://localhost:5000/info | grep graphisnotmap`)
- [ ] AC-4: `GET /info?hexa=6` 요청 시 관리자 UI가 렌더링되지 않는다. (검증 방법: `curl -s "http://localhost:5000/info?hexa=6" | grep -i "manager\|admin"` 결과 빈 출력 확인)
- [ ] AC-5: `import streamlit` 구문이 `bushexa/web/routes/info.py`에 존재하지 않는다. (검증 방법: `grep -r "import streamlit" bushexa/` 결과 해당 파일 미포함 확인)

> Executor는 모든 AC를 체크할 때까지 task in-progress 유지. 보고 시 항목별 한 줄 근거 첨부.

## 8. 테스트 계획

### 8.1 단위 테스트 (pytest)

`tests/unit/test_info_content.py`에 도메인 함수 단위 테스트:

- `test_load_destinations_returns_expected_rows`: `bushexa.domain.info_content.load_destinations()`가 14개 목적지 row를 반환하고 각 row가 `(destination_kr, [bus_no, ...])` 형식인지 확인한다 (Flask 환경 미의존).
- `test_load_bus_routes_returns_expected_rows`: `load_bus_routes()`가 5개 노선(513,713,743,753,1115) row를 반환하고 각 row에 경유지 텍스트가 포함되는지 확인한다.
- `test_load_changelog_parses_dates`: `load_changelog("data/changelog.json")`가 ISO 날짜 + message 필드를 가진 entry list를 반환하는지 확인한다 (tmp_path에 sample json 생성 후 호출).
- `test_load_changelog_missing_file_returns_empty`: 파일이 없을 때 빈 list 반환 (예외 발생 금지) 확인한다.
- `test_destinations_no_duplicate_keys`: load_destinations 결과의 destination 키가 중복 없음 확인 (정렬·dedup 정책 검증).

### 8.2 통합 테스트

`tests/web/test_info_route.py`에 Flask test_client 시나리오:

- `test_info_returns_200`: `GET /info` → 200.
- `test_info_contains_route_numbers`: 응답 HTML에 513, 713, 743, 753, 1115 모두 포함.
- `test_info_hexa_param_ignored`: `GET /info?hexa=6` → 응답 HTML에 관리자 UI 마커(`__mgr_auth__`, `/admin`)가 없음.
- `test_info_image_url_uses_static`: 응답 HTML에 `/static/media/graphisnotmap.png` 포함.
- `test_info_changelog_missing_fallback`: `changelog.json`이 없을 때 200 + 변경이력 섹션 빈 상태로 렌더.

### 8.3 수동 검증 시나리오

1. `uv run bushexa serve` 실행 후 브라우저에서 `http://localhost:5000/info` 접근.
2. 페이지 상단에 제목이 표시되고, 노선 그래프 이미지가 로드됨을 확인한다.
3. "For Destination" 표와 "For Bus Number" 표가 렌더링됨을 확인한다.
4. Tips 섹션에서 513번 경고 박스(warning 스타일)가 표시됨을 확인한다.
5. 변경이력 섹션에서 날짜별 항목이 표시됨을 확인한다.
6. `http://localhost:5000/info?hexa=6` 접근 시 관리자 UI가 노출되지 않음을 확인한다.

## 9. 변경 영향 범위

- **F04 (관리자 페이지):** `?hexa=6` 숨김 진입을 제거하고 F04 `/admin` 라우트로 대체한다. F04가 완성되기 전까지 관리자 기능은 접근 불가 상태가 된다.
- breaking change: **Yes** — `?hexa=6` 방식의 관리자 진입이 제거된다. 기존 북마크나 URL 공유로 관리자 페이지에 접근하던 경로가 차단된다. 의도적 제거이며 F04로 대체된다.

## 10. 미해결 질문 (있다면)

- `changelog.json` 분리: 선택 사항으로 표기했다. 배포 편의성과 소스 간결성 사이의 트레이드오프가 있으므로 구현자가 결정한다.
- 노선표 데이터(`src/constants.py`의 `ROUTEID`, `VIA_STOPS`)를 템플릿에 동적으로 주입할지, HTML에 직접 하드코딩할지는 구현자 판단에 맡긴다. 동적 주입 시 `bushexa/data/constants.py`에서 로드한다.
