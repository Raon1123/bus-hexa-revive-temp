# Touch Point Index

> 사람과 시스템이 만나는 지점의 인터랙션 디자인 문서 목록. 규약은 `../00-workflow.md` §9, 템플릿 `../templates/touchpoint-template.md`.

## 계획된 touch point (feature → TP)

| TP | 제목 | actor | surface | feature | status |
|---|---|---|---|---|---|
| TP-001 | 출발 게시판 자동 갱신 화면 | 일반 사용자 | web | F01 | implemented |
| TP-002 | 버스번호별 시간표 조회 (선택 캐스케이드) | 일반 사용자 | web | F02 | implemented |
| TP-003 | 정류장 도착정보 선택·자동갱신 | 일반 사용자 | web | F06 | implemented |
| TP-004 | UNIST 출발 카드 보드 | 일반 사용자 | web | F07 | implemented |
| TP-005 | 전체 시간표 요일 전환 | 일반 사용자 | web | F08 | implemented |
| TP-006 | 운행 로그 날짜·노선 조회 | 일반 사용자 | web | F05 | implemented |
| TP-007 | 관리자 로그인·세션 | 관리자 | admin | F04 | implemented |
| TP-008 | 관리자 데이터 수동 조회·CSV | 관리자 | admin | F04 | implemented |
| TP-009 | 관리자 시간표 직접 편집·저장 | 관리자 | admin | F04 | implemented |
| TP-010 | 관리자 시간표 재크롤 (SSE 진행) | 관리자 | admin | F04 | implemented |
| TP-011 | 관리자 govtrack 데몬 상태 모니터 | 관리자 | admin | F04 | implemented |
| TP-012 | 관리자 비밀번호 재설정 | 관리자 | admin | F04 | implemented |
| TP-013 | 운영자 크롤 데몬 실행 (CLI) | 운영자 | cli | F09 | planned |
| TP-014 | 운영자 시간표 재크롤 (CLI) | 운영자 | cli | F10 | planned |
| TP-015 | 관리자 애플리케이션 로그 조회 | 관리자 | admin | F04 | implemented |

> TP 문서는 P4(web)·P2(cli) 실행 시 각 work item 산출물로 작성한다. 가장 복잡한 인터랙션(TP-009 시간표 편집, TP-001 자동갱신)을 우선 대표 작성한다.

## status 범례

- **planned**: 목록 등재, 문서 미작성
- **designed**: TP 문서 작성 + 설계 감리 PASS
- **implemented**: 구현 + 실행 감리에서 인터랙션 일치 확인 (E-12)
