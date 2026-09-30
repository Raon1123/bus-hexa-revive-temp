# 시간표 재설계 보완안: 기한형 공지 · 경유 시각 예측 · 방향 일반화

> **이 문서의 위치.** `docs/timetable-ux/02-redesign-plan.md`(이하 "계획")에 붙이는 보완안입니다. 오너가 2026-09-29에 내린 세 가지 결정을 계획에 반영합니다.
> **기준 시각.** 2026-09-29(화) 20:45 KST.
> **표기.**
> - **[검증]** 파일을 읽거나 명령을 실행해 확인한 사실
> - **[시뮬]** 봄학기 로그(`logs/logs.tsv`)를 저장소 밖 스크래치 스크립트로 다시 계산한 결과. 스크립트는 `docs/timetable-ux/analysis/`, (검토 스크립트는 세션 임시 폴더라 보존하지 않음)에 있습니다.
> - **[추론]** 위 근거에서 끌어낸 판단
>
> **줄번호 기준.** 브랜치가 여러 개라서 인용마다 기준을 붙입니다.
> - `[HEAD]`: 이 체크아웃의 현재 커밋. `feat/route-map-geo-ab` bf5d807이고, 로컬 master 05c3b94 위에 있습니다.
> - `[origin]`: origin/master 33c3179
> - `[notices]`: 워크트리 `/home/mlv/project/bushexa/bushexa-notices`. 브랜치 `feat/deadline-notices`, origin/master 기준이며 커밋 전에 스테이징된 상태입니다.
> - 도메인 파일(`board.py`, `unist_board.py`, `unist_timetable.py`, `busno.py`, `constants.py`의 ROUTEID)은 세 기준에서 내용이 같습니다.
>
> 저장소 파일은 수정하지 않았습니다.

> **개정 (2026-09-29 밤, 오너 결정 반영).** 이 보완안의 초안은 오너가 예측 기준을 정하기 전에 작성됐습니다. 다음 결정으로 해당 부분을 고쳤습니다.
> - **예측 게이트 = 최근 30일 · 같은 요일군 · 같은 편 표본 4건 이상**(오너). 초안의 게이트(학습 n≥12·날짜≥8·IQR≤8·LODO p80≤6, 42/84일 창, 14일 전진창)는 **폐기**하고, 필요하면 오너 게이트 위에 얹는 *선택 품질 조건*으로만 남깁니다(§2.4 7번, Q33).
> - **예측 소스 우선순위 = 운행 중 실시간 ETA → 과거 기록 예측 → 기점 출발 시각**(오너). §2.1의 계층이 이미 이 순서입니다(`unist_live` > `unist_predicted` > `origin_fallback`). `unist_exact`는 UNIST 기점 노선의 시간표 시각이라 예측과 경쟁하지 않습니다.
> - **공지 패치는 지금 수행, 배포는 오너가 수동**(오너). N0-a의 K1·K3·K4는 수정해 스테이징했습니다(§1.2). 배포 경로 주의는 S6·Q2를 보세요.
> - 오너 게이트를 봄학기 기록으로 다시 시뮬레이션한 결과는 §2.3 끝의 **"오너 게이트 시뮬레이션"**에 있습니다. 핵심: 평일은 충족, **토요일은 30일 안에 토요일이 4~5번뿐이라 거의 항상 폴백** → 토·일·공휴일 시간표가 5개 노선 모두 동일하므로 **주말을 한 요일군으로 묶으면** 96~97% 편이 게이트를 통과합니다(Q32).

---

## 먼저 알아야 할 상태 변화 (조사 도중 바뀐 전제)

| # | 사실 [검증] | 계획에 주는 영향 |
|---|---|---|
| S1 | "커밋되지 않은 오너 WIP"는 **20:41에 커밋됐고 원격에도 올라갔습니다**. 커밋은 `bf5d807`(`feat/route-map-geo-ab`, `origin/feat/route-map-geo-ab`)이고 16개 파일, +1542/−272줄입니다(`git show --stat bf5d807`). | 계획의 P0-0a("WIP 정리")는 이제 "이 브랜치를 origin/master 위로 rebase하는 일"로 바뀝니다. |
| S2 | 로컬 master가 origin/master보다 **8커밋 뒤처져 있습니다**(`git rev-list --count master..origin/master` = 8). 이 커밋들에는 i18n 병합, 노선도 개편 101ecac, **API 키 로그 마스킹 28093a3(PM-016)**, `CLAUDE.md` 절대 규칙이 들어 있습니다. | 모든 새 PR은 origin/master를 기준으로 만듭니다. |
| S3 | `bf5d807`을 origin/master와 합치면 **7개 파일에서 충돌 구간 14개**가 나옵니다(`git merge-tree 05c3b94 origin/master bf5d807`). 파일은 `route_diagram.py`, `routes/admin.py`, `routes/info.py`, `static/css/info.css`, `templates/info.html`, `data/changelog.json`, `tests/web/test_route_diagram.py`입니다. | 10/3 긴급 경로에 이 rebase를 넣으면 안 됩니다. |
| S4 | 기한형 공지는 **이미 구현돼 있습니다**. 위치는 `[notices]` 워크트리이고 커밋 전 스테이징 상태입니다. 신규 파일은 `services/notices.py`(561줄), `routes/notices.py`, `partial/notices.html`, `admin/notices.html`, `data/notices.seed.json`, 테스트 2개입니다. `board.html`, `unist_board.html`, `board_lite.html`, `_base.html`, `i18n.py`, `backup.py`, `admin.py`, `app.py`, `busno.py`도 수정했습니다(`git -C ../bushexa-notices status`). 파일 mtime은 `notices.py` 20:27, `test_notices_web.py` 20:30입니다. | 계획의 P4-3은 사실상 구현이 끝났습니다. 긴급 작업은 "처음부터 만들기"가 아니라 "보강하고 병합해 배포하기"입니다. |
| S5 | 10/3 노선 변경은 743 **한 건이 아니라 743과 1115 두 건**입니다. 출처는 "울산버스 공지 2272, 2026-09-18 인가"입니다(`[HEAD] route_diagram.py:159-175`, `[HEAD] info.html:73`). 1115는 현대자동차 명촌정문~성원상떼빌에 서지 않고 아산로로 갑니다. | 날짜가 박힌 문구가 "10/2까지" 형태까지 늘었습니다(`[HEAD] constants.py:74`, `info.html:123,135`, `route_diagram.py:205`, `route_lines.py:4,46,76`). |
| S6 | 문서화된 배포 스크립트 `../build-bus-tar.sh`는 VCS 밖에 있고 수정일은 2026-06-02입니다. 기본값으로 **이 체크아웃(`bus-hexa-revive-temp`)의 작업 트리**를 묶습니다(`:38`). `data/`도 통째로 복사합니다(`:72-81`). 마지막 번들은 2026-06-06에 만들어졌습니다. | 지금 번들을 만들면 A/B 계측이 들어간 **로컬 master 기반 트리**가 나갑니다. PM-016 마스킹이 빠진 채로요. 긴급 배포 절차를 새로 정해야 합니다(§1.6). |

---

## 0. 오너 결정 반영 요약

### 0.1 세 결정과 계획 변경

| 오너 결정 | 계획에서 바뀌는 것 |
|---|---|
| **(1) 긴급 패치는 유연한 기한형 공지로** | P0-9(i18n 키를 `.upcoming`과 `.active`로 나누는 핫픽스)는 **대체 경로로 내려갑니다**. 긴급 슬라이스는 **N0**(공지 병합, 시행일 단일 원천, 날짜 문구 전환)입니다. P4-3(공지 구조화 이관)은 N0-a에 **흡수**됩니다. D12 중 "`notices.json` + admin"은 **해소**됩니다. |
| **(2) D1: 기점 출발과 UNIST 경유 시각 분리, 가능하면 예측, 안 되면 기점 출발 폴백** | D1은 **시각 기준 4계층**으로 확정합니다(§2.1). D5는 "`origin_fallback`은 어떤 순위에도 넣지 않음"으로 **확정**합니다. P2-6a와 P2-6b는 **V1·V2로 흡수**합니다. P4-0~P4-2는 **E1~E3로 대체**합니다. 계획 6.5의 게이트(n≥30, IQR≤15, 시간대 단위)와 6.6의 `timetable_offsets.json`은 **폐기**합니다. D16(live 과잉 대체)은 **via 방향에 한해** V1에서 해소합니다. |
| **(3) 513은 번호 분기 없이 일반 규칙으로** | P1-1의 `DirectionSpec`을 **G0으로 앞당기고 확장**합니다. 관계(`from/via/to_unist`), 기준 정류소, 표시 메타를 넣습니다. 관계 판정 규칙이 지금 세 벌인데(`board.py:23-26`, `unist_board.py:188-203`, `unist_timetable.py:78-93`) 하나로 합칩니다. P2-1(513 분리)은 G0 위에서 "via 방향 일반 패널"로 바뀝니다. |

### 0.2 새 PR ID와 기존 항목의 대응

| 새 ID | 내용 | 대체·흡수하는 계획 항목 |
|---|---|---|
| N0-a | 공지 시스템 병합과 보강 | P4-3, D12의 일부 |
| N0-b | 노선 변경 레지스트리, 날짜 문구 전환(743·1115) | P0-9 |
| N0-c | 운영 배포(코드만 교체) | — |
| N1 | 공지 후속(`change` 필드, 화면당 상한, 위치) | P4-3의 잔여분 |
| R0 | `feat/route-map-geo-ab`를 origin/master로 rebase하고 레지스트리를 쓰도록 전환 | P0-0a |
| G0 | `DirectionSpec` 확장, `derive_relation`, 불변식 | P1-1의 방향 부분 |
| V1 | `/board`·`/lite` 기준 분리, live 시각 보정 | P2-6b, D5, D16(via) |
| V2 | `/unist`·`/timetable`·`/busno` 기준 분리 | P2-1, P2-6a, P0-5 후속 |
| E1 | 예측 운영 설정 파일과 관리자 토글 | P4-2의 일부 |
| E2 | 예측 산출 잡(그림자 모드) | P4-0, P4-1 |
| E3 | 예측 공개(설정 변경) | P4-2 |
| E4 | 운행 중 계층(현재 위치 + 구간 소요) | 신규 |
| X1 | poller 실패가 `[]`로 캐시되는 버그 수정 | 신규 |

P0-5(`/timetable` 513 '덕하발' 표식)는 값싼 응급조치라서 그대로 둡니다. V2가 머지되면 격자에서 513이 빠지므로 그때 제거합니다.

---

## 1. 기한형 공지 시스템

### 1.1 문제를 세 층으로 나눕니다 [추론]

743·1115 사례에는 성격이 다른 세 가지가 섞여 있습니다.

| 층 | 예 | 원천 | 전환 방식 |
|---|---|---|---|
| ① 공지(표시 기간이 있는 안내) | "10월 3일부터 743번은 …" | `data/notices.json` (데이터, 재시작 불필요) | `show_from ≤ now < show_until` |
| ② 시행일 전후로 바뀌는 문구 | 경유 열 "(10/3부터)", `/info` 본문, 노선도 주석 | 코드 문구 + 레지스트리 날짜 | `now.date() < effective` 이면 예고형, 아니면 평서형 |
| ③ 노선 데이터 자체 | 노선도 경로, `VIA_STOPS`, (추후) ROUTEID 추적 정류장 | `constants.py`(절대 규칙 6, `[origin] CLAUDE.md:54`) | 레지스트리 날짜 |

①은 운영자가 바꾸고, ②와 ③은 코드 사실입니다. 셋은 **같은 날짜 원천**(레지스트리 `ROUTE_CHANGES`)을 봐야 합니다. 공지 데이터가 원천이 되면 안 됩니다. 공지를 끄는 순간 노선 형상까지 바뀌기 때문입니다.

### 1.2 이미 구현된 것 [검증, `[notices]`]

| 요구사항 | 상태 | 근거 |
|---|---|---|
| live(`data/notices.json`)와 seed(`bushexa/data/notices.seed.json`, 공개 static 아님) 분리 | 완료 | `notices.py:58` |
| 표시 기간. 날짜만 쓰면 그날 끝까지 | 완료 | `parse_when(end_of_day=True)` :109-132 |
| 시행 전후 문구, `{date}`와 `{dow}` 치환 | 완료 | `phase` :169-173, `render_text` :184-198 |
| 종류와 심각도 | 완료 | `KINDS = (suspension, warning, route_change, info)` :62 |
| 화면 지정 | 완료 | `SURFACES` :63 (board, lite, unist, stops, timetable, busno, info, running) |
| 노선 필터 | 완료 | `/busno`는 실제로 표시 중인 노선 기준(`routes/busno.py`의 `g.notice_routes`) |
| 워커 간 반영 | 완료 | `_signature` (inode, mtime_ns, ctime_ns, size) :380-407 |
| 쓰기 잠금, 파손 시 저장 거부 | 완료 | `_mutate` + `locked_update_json` :472-496 |
| 오래 열린 화면 | 완료 | `POLL_SURFACES={board,unist,stops}` :79, 60초 `hx-trigger` |
| live 파손 시 seed 폴백 | 완료 | `load_entries` :436-441 |
| 백업 포함, 복구 시 항목 검증 | 완료 | `backup.py` `_FLAT_FILES` |
| 관리자 CRUD, 미리보기(`?at=`), 감사 로그, seed 가져오기, drift 표시 | 완료 | `admin.py`, `seed_drift` :457, `import_seed` :532 |
| `/lite` 평문 공지 | 완료 | `board_lite.html:18-19` |

**남은 결함 [검증]** — K1·K3·K4는 개정 시점에 수정해 `[notices]`에 스테이징했습니다(테스트 714 통과, 1 skip).
- K1 ✅ 수정: seed `text_after`를 "743번은 이제 구영리에서 범서중학교를 경유합니다 ({date} 변경, …)"로 바꿨습니다. 시행 후 화면에 "부터"가 남지 않습니다.
- K2 ⏳ 오너 확인 필요: seed에 1115가 없습니다(Q3).
- K3 ✅ 수정: `enabled`가 JSON bool이 아니면 `NoticeError`.
- K4 ✅ 수정: 폴링 `hx-get` URL에 `lang`을 넣었습니다(`test_poll_url_keeps_language`, 쿠키 없는 클라이언트로 검증).
- K5: 시행일 단일 원천이 없습니다. 경유 열과 `/info` 본문의 날짜 문구도 전환되지 않습니다(`[origin] constants.py:68`, `i18n.py:77-78`, `info.html:64,65,74`, `route_diagram.py:32,96,103`).

### 1.3 데이터 스키마

**`data/notices.json` v1** (구현 그대로 유지. 필드 규칙은 `notices.py` `validate` :254-315)

```json
{ "id": "743-beomseo-2026", "kind": "route_change", "routes": ["743"],
  "surfaces": ["board","lite","unist","stops","timetable","busno"],
  "show_from": null, "show_until": "2026-10-31", "effective_from": "2026-10-03",
  "text":       {"ko": "{date}부터 743번은 구영리에서 범서중학교를 경유합니다 (513번과 같은 경로, 713·753·1115번과 다름).",
                 "en": "From {date}, bus 743 passes Beomseo Middle School in Guyoung-ri (same as 513; different from 713/753/1115)."},
  "text_after": {"ko": "743번은 이제 구영리에서 범서중학교를 경유합니다 ({date} 변경, 513번과 같은 경로).",
                 "en": "Bus 743 now passes Beomseo Middle School in Guyoung-ri (changed {date}; same as 513)."},
  "link": "info", "priority": 0, "enabled": true }
```

1115 항목도 같은 모양입니다. `id`는 `1115-asanro-2026`, `routes`는 `["1115"]`이고, `surfaces`에는 `stops`를 넣지 않습니다. 문구는 §1.5에 있습니다.

규칙: `text_after`에는 "부터"와 "까지"를 쓰지 않습니다(§1.7의 계약 테스트).

**노선 변경 레지스트리 (N0-b).** 데이터와 로직을 나눕니다. 이 부분은 설계안 두 개의 차이를 조정한 결과입니다[추론].
- 공지 설계는 `bushexa/data/route_changes.py`에 두자고 했습니다.
- 방향 설계는 `constants.py`에 두자고 했습니다.
- 절대 규칙 6("노선·정류장 ID와 문구는 `data/constants.py`에만", `[origin] CLAUDE.md:54`)을 지키려면 **데이터는 `constants.py`**, **판정 로직은 `bushexa/domain/route_changes.py`**에 둡니다.

```python
# bushexa/data/constants.py (추가형)
ROUTE_CHANGES: tuple[tuple, ...] = (
    # (id, line, effective(KST), route_ids(방향), summary, source)
    ("743-beomseo-2026", "743",  date(2026, 10, 3), ("195000216", "195000215"),
     "구영리 범서중학교앞 경유", "울산버스 공지 2272 (2026-09-18 인가)"),
    ("1115-asanro-2026", "1115", date(2026, 10, 3), ("194000107", "194000106"),
     "현대자동차(명촌정문~성원상떼빌) 미정차, 아산로 경유", "울산버스 공지 2272 (2026-09-18 인가)"),
)
# VIA_STOPS 값은 '시행 후' 평서형. 시행 전 예고형은 따로 둔다.
VIA_STOPS_DATED: dict[str, dict[str, tuple[str, str]]] = {
    "743":  {"명촌":  ("743-beomseo-2026", "천상 - 구영리(범서중학교, {md}부터) - 굴화주공 - … - 명촌 (종점)")},
    "1115": {"꽃바위": ("1115-asanro-2026", "… - 태화강역광장 - 현대자동차({md_prev}까지) - 아산로({md}부터) - 남목 - … - 꽃바위 (종점)")},
}
```

```python
# bushexa/domain/route_changes.py (신규, 순수. constants와 time_utils만 import)
@dataclass(frozen=True)
class RouteChange: id: str; line: str; effective: date; route_ids: tuple[str, ...]; summary: str; source: str
def get_change(change_id: str) -> RouteChange              # 모르는 id는 KeyError (fail-closed)
def is_effective(change_id: str, today: date | None = None) -> bool   # None이면 get_now().date()
def md(d: date) -> str; def md_prev(d: date) -> str         # "10/3", "10/2"
def long_label(d: date, lang: str) -> str                   # "2026년 10월 3일" / "Oct 3, 2026"
def dated_via(busno: str, terminal_key: str, today: date) -> str | None   # 시행 전이면 예고형, 아니면 None(→ VIA_STOPS)
def history_epoch(route_id: str) -> date | None             # 이 방향의 최신 effective. §2 예측기가 이 날짜 이전 표본을 버림
```

- 모르는 id를 fail-open(시행 후로 간주)으로 처리하면 오타가 시행 전 기간 내내 숨습니다. 그래서 `KeyError`로 막습니다[추론].
- 공지 `effective_from`과 레지스트리 날짜는 **테스트로 묶습니다**(`test_seed_effective_dates_match_registry`). 스키마 필드 `change`는 N1에서 추가합니다.
- 지금 `validate()`는 고정된 키만 담은 dict를 새로 만들어 반환합니다(`notices.py:302-315`). 그래서 필드를 미리 넣어 두면 저장이나 가져오기를 할 때 조용히 사라집니다.

### 1.4 통합 지점 (N0-b, `[origin]` 줄번호)

| 위치 | 현재 | 변경 |
|---|---|---|
| `bushexa/web/route_diagram.py:32` | `VIA_743_BEOMSEO_FROM = date(2026, 10, 3)` | `= get_change("743-beomseo-2026").effective` (이름은 유지) |
| `route_diagram.py:96` | `today or date.today()` | `today or get_now().date()` (절대 규칙 5. CI는 UTC) |
| `route_diagram.py:103` | `"10/3부터"` | `f"{md(...)}부터"` |
| `bushexa/data/constants.py:67-69` | 날짜가 박힌 str | 평서형 + `VIA_STOPS_DATED` |
| (신규) 1115 경유 문자열 | origin에는 1115 변경이 반영되지 않음 | `[HEAD] constants.py:74`의 사실을 평서형과 예고형으로 옮겨 적음 |
| `bushexa/domain/board.py:56-76` `_via_for` | 날짜 개념 없음 | `*, today` 추가. 우선순위: override > `dated_via` > `VIA_STOPS` > 노선 정류장 |
| `board.py:79-84` `via_default`, 호출부 :155, :200 | | `today=now.date()` 전달(`get_board_data`의 `now` :241) |
| `bushexa/web/i18n.py` (`localize_stop` :174 부근) | `M/D부터`만 번역 | `_UNTIL_DATE_RE`와 `stop.annot.until_date` {ko "{date}까지", en "until {date}"} 추가 |
| `bushexa/web/routes/info.py:40-42` | changelog와 route_lines만 전달 | `route_changes={id: {effective, md, md_prev, long_ko, long_en}}` 전달 |
| `bushexa/web/templates/info.html:64-65,74` | 정적 날짜 문구 | `{% if route_changes['743-beomseo-2026'].effective %}`로 평서형과 예고형 분기. 1115 문장과 표 행 추가 |
| `bushexa/data/notices.seed.json` | 743만 있음, `text_after`에 '부터' | 두 항목(§1.3) |
| `[notices] partial/notices.html:26` | `url_for('notices.notices_partial', surface=…)` | `lang=g.lang` 추가(K4) |
| `[notices] notices.py:314` | `bool(entry.get("enabled", True))` | JSON bool이 아니면 `NoticeError`(K3) |

R0(오너 브랜치 rebase)에서 할 일:
- `[HEAD] route_diagram.py:152-176`의 `RouteChange`/`ROUTE_CHANGES_FROM`/`ROUTE_CHANGES`는 **노선도 전용 delta** `DIAGRAM_DELTAS: dict[change_id, (old, new)]`로 바꾸고, 날짜는 `get_change(id).effective`에서 읽습니다.
- 이름이 겹치므로 `ROUTE_CHANGES` 심볼은 노선도 모듈에서 없앱니다.
- `route_diagram.py:202,205` STOP_NOTE와 `route_lines.py`의 "10/3부터"/"10/2까지"도 `md()`로 만듭니다.

### 1.5 문구 (ko / en)

| 위치 | 시행 전 | 시행 후 |
|---|---|---|
| 743 공지 | {date}부터 743번은 구영리에서 범서중학교를 경유합니다 (513번과 같은 경로, 713·753·1115번과 다름). / From {date}, bus 743 passes Beomseo Middle School in Guyoung-ri (same as 513; different from 713/753/1115). | 743번은 이제 구영리에서 범서중학교를 경유합니다 ({date} 변경, 513번과 같은 경로). / Bus 743 now passes Beomseo Middle School in Guyoung-ri (changed {date}; same as 513). |
| 1115 공지 | {date}부터 1115번은 현대자동차 정류장(명촌정문~성원상떼빌)에 서지 않고 아산로로 갑니다. / From {date}, bus 1115 skips the Hyundai Motor stops (Myeongchon Gate to Seongwon Sangtteville) and runs via Asan-ro. | 1115번은 이제 현대자동차 정류장(명촌정문~성원상떼빌)에 서지 않고 아산로로 갑니다 ({date} 변경). / Bus 1115 now skips the Hyundai Motor stops and runs via Asan-ro (changed {date}). |
| `/board` 743 경유 열 | 천상 - 구영리(범서중학교, 10/3부터) - … | 천상 - 구영리(범서중학교) - … |
| `/board` 1115 경유 열 | … - 태화강역광장 - 현대자동차(10/2까지) - 아산로(10/3부터) - 남목 - … | … - 태화강역광장 - 아산로 - 남목 - … |
| `/info` 배너 | 2026년 10월 3일부터 …(743), 10월 2일까지는 … 10월 3일부터는 …(1115) | 평서형(`[HEAD] info.html:122-123`의 내용을 날짜 없이) |

- `[HEAD] info.html:120-124` 배너는 KO와 EN을 한 div에 병기하고, EN에는 1115 문장이 없습니다[검증]. 계획 N-6(한 화면 두 언어 병기 금지)에 따라 N0-b에서 언어별로 나눕니다.
- 접근성: 60초마다 바뀌는 공지 영역에 `aria-live`를 달지 않습니다. 달면 스크린리더가 같은 내용을 반복해서 읽습니다[추론].

### 1.6 긴급 슬라이스 (10/3 00:00 KST 기한)

**일정 [검증: `data/holiday_cache.json`에 20261003, 20261005, 20261009]**
- 10/3(토)은 개천절, 10/5(월)는 대체공휴일입니다.
- 작업일은 9/30, 10/1, 10/2 사흘입니다.
- **10/2(금) 18:00 배포가 목표**이고, 23:59가 절대 기한입니다.

| 슬라이스 | 기한 | 베이스 | 작업 | 파일 | 크기 |
|---|---|---|---|---|---|
| **N0-a** | 9/30 머지 | origin/master (`feat/deadline-notices`) | (1) 스테이징된 공지 구현 커밋(오너) (2)~(4) K3·K4·K1 ✅ 완료 (5) seed 1115 추가(Q3 답을 받은 뒤) (6) 아래 테스트 중 1·3·4 ✅ 완료 | `services/notices.py`, `partial/notices.html`, `data/notices.seed.json`, `tests/web/test_notices_web.py`, `tests/services/test_notices.py` | 구현은 완료, 보강 약 40줄 |
| **N0-b** | 10/1 머지 | N0-a 이후의 origin/master | §1.3 레지스트리와 `VIA_STOPS_DATED`, §1.4 통합 지점(1115 사실 포함), 아래 테스트 | `constants.py`, `domain/route_changes.py`(신규), `domain/board.py`, `web/route_diagram.py`, `web/i18n.py`, `routes/info.py`, `templates/info.html`, 테스트 | S~M(약 250줄, 테스트 포함) |
| **N0-c** | 10/2 오전 | **깨끗한** origin/master 체크아웃 | 운영에서 `bushexa/`만 교체하고 web 재시작. `data/`는 건드리지 않음. 워커 코드(ROUTEID)는 바뀌지 않으므로 워커는 재시작하지 않음 | 운영 | — |
| **N0-v** | 10/3 00:05 | — | 확인 체크리스트 실행 | — | — |

**N0-a 테스트**
1. `test_notices_web.py:74-78` 개정: 시행 후 문구 "743번은 이제 구영리에서 범서중학교를 경유합니다 (10월 3일 변경"을 단언하고, `"10월 3일부터" not in html`을 추가합니다.
2. `test_seed_1115_notice_switches`
   - 10/2 12:00+09:00의 `/busno?bus=1115`에 "10월 3일부터 1115번은"이 있어야 합니다.
   - 10/4에는 "1115번은 이제"가 있고 "부터"가 0건이어야 합니다.
   - `/busno?bus=713`에는 "아산로"가 0건이어야 합니다.
3. `test_enabled_must_be_bool`: `{"enabled": "false"}`이면 `NoticeError`.
4. `test_poll_url_carries_lang`: `/board?lang=en`의 `hx-get`에 `lang=en`이 있어야 합니다.

**N0-b 테스트**
1. `tests/data/test_route_changes.py`
   - id가 중복되지 않고, 모든 `route_ids`가 `ROUTEID` 키이며, `source`가 비어 있지 않습니다.
   - 10/2이면 `is_effective`가 False, 10/3이면 True입니다.
   - `freeze_time("2026-10-02T23:59:59+09:00")`이면 False, `freeze_time("2026-10-02T15:00:00Z")`이면 True입니다(TZ 경계).
   - `get_change("nope")`는 `KeyError`입니다.
2. `test_seed_effective_dates_match_registry`: `kind=="route_change"`이고 노선이 하나인 seed 항목은 레지스트리의 `(line, effective)`와 같아야 합니다.
3. `tests/domain/test_board.py`
   - `_via_for(..., today=10/2)`에 "(범서중학교, 10/3부터)"가 있습니다. `today=10/4`이면 "부터"가 0건입니다. 1115도 같은 방식입니다.
   - override가 있으면 날짜와 관계없이 override 값이 나옵니다.
   - `get_board_data(FakeClock(2026-10-03T00:00:30+09:00))`이면 평서형입니다.
4. `test_i18n.py`: `localize_stop("현대자동차(10/2까지)", "en", …)`에 "until 10/2"가 있습니다.
5. **교차 화면 계약** `tests/web/test_date_notice_contract.py`
   - 대상: `/board`, `/partial/board`, `/unist`, `/partial/unist`, `/lite`, `/info`, `/timetable?day=0`, `/busno?bus=743`, `/busno?bus=1115`. 각각 ko와 en.
   - 10/4 12:00+09:00에 정규식 `\d{1,2}/\d{1,2}(부터|까지)|\d{1,2}월 \d{1,2}일(부터|까지)|From Oct \d|until \d`가 **0건**이어야 합니다. "범서중학교"와 "아산로"는 1건 이상이어야 합니다.
   - **예외:** `/info` 변경이력 섹션은 검사에서 뺍니다. `[HEAD] data/changelog.json`에 "10월 3일부터 743번은 …" 항목(2026-09-29)이 이력으로 들어 있기 때문입니다[검증, `git diff 05c3b94 bf5d807 -- data/changelog.json`]. 빼지 않으면 R0 이후 이 테스트가 깨집니다.
   - 11/1 00:00이면 `notice-list` 0건이고, 경유 열과 `/info`는 평서형을 유지합니다.
6. 정책 테스트 `test_no_hardcoded_dated_copy`: `templates/**/*.html`, `constants.py`, `web/route_*.py`에서 위 정규식이 `VIA_STOPS_DATED` 밖에서 0건이어야 합니다. 재발을 막는 장치입니다.

**N0-c 배포 체크리스트** (Q2 답을 받은 뒤)
- [ ] 운영 중인 커밋과 배포 방식을 확인합니다(S6).
- [ ] 운영 `data/via_overrides.json`에서 743과 1115 항목을 grep합니다. 날짜 문구가 있으면 관리자 화면에서 지웁니다. override가 상수보다 우선하기 때문입니다(`board.py:67-70`).
- [ ] 운영에 `data/notices.json`이 없는지 확인합니다. 없어야 seed 두 건이 나옵니다. 이미 있으면 관리자 화면에서 "seed 가져오기"를 합니다.
- [ ] 배포 직후 `/board`, `/unist`, `/lite`, `/timetable`, `/busno?bus=743`, `/busno?bus=1115`, `/info`를 ko와 en으로 확인합니다.
- [ ] 10/3 00:05에 같은 화면이 평서형인지 확인합니다. 관리자 재크롤로 743·1115의 시간표와 route_id가 바뀌었는지도 봅니다(Q10).

**대체 경로**
- N0-b만 늦으면: N0-a만 배포합니다. 공지 배너는 자동으로 바뀌지만 경유 열과 `/info`에 "10/3부터"가 며칠 남습니다. 틀린 경로 안내가 아니라 낡은 문구라서 심각도는 낮습니다[추론].
- N0-a도 늦으면: 계획 P0-9 원안(i18n `.upcoming`/`.active` 분기)을 씁니다. 1115는 i18n 키를 하나 추가합니다.
- 아무것도 못 나가면: 운영 문구는 운영 버전 그대로입니다. 운영 버전을 모르면 영향도 판단할 수 없습니다(Q2).

### 1.7 후속 슬라이스 (N1, 10/6 이후)

- 공지 선택 필드 `change`를 추가합니다.
  - `validate`가 이 필드를 보존하게 하고, 관리자 폼에 레지스트리 드롭다운을 둡니다.
  - 저장할 때는 엄격하게: 모르는 id이거나 날짜가 다르면 거부합니다.
  - 로드할 때는 관대하게: 경고만 남깁니다.
- 화면당 공지 상한(권장 3건)과 `/info#notices` 전체 목록을 둡니다.
- `/board` 공지 위치를 정합니다. 지금은 `_base.html` `{% block notices %}`가 제목 위에 옵니다(Q25).
- `/stops`를 `POLL_SURFACES`에서 뺄지 정합니다. `/stops`에는 원래 주기 갱신이 없습니다(`stops.html:13,26`).
- changelog 편집의 공백을 메웁니다. 감사 로그(`admin.py:952-977`에 `_audit` 없음)와 백업(`backup.py:28-35`에 없음)이 빠져 있습니다.
- `build-bus-tar.sh`를 저장소로 옮기고, `data/` 제외 목록에 `notices.json`, `route_map_ab.json`, (E1 이후) `prediction_settings.json`, `unist_estimates.json`을 추가합니다.
- ROUTEID 추적 정류장을 갱신합니다. 1115의 현대출고 사무소앞(195030615/195030616)은 10/3 이후 지나지 않고, 743 목록에는 범서중학교앞이 없습니다(`constants.py:45-56`). 워커 재시작이 필요하며, 공식 정류소 목록을 대조한 뒤에 합니다(PM-014, Q23).

---

## 2. 경유 시각 분리와 예측 (D1)

### 2.1 시각 기준 계층

모든 시각에 `basis`를 붙입니다. 한 편마다 **위에서부터 처음 성립하는 기준 하나**를 씁니다.

| 순위 | basis | 의미 | 계산 | 등장 방향 |
|---|---|---|---|---|
| 1 | `unist_exact` | 시간표 시각이 곧 UNIST 시각 | 시간표 | from_unist |
| 2 | `unist_live` | 기준 정류소 **자체**의 BIS ETA | `fetched_at + eta` (현재 코드는 `now + eta`, `board.py:192-199`) | via(현재), from(해당 없음) |
| 3a | `unist_predicted` (`model="tracked"`, E4) | 운행 중인 차량의 현재 위치 + 구간 소요 중앙값 | govtrack 위치 또는 상류 ETA | via, to |
| 3b | `unist_predicted` (`model="history"`, E2·E3) | 과거 기록으로 산출한 편별 통과 시각 | §2.4 | via, to |
| 4 | `origin_fallback` | **기점 출발 시각. UNIST 시각이 아닙니다** | 시간표 | via, to |

**불변식** (§3.6에서 테스트로 고정)
- `origin_fallback`이면 `unist_time is None`, `minutes_until is None`이고, 어떤 순위(FIRST/SECOND, 다음 출발, 카운트다운)도 받지 않습니다.
- `unist_predicted`이면 카운트다운이 없습니다(계획 N-1). "약 HH:MM"만 표시합니다.
- 순위 대상은 `unist_exact`와 **신선한** `unist_live`뿐입니다. `unist_predicted`는 설정 `rank_predicted`(기본 false)로만 켤 수 있습니다.

### 2.2 현재 결함 [검증]

- **/board.** 2026-09-29(평일) 17:47에 실시간이 없으면 "17:50 513 삼남 출발 예정"이 **FIRST**, 17:55 713·743이 SECOND가 됩니다(`get_board_data`를 FakeClock과 mock으로 실행).
  - 원인 1: via 시간표 행이 `present=f"{departure} 출발 예정"`이고 `arrival_minutes`에 기점 시각을 넣습니다(`board.py:146-168`).
  - 원인 2: 순위가 basis를 가리지 않습니다(`board.py:291-325`).
- **/board.** 513 live가 한 대만 있어도 같은 (노선, 방면)의 시간표 행이 **전부** 사라집니다(`board.py:257-263`).
- **/unist.** via 카드 한 장에 live ETA와 기점 시각이 섞이고, 문구도 UNIST 출발 카드와 같습니다(`unist_board.py:82,95,120`). 이미 기점을 떠난 편은 `_is_future`(`:45-48`)에서 사라집니다.
- **/timetable.** `deps[0]`만 씁니다. 그래서 513 덕하 기점 시각(17:00, 17:30, 18:30 …)이 UNIST 출발 격자에 라벨 없이 섞이고, 삼남 방향은 빠집니다(`unist_timetable.py:78-93`).
- **/busno.** '출발지' 선택만 있고 기준 표기가 없습니다(`busno.py:93-113`, `busno.html:35-47`).

### 2.3 데이터 가용성 (실측)

**있는 데이터 [검증]**

| 원천 | 규모 | 비고 |
|---|---|---|
| `data/bushexa.db` `bus_timelog` | **16행** (2026-09-29 17:45:51~17:47:21, 513은 3행) | 사본을 `mode=ro`로 열어 조회 |
| `data/bushexa.db` `bus_arrival_cache` | 17행 (정류장별 최신 1건) | 이력이 없어 ETA 정확도를 사후 검증할 수 없음(`schema.py:28-33`) |
| `logs/logs.tsv` (gitignore, `.gitignore:11`) | **139,852행**, 2026-04-16 14:58 ~ 06-01 16:55, 47일(평일 31, 토 7, 일·공휴일 9) | 5/17 이후 하루 행 수가 약 3,600에서 1,000~2,000으로 줄었고, 원인은 확인하지 못함 |
| `data/logs.tsv` | 1,094행 (6/2 1,077, 9/29 17) | 조사 보고서마다 인용한 "1,095행"은 이 파일 |
| 운영 DB | 확인 불가 | 이 호스트에는 실행 중인 bushexa 컨테이너가 없음(`docker ps`) |

**기록 방식 [검증]**
- 약 15초마다 조회합니다(`daemon.py:124`). 01:00~05:00에는 조회하지 않습니다(`:31`).
- 차량의 **정류장이 바뀌었을 때만** 1행을 쓰고, 그 정류장이 추적 목록 안에 있어야 합니다(`recorder.py:188-198`).
- 정류장 순번, GPS, 운행 ID, ETA는 저장하지 않습니다(`schema.py:14-24`).

**관측 커버리지 [시뮬]**
- 513 운행 가운데 196040234가 기록된 비율은 68~69%, 캠퍼스 정류장 3곳 중 하나라도 기록된 비율은 90%입니다.
- 기점 관측률은 덕하발 57%, 삼남발 37%입니다.

**시간표 JSON이 실제 배차와 맞지 않습니다 [시뮬, 핵심]**
- 기점 관측 시각의 분 끝자리가 0~1인 비율은 덕하발 83%, 삼남발 85%입니다. 10분 격자에 몰려 있으므로 실제 배차 시각으로 보입니다.
- 관측 시각이 JSON 편성 ±1.5분 안에 드는 비율:

| 방향 | 일치율 |
|---|---|
| 513 덕하발 | 18~25% |
| 513 삼남발 | 28~40% |
| 1115 UNIST발 | 26~29% |
| 1115 꽃바위발 | 22~28% |
| 713 | 57~80% |
| 743 | 64~75% |
| 753 | 57~69% |

- 예: 6/2 삼남 기점 관측은 11:59, 12:20, 12:50, 13:20, 13:40이고, JSON은 12:00, 12:30, 13:00, 13:30, 14:00입니다.
- JSON mtime은 2026-06-02입니다.

**모델별 결과 [시뮬]**

| 모델 | 방향 | 표본 | 오차 | 판단 |
|---|---|---|---|---|
| JSON 편 + 편별 중앙값, LODO | 421 덕하발 / 422 삼남발 | — | 중앙 절대오차 3.98 / 2.28분, **p90 25.1** / 6.9분 | 꼬리가 길어 기각 |
| 기점 관측 + 시간대 오프셋, LODO | 421 / 422 | n=536 / 330 | 3.5 / 2.8분, p90 9.6 / 7.3, ±5분 66% / 78% | 버스가 출발한 뒤에만 쓸 수 있어 E4 계층으로 사용 |
| 과거 통과 군집(pass_clusters), LODO | 421 평일 / 422 평일 | 관측 통과 664건, 약 32군집 | 3.2 / 2.3분, p90 9.4 / 6.0, ±5분 69% / 83% | 누락·추가 편에 벌점이 없어 낙관적. 편과 연결되지 않아 폴백 편과 중복을 제거할 수 없음 |
| **D′: JSON 편 + 편별 오프셋 + "추정 실제 출발에 가장 가까운 편" 매칭(≤20분)** | 421 / 422 | 학습 4/16~5/15 평일 21일, 평가 5/16~6/1 평일 10일 | **전진 검증** 중앙 절대오차 3.4 / 2.2, p80 5.8 / 5.1, p90 7.4 / 6.5 | **1순위 후보** |
| (비교) D′를 원안 매칭("창 안 가장 늦은 편")으로 | 421 / 422 | 같음 | 전진 검증 4.8 / 2.3, p80 18.7 / 5.9, p90 **29.3** / 13.9 | 기각. 421 예측의 31%가 10분 넘게 틀림 |

- (참고, **폐기된 초안 게이트** 기준) D′ 게이트(n≥12, 날짜≥8, IQR≤8, LODO p80≤6)를 통과한 편 수:
  - 가장 가까운 편 매칭: 421 14편, 422 23편(28편 중)
  - **이후 기간 p80≤6 유지:** 421 **6편**, 422 **13편**(`fwd_gate.py`)
- 평가 표본이 평일 10일뿐이라 수치는 잠정값입니다.

**기점 관측에서 196040234까지 소요 (평일 중앙값 [IQR], 참고) [시뮬]**

| 방향 | 05-06시 | 07-09시 | 10-16시 | 17-19시 | 20-22시 |
|---|---|---|---|---|---|
| 421 덕하발 | 55.1 (n=50) | 66.5 [61.0–70.1] (n=68) | 62.9 [59.5–68.3] (n=204) | 64.5 [60.8–75.4], p90 **93.3** (n=56) | 55.5 (n=55) |
| 422 삼남발 | 38.5 (n=25) | 40.9 (n=44) | 42.2 [39.7–44.2] (n=133) | 41.4 (n=62) | 35.4 (n=35) |

**상류 정류장에서 UNIST(234)까지 구간 소요 (E4 근거, 중앙값 / IQR 폭) [시뮬]**

| 구간 | 중앙값 | IQR 폭 |
|---|---|---|
| 196040236 → 234 | 2.9분 | 0.5 |
| 196040212 → 234 | 5.9분 | 0.8 |
| 196020412(범서중) → 234 | 13.0분 | 2.3 |
| 193040224 → 234 | 19.7분 | 3.3 |
| 193031110(시청앞) → 234 | 36.3분 | 5.4 |
| 196015414(울산역) → 234 | 19.5분 | 2.8 |

**실시간 [검증]**
- 17:48:01 스냅샷의 196040234 payload에는 노선마다 1대씩 들어 있습니다.
  - 422 차량: '울산역(시내 방면' 1237초
  - 421 차량: '삼호' 1317초
- 보정한 통과 시각은 18:08:38과 18:09:58입니다. 현재 코드의 `now(17:47)+ETA` 방식은 18:07과 18:08로 약 1분 이르게 나옵니다.
- poller 한 사이클은 약 64초입니다(`data/arrival_status.json` 17:45:51→17:46:55). 관리자는 주기를 최대 600초까지 설정할 수 있습니다(`services/crawl_settings.py:27-28`).

**도착 방향 (V5·D6 근거) [시뮬]**
- 시간표 출발 → 196040232 평일 중앙값: 713 77.9분(IQR 70.8~84.4), 743 71.1분, 753 78.2분
- 1115는 기점 관측 → 999000145가 98.1분입니다. 1115 추적 목록에는 196040232가 없습니다(`constants.py:55-56`).

**오너 게이트 시뮬레이션 (개정 추가) [시뮬]**

규칙: 평가일 d마다 `[d−30일, d)` 창에서 **같은 요일군·같은 편**의 표본이 4건 이상이면 예측, 아니면 기점 출발 폴백. 봄학기 `logs/logs.tsv`로 전진 평가했습니다(평가일은 데이터 시작 30일 뒤부터, 평일 10일·주말 7일). 스크립트: `analysis/owner_gate_sim*.py`, `analysis/owner_gate_cluster*.py`.

*편(slot) 모델* — 예측 = 시간표 편 시각 + 창 안 오프셋 중앙값(편 매칭은 조사 스크립트의 `sched_dep`, 즉 원안 매칭)

| 방향 | 요일군 | 게이트 통과 편 | 오차 중앙 | p80 | p90 | ±5분 |
|---|---|---|---|---|---|---|
| 513 덕하발 | 평일 | 100% | 6.0 | 24.6 | 32.3 | 43% |
| 513 덕하발 | 토(단독) | **36%** | 4.8 | 8.6 | 20.0 | 58% |
| 513 덕하발 | 일·공휴일(단독) | 65% | 5.6 | 18.7 | 27.4 | 45% |
| 513 덕하발 | **주말 통합** | **97%** | 3.8 | 8.8 | 18.4 | 62% |
| 513 삼남발 | 평일 | 100% | 3.0 | 5.8 | 14.5 | 75% |
| 513 삼남발 | 토(단독) | **23%** | 2.6 | 7.1 | 8.4 | 75% |
| 513 삼남발 | 일·공휴일(단독) | 71% | 1.3 | 3.9 | 5.5 | 90% |
| 513 삼남발 | **주말 통합** | **96%** | 2.2 | 4.5 | 6.5 | 84% |

*통과시각 군집 모델* — 같은 요일군 창의 UNIST 통과 시각을 4분 간격으로 군집, **서로 다른 날 4일 이상** 나온 군집만 채택

| 방향 | 요일군 | 채택 군집/일 | 최근접 오차 중앙 | p80 | p90 | ±5분 |
|---|---|---|---|---|---|---|
| 513 덕하발 | 평일 | 34 | 3.2 | 7.1 | 9.8 | 69% |
| 513 덕하발 | 토(단독) | 4 | 96.9 | — | — | 9% |
| 513 덕하발 | 주말 통합 | 22 | 3.7 | 6.4 | 9.0 | 68% |
| 513 삼남발 | 평일 | 32 | 2.5 | 4.9 | 6.5 | 81% |
| 513 삼남발 | 주말 통합 | 23 | 2.4 | 5.0 | 7.4 | 80% |

해석 [추론]
- **평일은 오너 게이트로 충분히 채워집니다.** 30일에 평일이 약 21일이라 편마다 4건은 쉽게 넘습니다.
- **토요일 단독은 사실상 폴백 전용**입니다. 30일에 토요일이 4~5번뿐이고 UNIST 통과 관측률이 68~70%라 "4건"을 거의 못 채웁니다(통과 23~36%, 군집 모델은 하루 4개).
- **주말 통합이 해법입니다.** 5개 노선 모두 시간표 JSON의 토(`"1"`)와 일·공휴일(`"2"`)이 완전히 같습니다(DS-12). 요일군을 {평일, 주말·공휴일} 두 개로 쓰면 통과율 96~97%, 오차도 평일과 비슷합니다(Q32). 단, 시간표가 토/일로 갈라지는 날이 오면(크롤 결과 `d['1'] != d['2']`) 그 노선은 자동으로 3요일군으로 돌아가야 합니다.
- **덕하발은 '편 + 오프셋' 방식의 꼬리가 깁니다**(평일 p80 24.6분). 513 JSON이 실제 배차와 18~25%만 맞기 때문입니다(위 표). 같은 오너 게이트라도 조사의 **D′ 매칭**(추정 실제 출발에 가장 가까운 편, ≤20분)이나 **군집 모델**을 쓰면 p80이 5.8~7.1분으로 줄어듭니다. 게이트는 오너 규칙을 쓰고, **모델·매칭 방식은 D′를 기본**으로 합니다(Q17 개정).
- 오너 게이트만으로는 "표본은 4건인데 들쭉날쭉한" 편을 거르지 못합니다. 덕하발 평일에 IQR≤10분을 덧붙이면 통과율 56%, p90 28.9분으로 효과가 작고 적용률 손실이 큽니다. 그래서 품질 조건은 **기본으로 두지 않고**, 관리자 화면의 그림자 비교(편별 최근 오차)로 드러내 방향 단위 off로 대응합니다(Q33).

**결론 [추론] (개정)**
- 오늘 공개할 수 있는 예측은 **0건**입니다. 운영 이력이 확인되지 않았고, 봄학기 이후 데이터는 이 호스트에 없습니다(Q18).
- V1(분리 + live + 폴백)만으로 오너가 지적한 "기점 출발이 UNIST 출발보다 우선시되는" 결함은 사라집니다.
- 오너 게이트(30일·4건)는 초안 게이트보다 훨씬 빨리 찹니다. 운영 `bus_timelog`가 끊김 없이 쌓이고 있다면(Q18) 평일은 **표본 4일째**, 주말 통합은 **주말·공휴일 4일째**부터 편별로 켜집니다. 10/3·10/5·10/9 연휴와 743·1115 경로 변경(10/3, `history_epoch`)을 감안하면, 513 평일은 10/6 이후 약 1주, 743·1115는 10/3 이후 표본만 인정되므로 그 뒤 약 1주가 걸립니다.
- 봄학기 기준 예상 적용률(오너 게이트, 주말 통합): 513 평일·주말 모두 96~100% 편. 나머지는 기점 출발 폴백.

### 2.4 예측 산출 규칙 (E2, 신규 `bushexa/services/unist_estimates.py`)

1. **운행 분리.** (route_id, 차량) 단위로 나눕니다. 60분 넘게 비거나(`running._SPLIT_GAP_MINUTES`, `running.py:78`) `stops[0]`이 다시 나오면 새 운행입니다. `running.py:191`의 HH:MM 절삭은 쓰지 않고 원본 idx(초)를 씁니다.
2. **운행별 값.** `t_origin`(기점 관측), `t_first`(기점 이외 첫 관측과 그 정류장), `P`(`spec.ref_stop_id`를 처음 본 시각)를 구합니다. `P`가 없으면 제외합니다.
3. **추정 실제 출발.** `t_origin`이 있으면 그 값이고, 없으면 `t_first − lag[first_stop]`입니다. lag는 같은 창에서 `t_origin`이 있는 운행으로 구한 중앙값이며 n≥5일 때만 씁니다.
4. **편 매칭.** 그날 적용된 시간표에서 추정 출발에 **가장 가까운 편** D를 고릅니다. `|D − est| ≤ 20분`일 때만 쓰고, 동률이면 이른 편입니다.
   - `offset = P − D`이고 `0 < offset < 150`분만 씁니다.
   - `drift = est − D`도 기록합니다. 시간표 정확도 경보에 씁니다.
5. **학습 대상일.** 다음을 **모두** 만족하는 날입니다.
   - `asof − 30일` 이후(오너 결정. 요일군 공통)
   - `history_epoch(route_id)`(§1.3) 이후
   - 특별편 배정일이 아님(`SpecialTimetableService.get_edition_for_date`)
   - 정책의 `exclude_dates`에 없음
   - 공휴일은 `read_effective_holidays`와 학습 기간 모든 달의 `offline_month_holidays`(`holiday_service.py:36`)로 채웁니다. `holiday_cache.json`에는 지금 202609와 202610만 있습니다[검증].
6. **셀 키** = `"daygroup|prev|slot|next"`. 요일군은 기본 {평일, 주말·공휴일}이고, 그 노선의 시간표가 토/일로 갈라지면 {평일, 토, 일·공휴일}로 자동 전환합니다(Q32). 이웃 편이 바뀌면 그 셀만 초기화됩니다.
7. **게이트 (셀 단위, 오너 결정)**

   | 항목 | 기준 |
   |---|---|
   | **기본 게이트** | 최근 30일, 같은 요일군·같은 편(셀) 표본 **n ≥ 4**(서로 다른 날짜 기준) |
   | 예측값 | 창 안 오프셋 중앙값(편 시각 + 중앙값) |
   | 표시 범위 | 창 안 오프셋 p20~p80. 폭이 12분을 넘으면 범위를 빼고 "약 HH:MM"만 |
   | 선택 품질 조건(기본 off, Q33) | 셀 IQR 상한, 최근 14일 절대오차 p80 상한 — 설정 파일로만 켬 |
   | 자동 중지(기본 on) | 방향 단위로 최근 14일 실측 대비 p80 > 8분이고 n≥20이면 방향 전체 폴백 |
   | 산출물 신선도 | `generated_at`이 7일을 넘으면 폴백 |

8. **비교 모델.** pass_clusters를 같은 잡에서 **그림자로만** 계산해 관리자 화면에 전진 오차를 나란히 보여 줍니다. D′보다 확실히 좋고 편 연결 문제를 해결할 수 있을 때만 교체를 검토합니다(Q17).
9. **쓰기.** `atomic_write_json`으로 씁니다. 결과가 비었으면 기존 파일을 덮어쓰지 않습니다(PM-008, 절대 규칙 2).
10. **실행.** `crawler/cache_refresh.py:51-63` `refresh_all`에서 시간표 재크롤 **다음에** 별도 try/except로 격리해 실행합니다. CLI는 `bushexa compute-offsets [--write] [--from-tsv] [--asof] [--report]`입니다.
    - 관리자 화면 동기 실행 버튼은 두지 않습니다. gunicorn sync 워커 2개에 timeout이 60초입니다(`cli.py:313,333`).

**파일** (둘 다 `.gitignore`에 추가. `data/`가 git 추적 체크아웃의 bind-mount이기 때문입니다. `docker/compose.yaml:31-32`)

| 파일 | 누가 씀 | 백업 | 내용 |
|---|---|---|---|
| `data/unist_estimates.json` | 야간 잡 | 제외(다시 만들 수 있음) | 방향 × 요일군 × 셀 통계, 게이트, drift, 구간 통계, eval |
| `data/prediction_settings.json` | 관리자(`locked_update_json` + `_audit`) | `_FLAT_FILES`에 추가 | `directions.<rid>.mode ∈ off/shadow/auto`, `rank_predicted`, `special_days="fallback"`, `exclude_dates`, `fallback_window_min`, live 임계값, gate 덮어쓰기 |

- 로더는 `(inode, mtime_ns, ctime_ns, size)` 서명을 씁니다(공지 구현과 같은 방식).
- 파일이 없거나 깨지면 예측 0건이고 경고는 한 번만 남깁니다. 공개 화면은 500을 내지 않습니다(ADR-013).
- 테스트 리셋용 autouse 픽스처를 둡니다(PM-010).

### 2.5 예측 판정 순서 (`predict_pass`, 편 단위)

다음을 위에서부터 검사해 처음 걸리는 사유로 폴백합니다.
1. `mode=="off"` → `mode_off`
2. 특별편 날 → `special_day`
3. 산출물 없음 → `no_model`
4. 산출물이 7일 넘게 오래됨 → `stale`
5. 오늘 < epoch → `epoch`
6. 셀 키 불일치 → `slot_changed`
7. `gate != ok` → `gate`
8. 방향이 자동 중지됨 → `suspended`
9. `mode=="shadow"` → `shadow`(관리자 화면에만 표시)
10. 자정을 넘김 → `overflow_midnight`
11. 모두 통과 → `Prediction`

### 2.6 live 처리

- 시각은 `T = fetched_at + eta`입니다.
  - `fetched_at`은 `CachedArrivalClient.last_fetched_at`이 돌려주는 **ISO 문자열**을 파싱합니다(`cached_arrival.py:49-52`). 실패하면 None으로 두고 오래된 것으로 처리합니다.
  - `now < fetched_at`(시계 오차)이면 age를 0으로 고정합니다.
- **신선도 3단계.**

  | age | 처리 |
  |---|---|
  | ≤ `rank_max_age` | 순위 대상. 단 ETA ≤ 30분일 때만 |
  | ≤ `show_max_age` | 순위 없이 '(N초 전 자료)'로 표시 |
  | 그보다 큼 | live 폐기 + 배너 |

  - `rank_max_age = max(150, 2.5 × 유효 주기)`초입니다. 유효 주기는 `arrival_status.json`의 최근 두 `cycle_started_at` 차이이고, 없으면 설정값을 씁니다.
  - `show_max_age` 기본값은 600초입니다.
- `T < now − 1분`이면 그 live 행은 버립니다(이미 통과).
- **편 매칭** (via 방향. D16을 via에서 해소)
  - 예측이 있으면: live T마다 `origin_time ≤ now`이고 `T ∈ [center−10, center+15]`인 예측 편 **하나만** live로 바꿉니다.
  - 예측이 없으면: 이미 떠난 폴백 편 가운데 가장 최근 **1건만** 숨깁니다. 앞으로 출발할 기점 편은 지우지 않습니다. 다른 차이기 때문입니다.
  - live의 `present_stop`이 기점 이름과 같으면(기점 대기 차량) 다음 upcoming 편 1건을 숨깁니다.
- **API 실패가 `[]`로 캐시되는 미해결 버그**(`[origin] docs/guide/api-usage.md` §4)가 있습니다. 이것을 "버스 없음"으로 해석하지 않습니다. X1 PR로 poller를 고칩니다. 실패한 사이클은 upsert를 생략해야 합니다.

### 2.7 화면별 표시 규칙

| 화면 | exact | live (신선) | live (오래됨) | predicted | origin_fallback |
|---|---|---|---|---|---|
| `/board` (HTMX 15초) | main, 순위 | main, 순위 (Q11) | main, 순위 없음, '(N초 전)' | main, 순위 없음, '약 HH:MM', 범위는 조건부 | **main 아래 별도 구역** "기점 출발 시각 · UNIST 시각이 아닙니다". 방향별 upcoming 최대 2건 + (live 없을 때) 최근 출발 1건 '이동 중일 수 있음' |
| `/lite` | 첫 번째 표 | 첫 번째 표 | 첫 번째 표 | 첫 번째 표, "약 " 접두 | **두 번째 표**, "[기점] " 접두. `<style>`·`<script>` 0 |
| `/unist` | "UNIST 출발" 그룹 | "UNIST 경유" 카드의 첫 줄 | 같음, '(N초 전)' | 같음, '약' | 경유 카드 둘째 줄 "{기점} HH:MM 출발(시간표)" |
| `/timetable` | 격자(from_unist만) | 표시 안 함 | — | 경유 패널 "덕하 17:30 출발 → 약 18:37 UNIST 통과" | 경유 패널 "덕하 17:30 출발(시간표)" |
| `/busno` | 시각 | — | — | 계획 P2 `hour_groups`(분 단위 Departure)가 생긴 뒤. `busno.py:55`의 `minutes: str`에는 분 단위 요소가 없음 | 방향 라벨 "513 · 덕하 출발 → 삼남(울산역) 방면" |

**공통 규칙**
- 경유 방향 행은 UNIST 출발 행과 같은 정렬에 섞지 않습니다. 예외는 exact·live·predicted처럼 **UNIST 시각**인 경우입니다.
- `origin_fallback`은 기점 구역 안에서만 정렬합니다.
- `is_last_bus = not main_rows and not origin_rows`로 바꿉니다(`board.py:275`). 그렇지 않으면 22:50 이후 "금일 운행 종료"와 513 기점 시각이 함께 보입니다. 근거: 평일 마지막 UNIST 출발은 713 22:45, 1115 22:50이고, 513 삼남 막차는 22:20, 덕하 막차는 22:00입니다.
- main의 빈 상태 문구는 "오늘 UNIST 출발 버스 운행이 끝났습니다"로 바꿉니다.
- 새 마크업은 `.dboard`, `data-flap`, `dboard-*` 클래스를 쓰지 않습니다. `splitflap.js:211-213`이 `#board-table .dboard`를 모두 토글하고, `:67`이 `.dboard [data-flap]`를 구동하기 때문입니다. 새 클래스는 `via-board`, `origin-board`입니다.
- 인라인 `style`과 `on*` 속성은 0개(계획 N-5)이고, 색은 CSS 토큰을 씁니다(계획 P1-5).
- `/unist` HTMX 자동 갱신이 첫 교체 후 멈추는 문제(`[origin] CLAUDE.md` 미해결 표)는 V2의 선행 과제입니다.

**2026-09-29 평일 17:47, 실시간 없음, 예측 없음일 때의 기대 렌더 (V1)**

```
[UNIST 출발·통과]
 17:55  713  명촌 (시내) 방면   UNIST 출발 · 시간표   FIRST
 17:55  743  명촌 (시내) 방면   UNIST 출발 · 시간표   FIRST
 18:10 1115  꽃바위 (시내) 방면 UNIST 출발 · 시간표   SECOND
 18:15  753  명촌 (시내) 방면   UNIST 출발 · 시간표
[기점 출발 시각 · UNIST 시각이 아닙니다]
 513 덕하 (시내) 방면    삼남 17:50 출발 · 삼남 18:30 출발
 513 삼남 (울산역) 방면  덕하 18:30 출발 · 덕하 19:00 출발  (이동 중일 수 있음 · 덕하 17:30 출발)
```

- 17:48:01 스냅샷이 신선하면 main에 `18:08 513 덕하(시내) 방면 · 실시간`과 `18:09 513 삼남(울산역) 방면 · 실시간`이 들어갑니다.
- 이때 기점 구역에서는 '이동 중일 수 있음' 행을 숨기고, 앞으로 출발할 기점 편은 그대로 둡니다.

### 2.8 문구 (ko / en)

- `[origin] i18n.py:99`의 `translate(key, lang, **kwargs)`와 `app.py:120`의 `t(key, **kw)` 치환을 씁니다. 지명에는 `| stop` 필터를 씁니다(`stop_names.seed.json`: 덕하→Deokha, 삼남신화→Samnamsinhwa).
- 계획 D15의 `place.*` 임시 키는 필요 없어졌습니다.
- 로컬 master의 `translate`는 치환을 지원하지 않습니다(`[HEAD] i18n.py:81-92`). 이것도 origin/master 기준으로 작업해야 하는 이유입니다.

| 키 | ko | en |
|---|---|---|
| `board.section.unist` | UNIST 출발·통과 | Departing / passing UNIST |
| `board.origin.title` | 기점 출발 시각 · UNIST 시각이 아닙니다 | Departures from first stop · not UNIST times |
| `board.origin.hint` | UNIST에 오는 시각은 실시간 정보나 노선별 시간표를 확인하세요 | For times at UNIST, see live info or the route timetable |
| `board.main.service_over` | 오늘 UNIST 출발 버스 운행이 끝났습니다 | No more departures from UNIST today |
| `basis.unist_exact` | UNIST 출발 · 시간표 | Departs UNIST · scheduled |
| `basis.unist_live` | 실시간 · {min}분 후 UNIST 도착 · 현재 {stop} 부근 | Live · at UNIST in {min} min · now near {stop} |
| `basis.unist_live_stale` | 실시간({age}초 전 자료) | Live (data {age}s old) |
| `basis.unist_predicted` | 약 {time} UNIST 통과 예상 | approx. {time} at UNIST |
| `basis.unist_predicted.range` | ({lo}~{hi}) | ({lo}–{hi}) |
| `basis.unist_predicted.from` | {origin} {origin_time} 출발 편 | the {origin_time} departure from {origin} |
| `basis.origin_departs` | {origin} {time} 출발(시간표) | Leaves {origin} {time} (timetable) |
| `basis.origin_recent` | {origin} {time} 출발 · 이동 중일 수 있음 | Left {origin} {time} · may be on the way |
| `via.legend` | '약'은 과거 운행 기록으로 추정한 시각이며 실제와 다를 수 있습니다. | 'approx.' times are estimates from past trips and may differ. |
| `via.service_over` | 오늘 남은 {busno}번({terminal}) 운행이 없습니다 | No more {busno} ({terminal}) today |
| `board.live_stale_banner` | 실시간 정보가 {min}분째 갱신되지 않아 시간표로 표시합니다 | Live data is {min} min old; showing scheduled times |
| `lite.prefix.approx` / `lite.prefix.origin` | "약 " / "[기점] " | "~" / "[Origin] " |

**금지**
- 경유 항목에 "출발 예정"만 쓰는 것(`unist_board.py:95`의 현행 문구)
- 예측이나 기점 시각에 "N분 후"를 붙이는 것
- 도메인 코드가 한국어 문장을 새로 만드는 것. 기존 `present`는 호환용으로만 남깁니다(`board.py:163,204`, `unist_board.py:82,95,120`).

### 2.9 상태와 폴백 (요약)

| 상황 | 경유 표시 | main |
|---|---|---|
| 예측 정상(게이트, 전진 검증, 모드 auto, 셀 키, 신선도 모두 통과) | 약 HH:MM(범위는 조건부) | 영향 없음 |
| 일부 편만 예측 | 편별로 예측 또는 폴백, 범례 1회 | 영향 없음 |
| 산출물 없음·파손·오래됨, 모드 off/shadow, 특별편 날, epoch 이전, 자동 중지 | 폴백 | 영향 없음 |
| 셀 키 불일치(재크롤, 관리자 편집, git pull) | 해당 편만 폴백 | 영향 없음 |
| live 오래됨 / 없음 | 순위 없는 live / 폴백 | 영향 없음 |
| 시간표 없음, live도 없음 | "오늘 {busno}번 시간표 정보가 없습니다" | 영향 없음 |
| 자정을 넘기는 예측 | 폴백. 현재 경유 방향에는 해당 편이 없고, to_unist 713 명촌 22:55편만 해당(V5) | — |

---

## 3. 방향 일반화

### 3.1 분류 결과 [검증: `constants.py:35-57`를 `.venv` python으로 순회]

추적 정류장 목록만으로 10개 방향이 **예외 없이** 분류됩니다. idx는 추적 목록 기준 0부터이고, BIS 순번이 아닙니다.

| route_id | 번호 | 기점→방면 | relation | 기준 정류소 | 그 밖의 UNIST 권역 |
|---|---|---|---|---|---|
| 196000421 | 513 | 덕하→삼남(울산역) | via_unist | 196040234@7 | 232@6, 231@8 |
| 196000422 | 513 | 삼남→덕하(시내) | via_unist | 196040234@3 | 232@2, 231@4 |
| 195000178 / 195000216 / 195000222 | 713/743/753 | UNIST→명촌 | from_unist | 196040233@0 | 231@1 |
| 194000107 | 1115 | UNIST→꽃바위 | from_unist | 196040233@0 | — |
| 195000177 | 713 | 명촌→UNIST | to_unist | 999000145@11 | 232@10 |
| 195000215 / 195000221 | 743/753 | 명촌→UNIST | to_unist | 999000145@12 | 232@11 |
| 194000106 | 1115 | 꽃바위→UNIST | to_unist | 999000145@12 | — |

### 3.2 모델 (G0)

설계안 두 개가 달랐습니다. via-prediction은 계획 P1-1의 `timetable_view.DirectionSpec` 확장을, direction-generalization은 `domain/directions.py` 신설을 제안했습니다. 정의가 두 벌이 되면 계획 N-10(표면 간 단일 규칙)에 어긋납니다. 그래서 다음과 같이 합칩니다[추론].
- **정의는 `bushexa/domain/directions.py` 한 곳**에 둡니다. 소비처가 시간표 화면만이 아니라 `/board`와 `/unist`도 있기 때문입니다.
- P1-1의 `timetable_view.py`는 이것을 import해 씁니다.
- 계획 6.1의 용어는 이렇게 바꿉니다: `departs/passes/arrives` → `from/via/to_unist`, `'unist'/'estimated'/'origin'` → `unist_exact/unist_predicted/origin_fallback`, 그리고 `unist_live`를 추가합니다.

```python
# bushexa/data/constants.py (추가형. 노선 사실은 여기만. 절대 규칙 6)
UNIST_ORIGIN_STOP_ID = "196040233"; UNIST_TERMINUS_STOP_ID = "999000145"
UNIST_AREA_STOP_IDS = frozenset({"196040233", "196040234", "196040232", "196040231", "999000145"})
DIRECTION_META: dict[str, dict] = {           # 파생 규칙으로 정할 수 없는 것만. slug는 필수
    "196000421": {"slug": "513-samnam", "origin_label": "덕하"},
    "196000422": {"slug": "513-deokha", "origin_label": "삼남"},     # '삼남신화' 여부는 Q14
    "195000178": {"slug": "713-out"}, "195000177": {"slug": "713-in"},
    "195000216": {"slug": "743-out"}, "195000215": {"slug": "743-in"},
    "195000222": {"slug": "753-out"}, "195000221": {"slug": "753-in"},
    "194000107": {"slug": "1115-out"}, "194000106": {"slug": "1115-in"},
}   # 허용 키: slug, origin_label, relation(파생값 덮어쓰기), ref_stop_id, enabled
```

```python
# bushexa/domain/directions.py (순수, I/O 없음)
Relation  = Literal["from_unist", "via_unist", "to_unist", "none"]
TimeBasis = Literal["unist_exact", "unist_live", "unist_predicted", "origin_fallback"]

@dataclass(frozen=True)
class DirectionSpec:
    route_id: str; busno: str; relation: Relation
    origin_key: str          # ROUTEID[2]. 시간표 조회 키(data/timetable.py:81이 split()[0] 적용)
    origin_label: str        # 표시용(기본값 origin_key)
    terminal_label: str; terminal_key: str     # VIA_STOPS·via override 키
    ref_stop_id: str | None  # from=233, via=234, to=145 (DIRECTION_META로 덮어쓰기 가능)
    live_stop_id: str | None # ref가 SERACH_STOPS에 있으면 ref, 없으면 None
    ref_stop_index: int | None   # 추적 목록 인덱스. 보간·거리 계산 금지
    upstream: tuple[str, ...]    # ref 이전 추적 정류장(E4)
    slug: str; display_order: int; enabled: bool = True
    history_valid_from: date | None = None    # route_changes.history_epoch(route_id)

def derive_relation(stop_ids) -> Relation:
    # 순서가 중요: [0]==233 → from, [-1]==145 → to, 234 in [1:-1] → via, 그 밖 → none
    # (to 방향에도 232가 중간에 있으므로 to를 via보다 먼저 판정)
def derive_specs(routeid=ROUTEID, meta=DIRECTION_META, search_stops=SERACH_STOPS) -> tuple[DirectionSpec, ...]
SPECS = derive_specs()                        # 입력이 모두 상수라 import 시 한 번 계산. 워커 사이 불일치 없음
def spec_by_route(route_id) -> DirectionSpec | None
def specs_for(surface) -> tuple[DirectionSpec, ...]
```

`board._UNIST_BUSNOS`(`board.py:23-26`)는 `specs_for("board")`에서 파생한 **같은 값으로 유지**합니다. `tests/domain/test_board_cleanup.py:57`이 이 심볼을 import하기 때문입니다. 삭제는 마지막 단계에서 합니다.

### 3.3 정책 매트릭스 (`domain/directions.py`의 `POLICY`, 단일 소스)

| relation × basis | 시각의 의미 | /board·/lite | /unist | /timetable | /busno | 순위 |
|---|---|---|---|---|---|---|
| from × unist_exact | UNIST 기점 출발 | main | "출발" 그룹 | 격자 | 시각 | 항상 |
| from × unist_live | (현재 발생하지 않음. 233은 조회하지 않음) | main | 출발 | — | — | 신선할 때 |
| via × unist_live | 234 도착 ETA | main | 경유 카드 | — | — | **신선할 때**(Q11) |
| via × unist_predicted | 편별 통과 추정 | main '약' | 경유 카드 '약' | 경유 패널 | P2 이후 | 설정(기본 없음) |
| via × origin_fallback | 기점 출발 | **기점 구역** | 경유 카드 둘째 줄 | 경유 패널 | 방향 라벨 | **없음** |
| to × unist_predicted | UNIST 도착 추정 | — | — | in 뷰(D6) | P2 이후 | 없음 |
| to × origin_fallback | 기점 출발 | — | — | in 뷰(D6) | 방향 라벨 | 없음 |
| none × * | UNIST와 무관 | — | — | — | 시각 | 없음 |

- `rank_eligible(row)`는 `POLICY.rank`와 `row.live_confident`, 설정 `rank_predicted`로만 판정합니다.
- 코드에 `"513"` 리터럴 분기는 없습니다. 이것을 정책 테스트로 막습니다(T-G6).

### 3.4 소비처와 리팩터 경로 (도메인 파일은 세 기준에서 줄번호 동일)

| 위치 | 변경 | PR |
|---|---|---|
| `domain/board.py:23-26` `_UNIST_BUSNOS` | spec에서 파생(값 동일) | G0 |
| `domain/board.py:91-118` `BoardRow`·`BoardSnapshot` | 기본값 있는 필드 추가: `route_id`, `relation`, `basis`, `origin_label`, `origin_time`, `est_lo/hi`, `live_age_s`, `live_confident`, `is_recent` / `origin_rows`, `live_stale` | V1 |
| `domain/board.py:131-169` `_build_timetable_rows` | from은 main, via는 `resolve_unist_times` 결과를 main과 origin으로 나눔 | V1 |
| `domain/board.py:172-210` `_build_live_rows` | `fetched_at + eta`, age 3단계, `basis=unist_live` | V1 |
| `domain/board.py:257-263` | from은 기존 규칙(`test_live_overrides_timetable` 보존), via는 §2.6 편 매칭 | V1 |
| `domain/board.py:275, 291-325` | `is_last_bus`는 origin 포함. 순위는 `rank_eligible` 행만. `merge_live_rows` 시그니처는 유지 | V1 |
| `web/routes/board.py:29-63` `_build_snapshot` | `live_fetched_at`, `special_edition_for`, settings, estimates 전달(`/lite`는 `board_lite.py:39`에서 재사용하므로 자동 반영) | V1 (estimates는 E3) |
| `services/board_support.py` | `special_edition_for(config, today)`, `live_fetched_at(client, stop_id)`, `timetable_sig(...)` 추가 | V1 |
| `templates/partial/board_table.html:7-59`, `board_lite.html:20-36` | 기점 구역과 두 번째 표, 머리글 `t()` | V1 |
| `domain/unist_board.py:51-56, 59-98, 182-218` | spec 기반 분류, `[:2]+[:4]` 제거, `via_cards`/`from_cards` 추가(`cards`는 호환용으로 이어 붙임) | V2 |
| `templates/unist_partial.html:8-21` | 두 그룹. 둘 다 비면 `cards`로 폴백(목 테스트 호환) | V2 |
| `domain/unist_timetable.py:78-93` | 격자는 from만. via는 `via_sections`로, **같은 PR에서** 추가 | V2 |
| `domain/busno.py:93-113`, `busno.html` | `direction_options`, 레거시 `dep` 호환 | V2 |
| `web/routes/board.py:26,73` `_STOP_ID`, `unist_board.py:167` | spec의 `live_stop_id` 집합에 속하는지 불변식으로 검사 | G0 |
| 변경 없음 | `data/timetable.py:104-116`, `crawler/*`, `domain/stops.py`, `domain/running.py`, `api_clients/composite_location.py`, admin via 편집기 | — |

리팩터 순서 원칙: 관계 판정 세 벌을 한 PR에서 하나만 바꾸면 화면끼리 분류가 어긋납니다. 그래서 **G0에서 동치성 테스트를 먼저** 넣고(현재 세 규칙의 결과 = spec 결과), V1과 V2에서 소비처를 옮깁니다.

### 3.5 새 노선이나 경로 변경이 생길 때 하는 일

1. `ROUTEID`에 한 줄, `DIRECTION_META`에 slug 한 줄을 추가합니다. 코드 PR이고 `change-playbooks` §1을 따릅니다.
2. 경로 변경이면 `ROUTE_CHANGES`에 한 줄을 넣고 `source`를 적습니다. 공지 seed에 같은 id와 날짜를 넣습니다.
3. 불변식 테스트가 CI에서 검사합니다. 화면 코드는 바꾸지 않습니다.

### 3.6 불변식과 테스트

**신규 파일:** `tests/domain/test_directions.py`, `test_direction_policy.py`, `test_unist_time.py`, `test_board_basis.py`, `tests/services/test_unist_estimates.py`, `test_prediction_settings.py`, `tests/web/test_board_origin_section.py`, `tests/invariants/test_direction_coverage.py`. hypothesis는 의존성에 없으므로 `parametrize` 격자로 대신합니다.

| ID | 테스트 | 기대 |
|---|---|---|
| T-G1 | 분류 고정 | §3.1의 10행을 parametrize(relation, ref, idx, origin_key, terminal_key) |
| T-G2 | 판정 순서 | `[X, 232, 234, 145]` → to_unist, `[X, 232, 234, Y]` → via_unist |
| T-G3 | none 금지 | `DIRECTION_META.relation="none"`을 명시하지 않은 none은 0건 |
| T-G4 | slug | 모든 ROUTEID 키에 있고, `^[a-z0-9-]{1,40}$`를 만족하며, 유일함. META에 ROUTEID에 없는 키가 없음 |
| T-G5 | 조회 정류소 정합 | via의 `live_stop_id ⊆ SERACH_STOPS`, `_STOP_ID`가 그 집합에 속함 |
| T-G6 | 번호 분기 금지 | `bushexa/domain/*.py`, `web/routes/*.py`에서 `== "513"`, `in ("513"` 같은 패턴 0건 |
| T-G7 | 합성 via 노선 | `999000001 = [x1, 232, 234, 231, x2]`를 주입하면 코드를 고치지 않아도 `/board` 기점 구역, `/unist` 경유 카드, `/timetable` 경유 패널, `/busno` 옵션에 나옴 |
| T-G8 | 동치성(G0) | 현재 `_UNIST_BUSNOS`, `unist_board` 분류, `deps[0]` 결과가 spec에서 파생한 값과 같음 |
| T-B1 | 17:47 회귀 | 실시간 없음. FIRST는 {713, 743}@17:55, SECOND는 1115@18:10. main에 origin_fallback 0건. `origin_rows`에 삼남 17:50, 그리고 덕하 17:30 `is_recent` |
| T-B2 | 불변식 격자 | 기점 오프셋 {-40, -10, 0, +1, +3, +20} × from 출발 {+1, +8, +30} × live {없음, age 30, 300, 900} × 예측 {없음, 통과, 탈락}. (a) 순위가 있는 행은 모두 `rank_eligible` (b) main에 origin_fallback 없음 (c) main 오름차순 (d) predicted에 순위 없음 (e) basis 기본값인 행은 from/exact뿐 |
| T-B3 | live 보정 | `fetched_at` 17:48:01, ETA 1237초, now 17:49 → "18:08". now 17:53 → 순위 없음, stale 라벨. now 17:59 → live 0건, `live_stale` |
| T-B4 | 지난 live 폐기 | fetched 17:30 + 300초, now 17:37 → 제외 |
| T-B5 | is_last_bus | 22:51에 origin_rows가 있으면 False, 23:01이면 True |
| T-B6 | via 과잉 대체 해소 | 422 live가 있어도 삼남 18:30은 남고, 713 from live는 기존처럼 대체 |
| T-E1~E8 | 예측 | 가장 가까운 편 매칭(12:00/12:30 편, 실제 출발 12:20 → 12:30), 25분 차이 제외, lag 추정, 전진 실패 `fail_fwd`, 쌍봉 `fail_iqr`, 셀 키 국소 변경, `holiday_backfill`(9/24), 특별편, epoch(743 10-03), 자동 중지, 파손 로더 |
| T-W1 | `/partial/board` | 기점 구역이 `.dboard` 밖에 있고 `data-flap` 0. `?lang=en`에 "Departures from first stop"과 "Samnam" |
| T-W2 | `/lite` | 표 2개, 경유 표에 `*`/`+` 없음, `<style` 0(**신규 단언**. `test_board_lite.py:59`는 script, htmx, 폰트만 단언함) |
| T-W3 | `/timetable?day=0` | 격자에 `.bus-513` 0개, 경유 패널에 두 방향 |

**개정하는 기존 단언 [검증: 파일 위치]**

| 테스트 | 조치 |
|---|---|
| `tests/domain/test_board.py:166-182` `test_only_unist_departures_shown` | '덕하 (시내) 방면'을 `rows + origin_rows`에서 찾도록 바꿈 |
| `tests/domain/test_board.py:74-101` `test_rows_sorted` | 설계안 두 개의 판단이 다릅니다(fixture가 비어 1행이 된다 vs 통과한다). V1 PR에서 실행해 확인하고, 실패하면 fixture에 743 시각을 추가하되 정렬 단언은 유지 |
| `tests/domain/test_board_cleanup.py:57` | 심볼을 유지하므로 통과 |
| `tests/domain/test_unist_board.py:66-70` `test_six_cards` | `cards` 호환 필드로 통과. `via_cards`/`from_cards` 단언 추가 |
| `tests/web/test_unist_board_route.py:61`, `test_routes_smoke.py:81` | 템플릿 폴백으로 통과 |
| `tests/domain/test_unist_timetable.py:47-49` | `deps[0]` 전제 주석 갱신, 격자 513 부재 단언 추가 |
| `tests/web/test_notices_web.py:74-78` | N0-a에서 개정(§1.6) |
| `tests/web/test_route_diagram.py:115-122` (`[origin]`) | 레지스트리 동치 단언 추가. R0 이후에는 `[HEAD]` 버전과 병합 |

---

## 4. 수정된 실행 순서

### 4.1 의존 그래프

```
N0-a ─► N0-b ─► N0-c(10/2 배포) ─► N0-v(10/3 00:05)
                       │
                       ├─► R0(오너 브랜치 rebase, 레지스트리 사용) ─► N1
                       │
X1(poller) ─────────────┤
                       ▼
G0 ─► V1(/board·/lite) ─► V2(/unist·/timetable·/busno; /unist 갱신 중단 수정 선행)
 │                                  │
 └► E1(설정) ─► E2(산출·그림자) ──(오너 게이트: 30일 창, 셀당 4일)──► E3(auto 전환, 설정만)
                     └► E4(운행 중 계층, 선택) ─► V5(to_unist, D6)
```

### 4.2 PR 슬라이스

| PR | 내용 | 크기 | 선행 | 시점 | 계획 대비 |
|---|---|---|---|---|---|
| **N0-a** | 공지 병합과 보강(§1.6) | S(보강) | Q1, Q3, Q4, Q5 | 9/30 | P4-3 흡수 |
| **N0-b** | 레지스트리, 날짜 문구 전환, 1115 사실 반영, 계약 테스트 | S~M | N0-a, Q7, Q8 | 10/1 | P0-9 대체 |
| **N0-c** | 코드만 교체해 배포 | 운영 | Q2, Q9 | 10/2 오전 | 신규 |
| R0 | `feat/route-map-geo-ab` rebase(충돌 14구간/7파일). `DIAGRAM_DELTAS`로 전환, A/B 계측 분리 여부(Q24) | M | N0-c | 10/6 주 | P0-0a |
| X1 | poller가 오류일 때 upsert 생략 | XS | — | V1 전 | 신규 |
| N1 | 공지 `change` 필드, 상한, 위치, stops 폴링, changelog 감사·백업, 배포 스크립트 이관 | S~M | N0-c | 10/6~10/16 | P4-3 잔여 |
| **G0** | constants(`DIRECTION_META`, UNIST 상수), `domain/directions.py`, T-G1~G8 | S | R0 | 10/6 주 | P1-1 일부를 앞당김 |
| **V1** | `/board`·`/lite` 분리, live 보정과 신선도, `is_last_bus`, 문구, CSS, 개정 테스트, changelog 항목 | M | G0, X1 권장, Q11·Q15·Q20 | 10/12 주 | P2-6b, D5, D16(via) |
| V2 | `/unist`(갱신 중단 수정 포함), `/timetable` 경유 패널, `/busno` 방향 옵션 | M | V1 | V1 다음 | P2-1, P2-6a, P0-5 제거 |
| E1 | `prediction_settings.json`(seed, 로더, 관리자 토글, `_audit`, 백업) | S~M | G0 | V1과 병행 | P4-2 일부 |
| E2 | 산출 잡, CLI, 관리자 읽기 전용 표(게이트, drift, 전진 오차, pass_clusters 비교), `.gitignore` | M | E1, Q18 | V1 직후(공개 영향 없음) | P4-0, P4-1 |
| E3 | 방향별 `auto` 전환(설정만) | XS | E2 그림자 + 오너 게이트(셀당 4일) 충족 | 운영 이력이 이어져 있으면 10월 중순[추론, Q18] | P4-2 |
| E4 | 운행 중 계층(govtrack 위치 또는 상류 ETA + 구간 중앙값) | M | E2 segments | 선택(Q17) | 신규 |
| V5 | to_unist 노출(자정 처리 포함), 743·1115 epoch | S~M | D6 | 이후 | P2-2 |
| 정리 | `_UNIST_BUSNOS`·`UNISTBUS`·`UNIST_STR`(소비처 없음, `constants.py:26-29,159-165`) 삭제, `/info` 513 정적 경고와 Tips 정리 | S | V2, R0 | 이후 | P5-2 일부 |

**단계표 변경 요약**
- Phase 0: P0-9 → N0로 교체합니다(유일한 기한 항목). P0-0a → R0입니다.
- Phase 1: P1-1 가운데 방향 부분 → G0입니다.
- Phase 2: P2-1, P2-6a, P2-6b → V1과 V2입니다. P2-2 → V5입니다.
- Phase 4: P4-0~P4-2 → E1~E3입니다. P4-3 → N0-a와 N1입니다. P4-4와 P4-5는 그대로입니다.
- **10/3 전에 반드시 나가야 하는 경유·방향 슬라이스는 없습니다.**

---

## 5. 추가로 정리가 필요한 사항

**[긴급]** 표시는 10/2 배포 전에 답이 필요한 항목입니다.

| # | 질문 | 선택지 | 권장 | 막는 것 |
|---|---|---|---|---|
| ~~Q1~~ | ✅ **해소.** 공지 구현은 오너 지시로 만든 것이고, 커밋·배포는 오너가 수동으로 합니다. | — | — | — |
| **Q2 [긴급]** | 운영 서버는 지금 어떤 커밋을 돌리고 있고, 누가 어떻게 배포하나요? `build-bus-tar.sh`는 이 체크아웃의 작업 트리(지금은 A/B 브랜치, 로컬 master 기반, PM-016 마스킹 없음)와 `data/`를 통째로 묶습니다(S6) | (a) 깨끗한 origin/master 체크아웃에서 `bushexa/`만 교체하고 web 재시작 / (b) 번들 스크립트 / (c) 서버에서 git pull | (a). (b)는 개발용 `data/`(시간표, changelog)가 운영 데이터를 덮어쓸 위험이 있습니다. (c)는 git이 추적하는 `data/changelog.json`, `data/timetable/*.json`과 충돌할 수 있습니다 | N0-c |
| **Q3 [긴급]** | 1115 공지를 게시판(`/board`, `/unist`, `/lite`, `/timetable`, `/busno`)에도 띄울까요? 사실관계는 오너 커밋이 공지 2272로 확인했다고 적었습니다(`[HEAD] info.html:73`, `route_diagram.py:159`). §1.5 문구로 확정해 주세요 | (a) seed에 추가 / (b) `/info`만 | (a). 10/3 이후 현대자동차로 가는 승객에게 영향이 가장 큰 변경입니다 | N0-a seed |
| Q4 | ✅ **(a)로 적용**(K1). 다른 문구를 원하면 `/admin/notices`나 seed에서 바꾸면 됩니다. | — | — | — |
| **Q5 [긴급]** | 공지 종료일(`show_until`)을 언제로 할까요? | 10/31 / 10/17 / 무기한 | 10/31. 연휴와 한글날 뒤로 학기 중 노출 기간을 확보합니다 | N0-a seed |
| **Q6 [긴급]** | 오너 브랜치(`bf5d807`: SVG 지도, A/B 카운터, 공개 `POST /info/event`, `route_map.js` sendBeacon)를 10/3 전 배포에서 뺄까요? | (a) 빼고 1115 사실만 N0-b로 옮김 / (b) rebase해 함께 배포 | (a). 충돌이 14구간이고, 새 공개 쓰기 엔드포인트와 JS가 계획 N-4와 충돌합니다 | N0-b 범위, R0 |
| **Q7 [긴급]** | 10/3 전 `/board` 1115 경유 열을 두 구간 병기("현대자동차(10/2까지) - 아산로(10/3부터)")로 할까요? | (a) 병기 / (b) 10/2까지는 옛 경로만 | (a). 743 방식과 같고 영어도 번역됩니다 | N0-b `VIA_STOPS_DATED` |
| **Q8 [긴급]** | 시행일 단일 원천을 어디에 둘까요? | (a) `constants.ROUTE_CHANGES`(코드) + `domain/route_changes.py` 로직, 공지 날짜는 테스트로 묶음 / (b) 코드 기본값 + `data/route_changes.json` 덮어쓰기 / (c) 공지 `effective_from`이 원천 | (a). 절대 규칙 6에 맞고, 노선 형상(코드)과 날짜가 함께 움직입니다. 시행이 미뤄지면 코드를 배포해야 한다는 비용은 감수합니다 | N0-b |
| **Q9 [긴급, 확인 작업]** | 운영 `data/via_overrides.json`에 743·1115 날짜 문구가 있나요? 운영 `data/notices.json`이 이미 있나요? | — | N0-c 전에 grep합니다. 있으면 관리자 화면에서 정리합니다 | N0-c |
| Q10 | 10/3 인가에 배차 변경이나 BIS route_id 재발급이 따라오나요? | (a) 10/3 아침 재크롤과 route_id 점검 / (b) 변동 없음 확인 | (a). N0-v 체크리스트에 포함합니다 | 게시판 시각, E2 epoch |
| Q11 | 신선한 513 live(UNIST 실제 도착 ETA)를 main 순위(FIRST/SECOND)에 넣을까요? | (a) 경유 방향은 기준과 관계없이 모두 별도 구역 / (b) 신선한 live만 main 순위에 넣고, 예측은 main에 순위 없이, 폴백은 기점 구역 | (b). live는 실제 UNIST 시각이라 오너가 말한 "기점 출발 우선"과 성격이 다르고, 현재 동작에서 후퇴하지 않습니다. 반대 근거: 규칙은 (a)가 더 단순합니다 | V1 레이아웃, T-B1·T-B3 |
| Q12 | 예측에 순위를 줄까요? | (a) 순위 없이 '약'만 / (b) `rank_predicted=true` | (a)를 기본으로 하고 설정으로 바꿀 수 있게 합니다. 전진 검증 p90이 6.5~7.4분이라 10분 간격 편성에서 FIRST가 틀릴 수 있습니다 | V1 기본값 |
| Q13 | 경유 방향의 기준 정류소를 196040234(울산과학기술원 경유)로 확정할까요? 513은 232와 231도 지납니다 | 234 / 232 / 231 / 방향별 META | 234. 실시간 조회 정류소(`SERACH_STOPS[0]`)이고 기록 표본이 가장 많습니다. 탑승 위치 안내는 D7에서 따로 정합니다 | V1 문구, E2 대상 |
| Q14 | 513 기점 표시 이름을 '삼남신화'로 할까요? ROUTEID와 시간표 키는 '삼남'입니다(`constants.py:39`) | (a) `origin_label="삼남신화"`, 덕하 유지 / (b) ROUTEID 값 그대로 | (a). 시간표 키와 분리합니다. 실제 기점 정류소명은 BIS로 한 번 확인합니다 | G0 META 값(나중에 바꾸기 쉬움) |
| Q15 | 이미 기점을 떠났지만 UNIST에 아직 오지 않았을 수 있는 편을 1건 보여 줄까요? 창은 몇 분으로 할까요? | (a) live가 없는 방향만 1건. 창은 정책 → 산출 p90 → 기본값 / (b) 앞으로 출발할 편만(현행) | (a). 창 기본값은 덕하 75분, 삼남 45분입니다(기점→UNIST 중앙값 63분, 42분 기준) | V1 |
| Q16 | 예측 공개 방식을 어떻게 할까요? | (a) 방향별 off/shadow/auto 토글, auto 이후에는 셀 게이트(오너 규칙)를 매일 자동 판정 / (b) 셀 키마다 관리자 승인 / (c) 영구 off | (a). 오너가 요청한 유연성과 즉시 off(재시작 불필요), `_audit`를 함께 충족합니다 | E1 스키마, E3 |
| Q17 (개정) | 게이트는 오너 규칙(30일·같은 요일군·편당 4건)으로 **확정**. 남은 질문은 **모델과 편 매칭 방식**입니다. 운행 중 계층(E4, 실시간 위치 + 구간 소요)을 이력 예측(E3)보다 먼저 공개할까요? | (a) D′(추정 실제 출발에 가장 가까운 편 ≤20분) + 편별 오프셋, 군집 모델은 그림자 비교 / (b) 군집 모델 기본 / (c) 시간표 편 그대로 매칭 | (a). (c)는 513 덕하발 p80 24.6분으로 부적합(§2.3 시뮬). 오너 우선순위(실시간 우선)에 맞춰 **E4를 E3보다 먼저** 공개하는 것을 권장합니다 | E2 산출 규칙, E3·E4 순서 |
| Q18 | 운영 `bus_timelog`가 6/2 이후 끊김 없이 쌓이고 있나요? 읽기 전용 export를 받을 수 있나요? 5/17 이후 기록량 감소(하루 약 3,600 → 1,000~2,000행)의 원인은 무엇인가요? | (a) export로 9월 자료 재계산 / (b) 지금 수집 시작, 10/6부터 누적 / (c) 예측 보류 | (a)가 가능하면 (a), 아니면 (b). V1은 어느 쪽이든 진행합니다 | E2 착수, E3 시점 |
| Q19 | 현재(9월) 513·1115 시간표 JSON이 실제 배차와 맞나요? 봄 관측에서 일치율은 18~40%였고, 1115는 `unist_exact`로 FIRST를 받습니다 | (a) 재크롤 후 관측과 대조 / (b) BIS 웹과 운수사 공지를 수동 대조 / (c) E2 drift 지표로 감시만 | (a)+(c). 계속 맞지 않으면 `DIRECTION_META`에 `timetable_trust` 필드를 추가해 순위에서 빼는 방안을 검토합니다 | 폴백 시각의 신뢰도, 1115 순위 |
| Q20 | live 신선도 기준을 `max(150, 2.5×주기)`초 / 600초로 할까요? main의 UNIST 출발 live에도 같은 보정(`fetched_at + eta`)과 기준을 적용할까요? | 적용 / via에만 | 적용. 같은 화면 안에서 계산식이 다르면 안 됩니다 | V1 |
| Q21 | poller가 API 실패를 `[]`로 캐시하는 버그를 V1 전에 고칠까요? | (a) X1 별도 PR / (b) V1과 함께 / (c) 보류 | (a). 이 버그가 있으면 age 판정이 소용없습니다(절대 규칙 2) | V1 `live_stale` 정확도 |
| Q22 | to_unist(UNIST 도착 방향)를 `/timetable`에 넣을까요?(D6) | (a) in 뷰에 기점 시각 + 게이트 통과 시 예측 / (b) `/busno`만 | (a). 엔진은 G0부터 일반화되어 있어 노출만 결정하면 됩니다 | V5 |
| Q23 | 10/3 이후 ROUTEID 추적 정류장을 갱신할까요? 1115 추적 목록의 195030615/616은 더 이상 지나지 않고, 743 목록에는 범서중학교앞이 없습니다. 743 새 경로가 천상(196020808/807)을 계속 지나는지, 시내 방면 범서중 ID가 무엇인지도 확인해야 합니다 | (a) 공식 목록 대조 후 N1에서 갱신(워커 재시작) / (b) 운행 후 BIS 노선 API로 확인 | (a) 또는 (b). 10/3 전에 서두르지 않습니다. 목록을 바꾸면 `/running` 열이 즉시 바뀝니다(`running.py:135-139`) | N1, 743·1115 예측 재개 |
| Q24 | A/B 계측(공개 POST, flock 파일 쓰기, sendBeacon JS)을 계획 N-4의 예외로 허용할까요? | 허용(레이트 제한 추가) / 서버 로그 기반 집계로 대체 | 10/3 뒤 R0에서 결정합니다. 허용한다면 남용 방지와 CSRF 없는 쓰기의 위험 평가를 문서로 남깁니다 | R0 |
| Q25 | 공지 위치와 개수를 어떻게 할까요? 지금은 `/board` 제목 위에 나오고, `/stops`에는 60초 폴링이 새로 생깁니다 | (a) `/board`에서 block 재정의로 제목 아래, stops는 폴링 제외, 상한 3 / (b) 현행 | N0에서는 (b)(공지 두 건), N1에서 (a) | N1 |
| Q26 | git이 추적하는 운영 데이터(`data/changelog.json`, `data/timetable/*.json`, `data/logs.tsv`, `git ls-files data`)와 새 사이드카 파일을 어떻게 관리할까요? | (a) 새 파일은 `.gitignore`, 기존 추적 해제는 별도 논의, 배포 스크립트를 저장소로 이관 / (b) 새 파일만 | (a). git pull이 재크롤 결과를 되돌리면 셀 키가 흔들려 예측이 멈춥니다 | E2 배포, N1 |
| Q27 | live `notices.json`이 깨졌을 때 seed로 폴백하는 현재 동작이 의도한 것인가요?(`notices.py:436-441`) | 유지 / 0건 / 마지막 정상값 | 유지. 관리자 health 경고로 드러납니다. 문서화만 합니다 | 없음 |
| Q28 | 영어 문구가 없는 공지는 어떻게 할까요? | ko 폴백(현행) / 영어 모드에서 숨김 / en 필수 | ko 폴백 + 관리자 경고 | N1 |
| Q29 | 특별편 날에는 예측을 끌까요? | 전부 폴백 / 편 목록이 같으면 유지 | 전부 폴백. 시험이나 행사로 교통 상황이 평소와 다를 가능성이 큽니다 | E2 |
| Q30 | 로컬 `logs/bushexa-arrival.log`에 도착정보 serviceKey가 평문으로 남아 있습니다(urllib3 DEBUG). origin/master의 PM-016(28093a3)이 기록을 막았지만 이미 기록된 로그와 운영 로그는 남아 있습니다. 키를 교체하고 로그를 정리할까요? | 교체+정리 / 정리만 | 교체+정리. 운영이 PM-016 이전 버전이면 지금도 기록 중일 수 있습니다(Q2와 연동) | 보안(일정 무관) |
| **Q32 (신규)** | 예측 요일군을 {평일, 주말·공휴일} 둘로 묶을까요? 토요일 단독은 30일에 4~5회뿐이라 오너 게이트(4건)를 거의 못 채웁니다 | (a) 시간표가 토=일이면 묶고, 갈라지면 자동으로 3군 / (b) 항상 3군(토요일은 사실상 폴백) | (a). 봄학기 시뮬에서 주말 통과율 23~36% → 96~97% | E2 셀 키 |
| **Q33 (신규)** | 오너 게이트(n≥4) 위에 품질 조건(셀 IQR 상한 등)을 기본으로 켤까요? | (a) 기본 off, 관리자 화면에 편별 최근 오차 표시 + 방향 단위 자동 중지만 / (b) IQR≤10분 기본 on | (a). 시뮬에서 IQR 조건은 적용률만 크게 깎고 꼬리는 거의 못 줄입니다(덕하발 평일 통과 100%→56%, p90 32→29분). 꼬리는 D′ 매칭으로 줄입니다 | E2 기본값 |
| Q31 | 정리 범위를 어디까지 할까요? dead 상수, `/info` 513 정적 경고, Tips의 낡은 문구('이전 1147번', '이전에 133', `info.html:69-71` `[origin]`), changelog 편집의 감사·백업 누락 | 날짜 문구는 N0, 나머지는 N1과 정리 PR / 전부 별도 | 전자 | N1, 정리 PR |

---

## 6. 리스크

| # | 리스크 | 근거 | 완화 |
|---|---|---|---|
| 1 | **10/3 기한을 놓칠 위험.** 작업일 사흘, 공휴일 연속 | `holiday_cache.json` | N0를 작게 유지합니다(구현 재사용). 대체 경로 세 단계(§1.6) |
| 2 | **배포 경로가 불명확.** 번들 스크립트가 A/B 브랜치의 작업 트리와 `data/`를 묶고, 운영 버전을 모름 | S6, `build-bus-tar.sh:38,72-81` | 깨끗한 체크아웃에서 코드만 교체(Q2). 운영 버전을 먼저 확인 |
| 3 | **병행 브랜치 충돌.** `feat/deadline-notices`, `feat/route-map-geo-ab`, `feat/route-map-redesign`, `feat/743-effective-oct3`가 같은 파일을 만짐. 오너 브랜치와 origin/master 사이 충돌 14구간 | `git branch -a`, `git merge-tree` | 순서를 고정합니다: N0 → R0 → G0. R0는 10/3 이후 |
| 4 | **override 우선.** 운영 `via_overrides.json`에 날짜 문구가 있으면 N0-b가 무력화됨 | `board.py:67-70` | 배포 전 grep(Q9) |
| 5 | **seed와 live 규칙.** 운영에 live 파일이 이미 있으면 새 seed 공지가 자동으로 나오지 않음 | `seed_drift` :457 | N0-c 체크리스트에 "seed 가져오기" 포함 |
| 6 | **시간표 JSON 부정확.** 폴백으로 보여 주는 기점 시각 자체가 틀릴 수 있음. 1115 UNIST 출발도 마찬가지 | 일치율 18~40%(513), 26~29%(1115) | "(시간표)" 표기를 필수로. E2 drift 경보, Q19 |
| 7 | **예측 표본 공백.** 6/2 이후 이력이 없고 운영 DB도 확인하지 못함 | 로컬 16행, `logs.tsv`는 6/1까지 | V1은 예측과 무관하게 진행. E2는 그림자로 누적. 표본이 없으면 폴백이 영구 기본값 |
| 8 | **매칭 규칙 민감도.** 전진 검증 결과가 규칙에 따라 p90 7.4분과 29.3분으로 갈림. 평가 표본은 10일 | §2.3 표 | 규칙을 바꾸면 오프라인 재검증 필수. 자동 중지(p80 > 8분) |
| 9 | **관측 누락 편향.** 234 기록률 68~69%, 기점 관측률 37~57% | §2.3 | 게이트에 날짜 수와 전진 n 조건을 둠 |
| 10 | **BIS 노선당 1대 가정.** 스냅샷 관찰에 근거한 추론 | 196040236 payload | 틀리면 예측 행이 덜 사라질 뿐이고, 잘못된 순위는 생기지 않음 |
| 11 | **체감 변화.** 513이 main에서 빠진 것처럼 보일 수 있음(Q11 (b)면 live는 남음) | — | 기점 구역을 main 바로 아래에 두고 changelog와 공지로 안내 |
| 12 | **743·1115 이력 무효.** 10/3 이후 소요 이력과 추적 목록이 낡음 | `ROUTE_CHANGES`, `constants.py:45-56` | `history_epoch`로 표본 차단. N1에서 추적 목록 갱신(Q23) |
| 13 | **계약 테스트 오탐.** changelog 이력의 "10월 3일부터"가 정규식에 걸림 | `[HEAD] data/changelog.json` | 변경이력 섹션은 검사에서 제외(§1.6) |
| 14 | **XSS.** 공지 본문에 `\|safe`를 쓰면 저장형 XSS | 자동 이스케이프, 링크 화이트리스트(`test_live_file_overrides_seed_and_escapes_text`) | PR 체크리스트에 `\|safe` 금지 |
| 15 | **API 실패가 `[]`로 캐시됨.** 실시간이 조용히 사라짐 | `[origin] api-usage.md` §4 | X1(Q21) |
| 16 | **보안.** 로컬과 (아마도) 운영 로그에 serviceKey 평문 | `logs/bushexa-arrival.log`, PM-016 | 키 교체와 로그 정리(Q30) |
| 17 | **부분 적용.** 화면 하나만 바꾸면 화면 간 분류가 어긋남 | 관계 판정 규칙 세 벌 | G0 동치성 테스트(T-G8)를 먼저. V1과 V2를 연속 배포 |