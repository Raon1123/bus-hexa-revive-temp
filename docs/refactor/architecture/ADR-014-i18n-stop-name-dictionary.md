---
status: draft
adr_id: ADR-014
designer: opus
auditor_status: pending
last_updated: 2026-09-29
supersedes: null
superseded_by: null
---

# ADR-014 — 다국어(ko/en) 확장: UI 문자열은 코드 사전, 정류소 이름은 관리자가 편집하는 1:1 사전

## 컨텍스트

### 현재 상태 (master `4d192f9` 기준)

- `bushexa/web/i18n.py`에 자체 i18n 뼈대가 있다: `TRANSLATIONS[key][lang]`, `translate(key, lang)`,
  `resolve_lang(request)`(`?lang=` → `lang` 쿠키 → `"ko"`), `SUPPORTED_LANGS = ["ko", "en"]`.
- `web/app.py`가 `before_request`로 `g.lang`을 정하고, context processor로 `lang`, `t(key)`를
  모든 템플릿에 주입하며, `?lang=`가 오면 1년 쿠키를 심는다. `tests/web/test_i18n.py` 존재.
- **적용 범위가 매우 좁다.** `t()` 호출은 `_base.html`(14) · `board.html`(6) · `unist_board.html`(1)뿐.
  나머지 공개 템플릿(`info`, `busno`, `stops`, `running`, `unist_timetable`, `board_lite`,
  `partial/board_table` 등)은 한국어 리터럴을 직접 렌더한다.

### 번역 대상 문자열의 출처 (조사 결과)

| 출처 | 예 | 성격 |
|---|---|---|
| 템플릿 리터럴 | `info.html`, `busno.html`, `partial/board_table.html` | 고정 UI 문구 |
| 도메인 f-string | `domain/board.py:163` `f"{departure} 출발 예정"`, `domain/unist_board.py:82` `f"{stop} {m}분{s}초"` | 값 + 문구 조합 |
| 상수 | `WEEKDAY_STR`, `UNIST_STR`, `UNISTBUS`, `ROUTEID[*][1]` `"명촌 (시내) 방면"` | 고정 라벨 |
| 정류소 이름 (상수) | `STOP_IDS` 60여 개, 예 `"울산과학기술원정문 (시내)"` | **고유명사** |
| 정류소 이름 (조합 문자열) | `VIA_STOPS` / `via_overrides.json` `"천상 - 구영리 - 굴화주공 - …"` | 고유명사 나열 |
| 정류소 이름 (약칭) | `web/route_diagram.py` `"구영"`, `"범서중"`, `"산단캠"` | 고유명사 약칭 |
| 정류소 이름 (실시간) | Ulsan BIS `present_stop`, TAGO `nodenm` | **외부 API가 주는 임의 문자열** |
| 관리자 편집 콘텐츠 | 변경이력(`changelog.json`), 출발 게시판 공지 | 운영자 작성 자유 텍스트 |

### 정류소 이름이 특별한 이유

1. 고유명사라 기계적 번역이 불가능하고, 로마자 표기·약칭("UNIST" vs "Ulsan National Institute of
   Science and Technology")에 **운영 판단**이 필요하다. 노선 개편(예: 743 범서중 경유) 때마다 바뀐다.
2. 같은 이름이 여러 node_id에 붙는다(`공업탑` × 4). 반대로 이름은 여러 출처(상수·경유 문자열·
   노선도 약칭·실시간 API)에서 온다. → **node_id가 아니라 한국어 이름을 키로** 해야 모든 출처를
   하나의 사전으로 덮을 수 있다.
3. 한국어 `STOP_IDS` 값은 **표시 전용이 아니다.** `composite_location`이 이름→node_id 역인덱스를
   만들고, `recorder`가 `bus_timelog.stop_name`에 기록한다. → **번역은 렌더 계층에서만** 하고
   도메인·DB·역인덱스의 한국어 원문은 절대 바꾸지 않는다.

### 사용자 지시

> 정류소 이름의 경우에는 1-1 매칭이 되는 dict set을 만들고 이것을 직접 관리자 페이지에서
> 조절할 수 있게 하는게 맞겠다.

## 결정

번역 자원을 **두 층으로 분리**한다.

1. **UI 문구 → 코드 사전(`web/i18n.py` `TRANSLATIONS`)**. 개발자가 템플릿과 함께 관리하고 리뷰로 검증.
   값을 끼워 넣는 문구는 `str.format` 플레이스홀더를 쓰도록 `translate(key, lang, **kwargs)`로 확장.
2. **정류소 이름 → 관리자 편집 1:1 사전(`stop_names.json`)**. 한국어 기준명 ↔ 대상 언어명의 전단사(bijection).
   관리자 페이지 `/admin/stop-names`에서 편집. 코드에는 시드(seed)만 두고, 운영값은 `data_dir` override.

한국어가 원문(source of truth)이며, 번역이 없으면 **항상 한국어로 폴백**한다(깨지지 않음).

## 설계 상세

### 1. UI 문구 (코드 사전)

- `translate(key, lang, **kwargs)`: 기존 폴백 체인(lang → ko → key) 뒤에 `kwargs`가 있으면 `.format(**kwargs)`.
  템플릿: `{{ t('board.depart_scheduled', time=row.departure) }}`.
- **도메인은 문장을 만들지 않는다.** `f"{departure} 출발 예정"` 같은 조합은 도메인이 구조화된 값
  (`kind="scheduled", time="08:10"` / `kind="live", stop=…, seconds=…`)만 돌려주고, 템플릿이
  `t()`로 문장을 만든다. 도메인 테스트는 값만 검증하게 되어 오히려 단순해진다.
- 상수 라벨(`WEEKDAY_STR` 등)은 키를 부여해 사전으로 옮기고, 상수 자체는 한국어 폴백으로 유지.
- 방면 문구 `"명촌 (시내) 방면"` → `t('dir.towards', stop=stop_name(…))` = ko `"{stop} 방면"`, en `"To {stop}"`.
- **적용 범위: 공개 페이지만.** 관리자 화면은 운영자가 한국어 사용자이므로 번역하지 않는다
  (현재 `admin.nav.*` 키는 유지하되 확장하지 않음).
- 관리자 작성 자유 텍스트(변경이력·공지)는 Phase 3에서 선택적 `en` 필드로 다룬다(없으면 ko 표시).

### 2. 정류소 이름 사전 (1:1)

#### 저장 형식

`<data_dir>/stop_names.json` (운영 override), 시드는 `bushexa/data/stop_names.seed.json`.

```json
{
  "version": 1,
  "en": {
    "울산과학기술원": "UNIST",
    "울산과학기술원정문": "UNIST Main Gate",
    "굴화주공 아파트앞": "Gulhwa Jugong Apt.",
    "공업탑": "Gongeoptap Rotary"
  }
}
```

- 최상위가 언어별 dict의 **set**이다(`"en"`, 향후 `"zh"`, `"ja"` 추가 시 같은 구조).
- **키 = 괄호 주석을 뗀 기준명**(`clean_stop_name()` 결과). `"울산과학기술원정문 (시내)"`와
  `"울산과학기술원정문 (학교)"`는 같은 키 하나로 번역된다.
- 로드 우선순위: **override 파일 > 시드 > (없음 → 한국어 원문)**. 파일 부재·파손 시 시드로 동작(ADR-013).
- 쓰기는 `atomic_write_json`(ADR-012)만 사용.

#### 1:1(전단사) 불변식

저장 시 검증하고, 위반하면 저장을 거부하고 해당 행을 표시한다.

- 한국어 키 유일 — dict 구조상 자동 보장.
- **대상 언어 값 유일** — 대소문자·앞뒤 공백 무시 비교로 중복 금지.
  → 영어 이름만 보고 한국어 정류소를 되짚을 수 있어야 한다(향후 영문 검색·역조회, 안내 혼동 방지).
- 빈 값 = "번역 없음"(항목 삭제와 동일, 한국어 폴백). 길이 상한(예: 60자), 제어문자 금지.
- 주의: 약칭과 정식명이 둘 다 키로 존재하면(`"범서중"`, `"범서중학교앞"`) 영어 값도 서로 달라야 한다
  (`"Beomseo Mid."` / `"Beomseo Middle School"`). 편집 화면에서 이 제약을 안내한다.

#### 괄호 주석과 방면 표기

`"진목회관 (UNIST)"`처럼 주석이 붙은 이름은 **기준명 + 주석**으로 분해해 따로 번역한다.

- 기준명 → 정류소 사전.
- 주석 → 코드 사전의 고정 어휘 `stop.annot.*`: `시내`→`to City`, `UNIST`→`to UNIST`, `종점`→`Terminus`,
  `기점`→`Origin`, `경유`→`Via`, `학교`→`Campus side` 등. 어휘에 없으면 주석을 정류소 사전으로 한 번 더
  시도(`"울산역"` 같은 지명 주석)하고, 그래도 없으면 원문 유지.
- 구현: `localize_stop(raw: str, lang: str) -> str` 하나로 모은다. `ko`면 즉시 원문 반환(비용 0).

#### 조합 문자열

- 경유지 `"천상 - 구영리 - 굴화주공 - … - 명촌 (종점)"`: `" - "`로 분리 → 토큰별 `localize_stop` → 재결합.
  (경유지 편집기는 한국어 원문만 편집하고, 번역은 정류소 사전이 자동 적용 — 편집 지점이 하나로 유지된다.)
- 노선도 라벨(`route_diagram.py`): 컬럼 배치 키는 한국어 그대로 두고, **SVG에 그리는 텍스트만** 번역.
  약칭(`"구영"`, `"산단캠"`)도 사전의 독립 키로 등록한다.

#### 적용 지점 (렌더 계층)

- Jinja 필터 `{{ name | stop }}` (내부에서 `g.lang` 사용) 를 등록. 템플릿의 정류소 출력부에 적용.
- `route_diagram.py`는 SVG 생성 함수에 `lang` 인자를 받아 라벨에만 적용.
- **도메인·recorder·composite_location·DB는 변경하지 않는다.** (역인덱스·기록은 계속 한국어.)

#### 캐시와 멀티워커

- 요청마다 파일을 파싱하지 않도록 `(path, st_mtime_ns)` 키 메모이즈. 매 요청 `stat()` 1회로
  다른 gunicorn 워커의 저장도 즉시 반영된다(`via_overrides.json`과 같은 파일 기반 정합 모델).

### 3. 관리자 페이지 `/admin/stop-names`

- 화면: 행 = 한국어 기준명, 열 = 언어별 입력칸(현재 `en`), 상태 배지 `번역됨 / 미번역 / 고아`.
- **카탈로그(행 목록) 자동 수집** — 운영자가 키를 손으로 입력하지 않게:
  1. `STOP_IDS` 값의 기준명, 2. `VIA_STOPS` + `via_overrides.json` 토큰,
  3. `ROUTEID` 방면·종점명, 4. `route_diagram` 라벨,
  5. `bus_timelog`의 `DISTINCT stop_name`(실시간으로 관측된 이름; 읽기 전용 쿼리).
  - 카탈로그에 없지만 사전에 있는 키 = **고아**(노선 개편으로 사라진 정류소) → 삭제 후보로 표시.
- 필터(미번역만 보기), 검색, 저장 시 1:1 검증 오류를 행 단위로 표시.
- CSV 내보내기/가져오기(선택) — 대량 초기 입력용. 가져오기도 같은 검증을 통과해야 저장.
- `login_required`, `_audit("stop_names.save", changed=n, lang="en")`, 관리자 nav에 항목 추가.
- `services/backup.py` 백업 화이트리스트에 `stop_names.json` 추가.
- 서비스 계층: `services/stop_name_dict.py` — `StopNameDict(path, seed_path)`의 `load()/save()/validate()`,
  기존 `ViaEditor`와 같은 모양.

### 4. 언어 선택 UX · 기타

- **버그 수정:** `_base.html` 언어 전환 링크가 `{{ request.path }}?lang=…`라서 `/busno?bus=713`,
  `/running?route_id=…`, `/stops?stop_id=…`의 기존 쿼리를 잃는다. → 기존 `request.args`를 보존하고
  `lang`만 덮어쓰는 URL 헬퍼로 교체.
- 첫 방문 기본값: `Accept-Language`가 `en`으로 시작하면 `en`(쿠키가 없을 때만). 명시 선택이 항상 우선.
- 언어별로 응답이 달라지므로 공개 페이지 응답에 `Vary: Cookie, Accept-Language` 부여(프록시 캐시 대비).
- HTMX 부분 갱신 요청은 쿠키로 언어가 따라가므로 추가 작업 불필요(테스트로 고정).
- `board_lite`(키오스크): URL `?lang=`로 고정하는 방식을 기본으로 한다. ko/en 교대 표시는 후속 결정.
- 숫자·시각(`HH:MM`)은 언어 무관 동일 표기. "3분 20초" 류만 `t()` 템플릿으로.

## 대안

### 대안 A — Flask-Babel / gettext (.po)
- 장점: 표준 도구, 복수형·로케일 포맷 지원.
- 단점: 추출·컴파일 단계와 의존성 추가, 런타임 편집 불가(정류소 이름을 관리자가 못 고침).
- 기각 사유: 문구 수가 수백 개 수준이고 이미 경량 뼈대가 있다. 정류소 이름은 어차피 런타임 편집이 필요.

### 대안 B — 정류소 이름도 코드 사전(`TRANSLATIONS`)에 넣기
- 장점: 저장소 하나, 구현 최소.
- 단점: 노선 개편마다 배포 필요. 운영자가 직접 고칠 수 없음. 사용자 지시와 불일치.
- 기각 사유: 정류소 이름은 운영 데이터다(경유지 편집기와 같은 성격).

### 대안 C — node_id 키 사전
- 장점: API id와 직접 대응.
- 단점: 경유 문자열·노선도 약칭·실시간 `present_stop`은 id 없이 이름만 온다. `공업탑` × 4처럼 같은
  번역을 여러 번 입력해야 한다.
- 기각 사유: 이름 키가 모든 출처를 한 번에 덮는다.

### 대안 D — 도메인에서 번역된 문자열 생성(`lang`을 도메인까지 전달)
- 장점: 템플릿 변경 적음.
- 단점: 도메인 함수 시그니처 전부 변경, 한국어 원문을 쓰는 역인덱스·recorder와 섞일 위험.
- 기각 사유: 렌더 계층 번역이 경계가 분명하다.

### 대안 E — 자동 번역/로마자 변환 API
- 기각 사유: 고유명사 품질 불안정, 외부 의존, 오프라인 폴백(ADR-013) 원칙과 충돌. 시드 초안 작성에만 참고.

## 결과

### 긍정적 영향
- 외국인 학생·방문자가 공개 페이지를 영어로 사용 가능.
- 정류소 이름 수정이 배포 없이 관리자 화면에서 끝나고, 감사 로그·백업에 포함된다.
- 경유지 편집기는 한국어만 관리 — 번역은 사전이 자동 적용해 이중 편집이 없다.

### 부정적 영향 / 비용
- 템플릿·도메인 반환형 변경량이 크다(도메인 f-string 제거는 기존 테스트 수정 동반).
- 번역 누락은 한국어로 조용히 폴백하므로, 관리자 화면의 "미번역" 수치로 가시성을 확보해야 한다.
- 1:1 제약 때문에 약칭/정식명 영어 값을 일부러 다르게 지어야 한다.

### 따라오는 작업 (Follow-up) — 구현 단계
- **Phase 0 (기반):** `translate(**kwargs)`, `localize_stop`, `| stop` 필터, `StopNameDict` 서비스 + 시드,
  언어 전환 링크 쿼리 보존 버그 수정, `Vary` 헤더, `Accept-Language` 기본값.
- **Phase 1 (공개 UI):** 공개 템플릿 전체 `t()` 전환, 도메인 f-string → 구조화 값, 상수 라벨 키화.
  출발 게시판·UNIST 보드·시간표 우선, 그다음 `info`/`running`/`stops`/`busno`, 마지막 노선도 SVG.
- **Phase 2 (관리자 사전):** `/admin/stop-names` 편집기, 카탈로그 수집, 1:1 검증, 감사·백업 연동, CSV.
- **Phase 3 (선택):** 변경이력·공지의 `en` 필드, `board_lite` 교대 표시.

## 검증 방법

- `uv run pytest tests/web/test_i18n.py tests/services/test_stop_name_dict.py`
  - 전단사 위반(영어 값 중복, 대소문자만 다른 중복) 저장 거부.
  - override 부재/파손 → 시드 폴백, 시드도 없으면 원문.
  - `localize_stop`: 주석 분해, 조합 문자열 분리·재결합, 미등록 이름 원문 유지, `ko`는 항등.
  - mtime 변경 시 캐시 무효화.
- 웹 스모크: 모든 공개 라우트를 `?lang=en`으로 GET → 200, **key 형태 문자열(`board.`, `nav.` 등) 미노출**,
  `?lang=en&bus=713`에서 전환 링크가 `bus=713`을 보존.
- 회귀: `composite_location` 역인덱스·`recorder` 테스트가 변경 없이 통과(한국어 원문 불변 확인).
- 감사: 사전 저장 후 `/admin/audit`에 `stop_names.save` 기록, 백업 ZIP에 `stop_names.json` 포함.

## 미해결 / 후속 결정

- 괄호 주석 영어 어휘 확정(`시내` = "to City" / "Downtown-bound" 중 택일) — 현장 안내판 표기와 맞출지.
- `UNIST` 표기: 모든 영어 화면에서 약칭 `UNIST`로 통일할지.
- `bus_timelog` DISTINCT 스캔 비용 — 데이터가 커지면 최근 N일로 제한.
- 3번째 언어(zh/ja) 도입 여부 — 저장 구조는 이미 대비되어 있음.
- 관리자 화면 번역은 하지 않는 것으로 결정했으나, 외국인 운영자 합류 시 재검토.
