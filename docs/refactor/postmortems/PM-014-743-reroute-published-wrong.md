---
status: fixed
postmortem_id: PM-014
severity: medium
discovered: 2026-09-29
phase: 운영 (콘텐츠 갱신)
component: bushexa.data.constants(VIA_STOPS), bushexa.web.route_diagram, templates/info.html, data/changelog.json, web/i18n.py
related: ["tests/web/test_route_diagram.py::test_743_beomseo_only_from_oct3", docs/guide/change-playbooks.md]
auditor_status: pending
---

# PM-014 — 743 구영리 경유 변경을 틀린 경로·시행일로 게시하고 7분 사이 세 번 정정

> 부검(postmortem)은 **비난이 아니라 재발 방지**를 위한 기록이다. 사람이 아니라 시스템·프로세스의 결함을 본다.

## 1. 요약 (3줄)

- **증상:** 743 노선 변경을 "713·753·1115 와 같은 구영 정류장 재경유"로 게시했다. 실제로는 **513 과 같은 범서중학교 경유**였고, **2026-10-03 시행**이었다. 노선도 박스도 겹쳤다.
- **근본 원인:** 공식 공지(정확한 정차 지점·시행일)를 확인하기 전에 편집했다. 노선 사실이 4~6곳에 손으로 복제되어 있어 한 번에 맞추기 어렵다. 렌더링 결과를 눈으로 보기 전에 머지했다.
- **재발 방지:** 날짜 게이트 + 테스트, 노선 변경 체크리스트(`docs/guide/change-playbooks.md`), 렌더링 육안 확인 의무화.

## 2. 영향

- 승객 대상 오정보(노선도·경유지·안내 배너)가 몇 분간 master 에 존재. 배포 반영 여부는 기록 없음.

## 3. 타임라인 (2026-09-29)

| 시각 | 커밋 | 내용 |
|---|---|---|
| 17:41 | `dea5ddc` | 743 이 "구영"(713/753/1115 와 같은 노드) 재경유로 반영. VIA_STOPS·info·배너·changelog 수정 |
| 17:43 | `e31a55f` | 정정: 범서중학교 경유(513 과 동일). `범서중` 노드 신설, `LINE_ORDER` 재배치, 시청/울산대학교 열 분리, i18n 배너 |
| 17:48 | `c89ac02` | 누락 정정: 시행일 2026-10-03. `VIA_743_BEOMSEO_FROM` 날짜 게이트 + 테스트, "10/3부터" 문구 |
| 17:48 | `177f444` | 범서중·구영이 같은 열(4)이라 박스 겹침 → 구영 열 5 로 분리 |

## 4. 근본 원인

- **사실 확인 단계 부재:** "구영리 재경유"라는 요약만으로 어느 도로·어느 정류장인지, 언제부터인지 확인하지 않았다.
- **사실의 다중 복제:** 같은 노선 사실이 `VIA_STOPS`, `route_diagram.LINE_STOPS/COLS/LINE_ORDER`, `info.html`(표 2곳 + 배너), `changelog.json`, `i18n.py` 배너에 흩어져 있다.
- **시각 검증 부재:** `test_route_diagram.py` 는 열 단조증가·박스 개수만 본다. 박스가 엉뚱한 레인을 덮는지는 테스트가 못 본다.

## 6. 해결

- `bushexa/web/route_diagram.py` — `범서중` 노드, 레인 재배치, 열 분리, `VIA_743_BEOMSEO_FROM` 날짜 게이트.
- `bushexa/data/constants.py` `VIA_STOPS` 513/743 → `구영리(범서중학교)`.
- `info.html`, `i18n.py`(`board.notice.743`), `board.html`·`unist_board.html` 배너, `data/changelog.json`.

## 7. 재발 방지 (Prevention) — **필수**

- [x] **회귀 테스트**: `tests/web/test_route_diagram.py::test_743_beomseo_upcoming` — 시행일 전에는 743 범서중에 "10/3부터" 예고를 붙인다. (최초 테스트 `test_743_beomseo_only_from_oct3` 는 PR #3 에서 대체)
- [x] `tests/web/test_route_diagram.py::test_beomseo_split` — 구영리 안에서 513·743 은 범서중, 나머지는 구영으로 갈린다.
- [x] **프로세스**: `docs/guide/change-playbooks.md` §1 노선 변경 체크리스트(공지 원문 확인 → 시행일 → 전 파일 → `/info` 육안 확인).
- [ ] 남은 위험: 날짜 게이트가 `date.today()`(호스트 TZ)를 쓴다. `VIA_STOPS`·info·배너는 날짜 게이트가 없고 문구로만 시행일을 알린다.
- [ ] 장기: 노선 사실을 한 데이터 소스로 모으는 것(ADR 후보).
- [x] 후속(2026-09-29, PR #3): 가로 SVG 노선도를 노선별 세로 정류장 목록으로 교체해 레인·박스·열 배치 문제 자체를 없앴다. 시행일 테스트는 `test_743_beomseo_upcoming` 으로 바뀌었다.

## 8. 교훈

- 콘텐츠 변경도 코드 변경처럼 **출처(공식 공지)와 시행일**을 먼저 확정한다. 커밋 메시지에 출처를 적는다.
- 시각 산출물(SVG 노선도)은 테스트 통과만으로 끝내지 않는다. 브라우저로 렌더링을 확인한다.
- 시행일이 미래인 변경은 날짜 게이트로 넣고, 게이트 날짜는 KST 기준으로 계산한다.
