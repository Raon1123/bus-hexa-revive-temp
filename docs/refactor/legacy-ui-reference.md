# 레거시 UI 레퍼런스 (Streamlit → Flask 충실 재현용)

> 출처: 레거시 `app.py` + `infopages/*.py` 소스 분석 (2026-06-02).
> 목적: 신규 Flask UI를 레거시 Streamlit 화면에 **충실히 재현**하기 위한 페이지별 구성 명세.
> 시각 디테일(정확한 색/간격)은 사용자 제공 스크린샷으로 보정한다.

## 전역 (app.py)

- 페이지 타이틀: `Bus HeXA - UNIST 버스정보 사이트`, 아이콘 `media/hexaLogo.ico`, `layout="wide"`.
- 좌측 사이드바 네비게이션 (`st.navigation`), 3그룹: **Information / Timetable / Tracking** — ✅ 신규 UI에 복원 완료.
- 기본 페이지 = **Departure Board**.
- 하단: `Made by [HeXA](https://hexa.pro)` — ✅ 복원 완료.

---

## 1. Departure Board (`departure_board.py`) — 기본/핵심

- 상단: `Current time is {요일} HH:MM` 텍스트.
- `Timetable` 라벨 후 **커스텀 HTML `<table>`** (st.dataframe 아님).
- 컬럼: **노선번호 · 출발 시각 · 현재 위치**.
- **버스 1대 = 2행 구조** (노선번호 셀 `rowspan=2`):
  - 1행: `[노선번호] [출발시각] [현재위치 + " 도착" 또는 "출발예정"]`
  - 2행: `[FIRST/SECOND 플래그] [경유 정류장 문자열]`
- **FIRST/SECOND 강조색**: FIRST = `#DC143C`(crimson) **굵게**, SECOND = `#0000CD`(blue) **굵게**.
- 최대 **10개**, 도착시각 오름차순.
- 실시간 크롤(운행 중 버스) + 시간표를 병합. 실시간은 `{종점}행 {present} 도착` 형태.
- 상태: 막차 종료 시 `notify_lastbus` 경고 / fetch 실패 시 에러 / `운행 중인 버스가 없습니다.` 경고.
- ※ 신규 구현(`board.html`)과 컬럼/2행 구조·FIRST/SECOND 색을 대조해 맞출 것.

## 2. 버스번호별 (`busno.py`)

- 상단: `Current time is ...`.
- `st.segmented_control` **버스번호 칩** (Select bus number).
- `st.segmented_control` **요일** `[Weekday, Saturday, Sunday/Holiday]`.
- `st.selectbox` **출발지** (Select departure of bus: 출발지 선택).
- `Timetable` 라벨 + `st.dataframe` (**Hour 행 / Minute 열**, 분은 콤마로 join, `width=300`).
- 재현 포인트: 칩형 토글(segmented control), 시/분 피벗 표.

## 3. UNIST Timetable (`unist_timetable.py`)

- 상단: `Current time is ...` + `st.segmented_control` 요일.
- **범례(Legend)**: 노선 색 칩 — 513 `#D32F2F`(red), 713 `#388E3C`(green), 743 `#1976D2`(blue), 753 `#7B1FA2`(purple), 1115 `#F57C00`(orange).
- HTML 표: **Hour | Minutes**. 분 셀 = `MM (노선)` **배지**들, 노선별 색상.
- 표 스타일: header bg `#f0f2f6`, row hover `#f9f9f9`, Hour 컬럼 50px 중앙·굵게, `table-layout: fixed`.
- ※ 신규 `static/css/timetable.css`의 `.bus-{N}` 색이 이 값들과 일치하는지 이미 확인됨(E-13).

## 4. Running Log (`running_table.py`)

- `st.info` 안내: "시범적으로 과거의 운행 정보를 제공합니다...".
- `st.date_input` 날짜(기본=어제, `YYYY.MM.DD`).
- `st.selectbox` 노선 (`{번호}번 {방향}행`).
- 결과: **행=정류장명, 열=각 운행** 매트릭스 표(`df.T`). 값 = `HH:MM` / `レ`(미경유) / `미`(시각 불명).
- 에러: `검색된 버스가 없습니다.`

## 5. From UNIST (`unist_board.py`)

- **`st.columns(3)` × 2행 = 타일 그리드**.
- 각 타일: `#### {노선} {방향}행` 헤더 + 줄들:
  - 실시간: `{present} {arrival}` (덕하→"(시내)", 삼남→"(울산역)" 접미사)
  - 시간표: `{HH:MM} 출발 예정` (각 타일 최대 2대, VISUALIZE=2)
- 막차 시 `notify_lastbus`.
- 재현 포인트: 3열 카드 그리드 레이아웃.

## 6. To UNIST (`stops.py`)

- `st.selectbox` 정류소 (정류소를 선택해주세요 / Select bus stop), 표시명 = 정류소 이름.
- `pageblock_busstop(...)`로 도착정보 블록 렌더(노선/도착시간/현재위치 verbose).
- **10초 자동 갱신**(session_state timestamp).
- 상태: `운행 중인 버스가 없습니다.` 에러 / 1·2번째 버스 간격 30분↑ 경고.

## 7. 버스정보 / Info (`info.py`)

- `st.title("Bus HeXA Information")`.
- 안내 문단(노선 개편 24-12-21).
- `# Bus Route Map` + 이미지 `media/graphisnotmap.png` (가로 100%).
- `## For Destination` — 표(Destination | Bus Number).
- `## For Bus Number` — `st.warning`(713/1115 천상 경유) + 표(Bus Number | Route).
- `# Tips` — `st.error`(513 방향 주의) + 환승 팁 불릿.
- `# Update` — 변경 이력 목록(신규는 `changelog.json` 사용).
- 숨김: `?hexa=6` 매니저 페이지 unlock(신규는 `/admin`으로 대체됨).

---

## 재현 시 공통 원칙

- 레거시 IA(3그룹 사이드바) 유지 — 완료.
- 페이지 상단 `Current time is {요일} HH:MM` 표기 습관 유지.
- 토글/선택은 Streamlit `segmented_control`(칩형)·`selectbox` 느낌 재현.
- 표 색·배지 색은 위 HEX 값 고정(E-13: 레거시 출처).
- 정확한 폰트/여백/카드 모양은 **사용자 스크린샷**으로 확정.
