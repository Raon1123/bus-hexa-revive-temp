---
status: implemented
touchpoint_id: TP-009
actor: 관리자
surface: admin
location: "GET/POST /admin/timetable/<busno>"
related_feature: F04
auditor_status: pending
last_updated: 2026-06-02
implemented_by: P4/W13a
---

# TP-009 — 관리자가 시간표를 직접 편집·저장한다

> Designer 대표 작성(가장 복잡한 폼 인터랙션 + 데이터 보호). Executor는 W13a 구현 시 이 명세를 그대로 따른다.
> feature: F04 §4.2/§4.4, phase: P4/W13a (저장은 W11 `TimetableEditor.save` 위임).

## 1. 맥락

- **누가 (actor):** 인증된 관리자
- **언제·왜:** 노선 시간표가 바뀌어 즉시 수정이 필요할 때(재크롤 없이 수기 보정).
- **위치 (surface/location):** `GET /admin/timetable`(목록), `GET /admin/timetable/<busno>`(편집), `POST /admin/timetable/<busno>`(저장)
- **사전 상태 (precondition):** `login_required` 통과(비로그인 시 302 → [[TP-007]]). `<busno>`는 알려진 노선만(traversal 차단). 저장 POST는 CSRF 토큰 필요(§10 S5).

## 2. 인터랙션 흐름 (Happy Path)

| # | 사람의 행동 | 시스템의 정확한 반응 | 화면/상태 변화 |
|---|---|---|---|
| 1 | `/admin/timetable` 진입 | 200 + 노선 목록(513/713/743/753/1115) | 편집 가능한 노선 카드/링크 |
| 2 | `713` 선택 → `/admin/timetable/713` | 200 + **3개 weekday 탭**(평일/토/일·공휴일) + departure별 시간 목록 + CSRF hidden 토큰 | 편집 폼 |
| 3 | 한 weekday 패널의 시각들을 편집 | **본 구현: weekday별 textarea 일괄 편집**(한 패널의 시각 목록을 텍스트로 수정). HTMX 항목단위 partial 추가/삭제는 선택사항으로 보류 — Designer 확정(2026-06-02): W13a AC/EC-4가 HTMX partial을 요구하지 않으므로 textarea 배치 편집 수용 | 패널 textarea 내용 변경 |
| 4 | "저장" 클릭(POST) | `TimetableEditor.save`: 검증→백업(`backup_dir/713.{ts}.json`)→tmp write→fsync→rename(atomic). 성공 시 200 + flash "저장됨" | 성공 배너 + 백업 생성 |

## 3. 화면/상태 목업 (ASCII)

```text
┌─ /admin/timetable/713 ─────────────────────────┐
│ [평일] [토요일] [일/공휴일]   ← weekday 탭     │
│ ── UNIST 출발 ───────────────────────────────  │
│  07:10  07:40  08:10  [+추가] 각 항목 [x삭제]  │
│  ── (hx-post로 패널만 갱신) ──                 │
│ <input hidden name=csrf_token value=...>       │
│                         [ 저장 ]               │
└────────────────────────────────────────────────┘
```

## 4. 입력 사양

| 입력 | 형식/제약 | 필수 | 기본값 | 검증 시점 |
|---|---|---|---|---|
| `<busno>` (경로) | 알려진 노선 화이트리스트, traversal 거부 | Y | — | server |
| weekday 키 | **`"0"`(평일)/`"1"`(토요일)/`"2"`(일·공휴일)** — `validate_timetable._VALID_WEEKDAYS` 계약. 화면 라벨만 평일/토/일·공휴일로 표시하고 폼·디스크 키는 숫자 문자열. 그 외 키는 422 (Designer 사후 정정 2026-06-02) | Y | — | server (잘못되면 422) |
| 시각 값 | `HH:MM`, 00:00–23:59, 중복 금지 | Y | — | server (`validate`) |
| `csrf_token` | 세션 토큰과 일치 | Y | — | server (불일치 400/403) |

## 5. 피드백 규약

- **로딩:** 시간 추가/삭제 partial은 `hx-indicator`로 미세 표시; 저장은 버튼 비활성+"저장 중...".
- **성공:** flash 배너 "713 시간표가 저장되었습니다 (백업 생성됨)".
- **에러:** 검증 실패 시 422 + 어떤 항목이 왜 잘못됐는지(예 "25:00은 잘못된 시각") 폼 상단/항목 옆 표시, **디스크 원본 미변경**.
- **빈 상태:** departure에 시각이 0개면 "등록된 시각 없음 + [추가]".

## 6. 분기 (성공/실패/엣지)

| 조건 | 시스템 반응 | 사용자에게 보이는 것 |
|---|---|---|
| 정상 저장 | 검증→백업→atomic rename, 200 | 성공 배너 + 백업 |
| 형식 오류(25:00, 중복) | `ValidationError` → 422, 원본 보존 | 오류 메시지, 원본 유지 |
| 잘못된 weekday 키 | 422 | 오류 메시지 |
| 비로그인 | 302 `/admin/login?next=...` | 로그인 페이지 |
| CSRF 토큰 누락/불일치 | 400/403, 저장 안 함 | 거부 메시지 |
| rename 실패(I/O) | 원본 파일 무손상(atomic), 5xx 대신 안내 | "저장 실패, 원본 유지" |

## 7. 접근성·키보드

- weekday 탭은 키보드 이동 가능(Tab/화살표), 선택 탭 `aria-selected`.
- 시각 입력은 `<label>` 연결. partial 갱신 후 포커스를 추가/삭제한 항목 근처로 이동.

## 8. 자동 갱신/실시간

- 자동 폴링 없음(편집 화면). 본 구현은 weekday별 textarea 일괄 편집(HTMX 항목단위 partial은 보류 — §2#3 Designer 정정). 다른 사용자 동시 편집은 "마지막 저장 승리 + 백업 복구"(R3).

## 9. Acceptance (W13a/W11 AC 재인용)

- [ ] AC-1: `GET /admin/timetable/713` → 200 + 3개 weekday 탭 (검증: `tests/web/test_admin_timetable_edit.py::test_edit_view`)
- [ ] AC-2: POST 저장 → 디스크 JSON 갱신 + `backup_dir`에 타임스탬프 백업 (검증: `::test_save`, `tests/services/test_timetable_editor.py::test_save_backup`)
- [ ] AC-3: 잘못된 형식/weekday → 422 + 원본 보존 (검증: `::test_invalid_save_422`, `test_timetable_editor.py::test_invalid_preserves_original`)

## 10. 관련 touch point / feature

- feature: F04
- 인접 TP: [[TP-010]] (편집 화면에서 재크롤 시작), [[TP-007]] (인증 게이트)
