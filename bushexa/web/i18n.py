"""Lightweight in-house i18n for Bus HeXA (Korean default, English secondary).

Design: "최소 인프라 + 점진 적용" — no Flask-Babel/gettext, no heavy deps.

Public API
----------
translate(key, lang, **kw) -> str : a.k.a. t(); kw는 str.format 플레이스홀더
resolve_lang(request) -> str      : ?lang= → cookie → Accept-Language → "ko"
localize_stop(raw, lang, names)   : 정류소 이름 번역(ADR-014, 렌더 계층 전용)
lang_url(request, lang) -> str    : 현재 URL의 쿼리를 보존한 채 lang만 교체
SUPPORTED_LANGS : list[str]
DEFAULT_LANG     : str

How to extend coverage incrementally
-------------------------------------
1. Add a new key/value pair to TRANSLATIONS below (ko + en).
2. In the template, replace the Korean literal with {{ t('your.new.key') }}.
   That's it — other templates keep their Korean literals (they still work because
   t() is only called where you explicitly use it, and untouched templates just
   render their own Korean strings directly).
3. If a key is missing or mis-spelled, translate() returns the key itself as a
   visible marker so you notice it during development — no silent breakage.
"""

from __future__ import annotations

import re
from urllib.parse import urlencode

from bushexa.data.constants import clean_stop_name

SUPPORTED_LANGS: list[str] = ["ko", "en"]
DEFAULT_LANG: str = "ko"

# ---------------------------------------------------------------------------
# Translation dictionary
# TRANSLATIONS[key][lang] = string
# Keys use dot-notation: section.name
# ---------------------------------------------------------------------------
TRANSLATIONS: dict[str, dict[str, str]] = {
    # ── Shell: nav group titles ────────────────────────────────────────────
    "nav.group.information": {"ko": "Information",  "en": "Information"},
    "nav.group.timetable":   {"ko": "Timetable",    "en": "Timetable"},
    "nav.group.tracking":    {"ko": "Tracking",     "en": "Tracking"},

    # ── Shell: nav link labels ─────────────────────────────────────────────
    "nav.info":             {"ko": "버스정보",            "en": "Bus Info"},
    "nav.busno":            {"ko": "버스번호별",           "en": "By Route No."},
    "nav.running":          {"ko": "Running Log",        "en": "Running Log"},
    "nav.unist_timetable":  {"ko": "UNIST Timetable",   "en": "UNIST Timetable"},
    "nav.unist_board":      {"ko": "From UNIST",        "en": "From UNIST"},
    "nav.stops":            {"ko": "To UNIST",          "en": "To UNIST"},
    "nav.board":            {"ko": "Departure Board",   "en": "Departure Board"},
    "nav.busan":            {"ko": "부산 가는 길",       "en": "To Busan"},
    "nav.seoul":            {"ko": "서울 가는 길",       "en": "To Seoul"},

    # ── 서울 가는 길 (/seoul) ──
    "seoul.title":          {"ko": "서울 가는 길", "en": "Getting to Seoul"},
    "seoul.intro":          {"ko": "513으로 울산역까지 간 뒤 KTX로 서울역·수서역에 갑니다. '발차 안내판' 보기에서 정차역도 볼 수 있습니다.",
                             "en": "Take bus 513 to Ulsan Station, then KTX to Seoul or Suseo. Switch to the departure board view to see stops."},
    "seoul.step1":          {"ko": "UNIST → 울산역", "en": "UNIST → Ulsan Station"},
    "seoul.step2":          {"ko": "울산역 발차 안내", "en": "Ulsan Station departures"},
    "seoul.board_hint":     {"ko": "불 켜진 역에 섭니다", "en": "Lit stations are stops"},
    "seoul.col.to_seoul":   {"ko": "서울역 KTX", "en": "KTX to Seoul"},
    "seoul.col.to_suseo":   {"ko": "수서역 KTX", "en": "KTX to Suseo"},
    "seoul.tab.all":        {"ko": "전체", "en": "All"},
    "seoul.tab.seoul":      {"ko": "서울역", "en": "Seoul"},
    "seoul.tab.suseo":      {"ko": "수서역", "en": "Suseo"},
    "seoul.missing":        {"ko": "{dest}행 열차 시간표를 아직 받지 못했습니다.", "en": "Timetable to {dest} is not available yet."},
    "seoul.stops_note":     {"ko": "정차역은 같은 시각에 울산역을 떠나는 열차가 각 역행 조회에도 나오는지로 판단합니다(국토교통부 TAGO). 오늘·내일 열차만 표시합니다.",
                             "en": "Stops are inferred from MOLIT TAGO timetables (same departure time from Ulsan). Shown for today and tomorrow only."},
    # ── 역 발차 안내판 (macros/_rail_board.html) ──
    "rb.aria":              {"ko": "열차 발차 안내", "en": "Train departures"},
    "rb.col.dep":           {"ko": "출발", "en": "Dep"},
    "rb.col.type":          {"ko": "종별", "en": "Type"},
    "rb.col.dest":          {"ko": "행선", "en": "To"},
    "rb.col.arr":           {"ko": "도착", "en": "Arr"},
    "rb.bound":             {"ko": "행", "en": "bound"},
    "rb.connect":           {"ko": "지금 오는 513으로 연결", "en": "Reachable by the next 513"},
    "rb.soon":              {"ko": "곧 출발", "en": "Departing"},
    "rb.left":              {"ko": "{min}분 후", "en": "in {min} min"},
    "rb.stops":             {"ko": "정차역", "en": "Stops"},
    "rb.marquee":           {"ko": "{origin} 출발 → {stops} 정차 → {dest} {arr} 도착", "en": "{origin} → stops at {stops} → {dest} arr. {arr}"},
    "rb.marquee_direct":    {"ko": "{origin} → {dest} 직행 · {arr} 도착", "en": "{origin} → {dest} direct · arr. {arr}"},
    "rb.view":              {"ko": "보기", "en": "View"},
    "rb.view.table":        {"ko": "표", "en": "Table"},
    "rb.view.board":        {"ko": "발차 안내판", "en": "Departure board"},
    "rb.no_stops":          {"ko": "정차역 정보 없음", "en": "Stop information unavailable"},
    "rb.empty":             {"ko": "오늘 남은 열차가 없습니다.", "en": "No more trains today."},
    # ── 부산 가는 길 (/busan) ──
    "busan.title":          {"ko": "부산 가는 길", "en": "Getting to Busan"},
    "busan.intro":          {"ko": "지금 UNIST에서 출발하면 어떤 차를 이어 타고 언제 도착하는지 목적지별로 보여 줍니다.",
                             "en": "Next connections from UNIST to Busan, by destination."},
    "busan.as_of":          {"ko": "{time} 기준", "en": "As of {time}"},
    "busan.r1.title":       {"ko": "부산역", "en": "Busan Station"},
    "busan.r1.via":         {"ko": "513 → 울산역 → KTX", "en": "Bus 513 → Ulsan Station → KTX"},
    "busan.r2.title":       {"ko": "노포", "en": "Nopo"},
    "busan.r2.via":         {"ko": "743·753 → 좋은삼정병원앞 환승 → 1224", "en": "Bus 743/753 → transfer at Joeun Samjeong Hospital → Bus 1224"},
    "busan.r3.title":       {"ko": "벡스코 · 부전", "en": "BEXCO · Bujeon"},
    "busan.r3.via":         {"ko": "버스 → 태화강역 → 동해선", "en": "Bus → Taehwagang Station → Donghae Line"},
    "busan.col.bus":        {"ko": "버스", "en": "Bus"},
    "busan.col.unist_arr":  {"ko": "UNIST 도착", "en": "At UNIST"},
    "busan.col.unist_dep":  {"ko": "UNIST 출발", "en": "Leaves UNIST"},
    "busan.col.station":    {"ko": "울산역 도착(예상)", "en": "Ulsan Stn (est.)"},
    "busan.col.ktx":        {"ko": "KTX 출발", "en": "KTX dep."},
    "busan.col.busan_arr":  {"ko": "부산역 도착", "en": "Busan arr."},
    "busan.col.taehwagang": {"ko": "태화강역(예상)", "en": "Taehwagang (est.)"},
    "busan.col.metro":      {"ko": "동해선 출발", "en": "Donghae Line dep."},
    "busan.col.bexco":      {"ko": "벡스코", "en": "BEXCO"},
    "busan.col.bujeon":     {"ko": "부전", "en": "Bujeon"},
    "busan.col.dep":        {"ko": "출발", "en": "Dep."},
    "busan.col.arr":        {"ko": "도착", "en": "Arr."},
    "busan.col.train":      {"ko": "열차", "en": "Train"},
    "busan.in_min":         {"ko": "{min}분 후", "en": "in {min} min"},
    "busan.live_513":       {"ko": "UNIST로 오는 513(울산역 방면) 실시간", "en": "Live: bus 513 toward Ulsan Station"},
    "busan.no_live_513":    {"ko": "지금 UNIST로 오는 513(울산역 방면) 실시간 정보가 없습니다.",
                             "en": "No live bus 513 (toward Ulsan Station) approaching UNIST right now."},
    "busan.origin_513":     {"ko": "513 덕하 출발 시각 — UNIST 통과 시각이 아닙니다(UNIST까지 보통 1시간 안팎, 편차 큼)",
                             "en": "Bus 513 departures from Deokha — not UNIST times (usually about 1 hour to UNIST, varies a lot)"},
    "busan.ktx_next":       {"ko": "울산역 → 부산역 KTX", "en": "KTX Ulsan → Busan"},
    "busan.note_513":       {"ko": "울산역 도착은 UNIST 도착 + {min}분(2026년 4~6월 기록 중앙값)으로 계산하고, KTX는 {transfer}분 여유를 두고 고릅니다.",
                             "en": "Ulsan Station arrival = UNIST + {min} min (median, Apr–Jun 2026 records); KTX chosen with a {transfer}-min margin."},
    "busan.rail_missing":   {"ko": "열차 시간표를 아직 받지 못했습니다.", "en": "Train timetable not available yet."},
    "busan.rail_suspect":   {"ko": "오늘 열차가 평소보다 훨씬 적게 조회되었습니다. 코레일에서 확인하세요.",
                             "en": "Far fewer trains than usual were listed for today. Please check with Korail."},
    "busan.no_more_trains": {"ko": "오늘 남은 열차가 없습니다.", "en": "No more trains today."},
    "busan.no_more_buses":  {"ko": "오늘 남은 버스가 없습니다.", "en": "No more buses today."},
    "busan.no_connection":  {"ko": "연결 없음", "en": "No connection"},
    "busan.r2.pending":     {"ko": "1224번 시간표와 좋은삼정병원앞 환승 정보는 준비 중입니다. 우선 743·753의 UNIST 출발 시각을 보여 줍니다.",
                             "en": "Bus 1224 timetable and transfer details are in preparation. Showing bus 743/753 departures from UNIST for now."},
    "busan.r3.note":        {"ko": "태화강역 도착은 노선별 기록 중앙값(2026년 4~6월)으로 계산하고, 정류장에서 승강장까지 5~8분 여유를 둔 뒤 첫 동해선을 고릅니다. 벡스코·부전 도착은 동해선 시간표 기준입니다.",
                             "en": "Taehwagang arrival uses per-route median travel times (Apr–Jun 2026); the first Donghae Line train is chosen after a 5–8 min walk."},
    "busan.metro_saturday": {"ko": "토요일은 휴일 시간표로 안내합니다.", "en": "Saturday uses the holiday timetable."},
    "busan.metro_missing":  {"ko": "동해선 시간표를 아직 받지 못했습니다.", "en": "Donghae Line timetable not available yet."},
    "busan.intercity":      {"ko": "태화강역 → 부전 일반·고속열차 (KTX-이음·ITX-마음·무궁화)", "en": "Taehwagang → Bujeon intercity trains (KTX-Eum, ITX-Maeum, Mugunghwa)"},
    "busan.arrival_error":  {"ko": "실시간 정보를 가져오지 못했습니다. 시간표 정보만 표시합니다.",
                             "en": "Live information is unavailable. Showing timetables only."},
    "busan.source":         {"ko": "열차: 국토교통부 TAGO 시간표(매일 갱신). 예상 시각은 참고용이며 실제와 다를 수 있습니다.",
                             "en": "Trains: MOLIT TAGO timetables (updated daily). Estimated times are for reference only."},

    # ── Shell: footer & default page title ────────────────────────────────
    "footer.made_by":       {"ko": "Made by",            "en": "Made by"},
    "footer.credit":        {"ko": "UNIST 통학버스 정보 시스템 · Made by", "en": "UNIST Bus Info System · Made by"},
    "page.default_title":   {"ko": "UNIST 버스정보",      "en": "UNIST Bus Info"},

    # ── Admin nav ──────────────────────────────────────────────────────────
    "admin.nav.group.admin":    {"ko": "Admin",       "en": "Admin"},
    "admin.nav.group.site":     {"ko": "Site",        "en": "Site"},
    "admin.nav.dashboard":      {"ko": "대시보드",      "en": "Dashboard"},
    "admin.nav.data_browser":   {"ko": "데이터 브라우저", "en": "Data Browser"},
    "admin.nav.timetable":      {"ko": "시간표 편집",    "en": "Timetable Edit"},
    "admin.nav.via":            {"ko": "경유지 편집",    "en": "Via Stop Edit"},
    "admin.nav.holidays":       {"ko": "공휴일 관리",    "en": "Holiday Mgmt"},
    "admin.nav.special":        {"ko": "특별 시간표",    "en": "Special Timetable"},
    "admin.nav.changelog":      {"ko": "변경이력 관리",  "en": "Changelog"},
    "admin.nav.logs":           {"ko": "로그",          "en": "Logs"},
    "admin.nav.password":       {"ko": "비밀번호 변경",  "en": "Change Password"},
    "admin.nav.public_site":    {"ko": "공개 사이트",    "en": "Public Site"},
    "admin.nav.logout":         {"ko": "로그아웃",       "en": "Log out"},

    # ── Board page ─────────────────────────────────────────────────────────
    "board.title":          {"ko": "UNIST 출발안내",      "en": "UNIST Departures"},
    "board.notice.743":    {"ko": "10월 3일부터 743번은 구영리에서 범서중학교를 경유합니다 (513번과 같은 경로, 713·753·1115번과 다름). 자세한 경로는 정보 페이지의 노선도를 확인하세요.",
                            "en": "From Oct 3, bus 743 passes Beomseo Middle School in Guyoung-ri (same as 513; different from 713/753/1115). See the route map on the Info page."},
    "board.page_title":     {"ko": "출발 게시판",          "en": "Departure Board"},
    "board.btn.table":      {"ko": "표",                 "en": "Table"},
    "board.btn.flap":       {"ko": "Split-flap",         "en": "Split-flap"},

    # ── Stop names: parenthetical annotations & direction (ADR-014) ────────
    # 방향 주석은 목적지 이름으로 표기한다: 시내 → Ulsan, 학교/UNIST → UNIST.
    "stop.annot.city":      {"ko": "시내",               "en": "Ulsan"},
    "stop.annot.unist":     {"ko": "UNIST",              "en": "UNIST"},
    "stop.annot.terminus":  {"ko": "종점",               "en": "Terminus"},
    "stop.annot.origin":    {"ko": "기점",               "en": "Origin"},
    "stop.annot.via":       {"ko": "경유",               "en": "Via"},
    "stop.annot.from_date": {"ko": "{date}부터",          "en": "from {date}"},
    "dir.towards":          {"ko": "{stop} 방면",         "en": "To {stop}"},

    # ── Language switcher UI labels ────────────────────────────────────────
    "lang.ko":              {"ko": "한국어",              "en": "한국어"},
    "lang.en":              {"ko": "English",            "en": "English"},
}


def translate(key: str, lang: str, **kwargs: object) -> str:
    """Return the translation for *key* in *lang*.

    Fallback chain:
      1. requested lang
      2. DEFAULT_LANG ("ko")
      3. the key itself (so untranslated keys are visible, not broken)

    *kwargs* fill ``{name}`` placeholders via ``str.format``. A missing placeholder
    returns the unformatted template rather than raising (render must not 500).
    """
    entry = TRANSLATIONS.get(key)
    if entry is None:
        return key
    text = entry.get(lang) or entry.get(DEFAULT_LANG) or key
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            return text
    return text


# Convenient alias used by templates via context processor.
t = translate


def resolve_lang(request) -> str:  # type: ignore[type-arg]
    """Determine the active language for *request*.

    Resolution order:
      1. ``?lang=`` query parameter (if valid)
      2. ``lang`` cookie
      3. ``Accept-Language`` best match (first visit only — explicit choice wins)
      4. DEFAULT_LANG ("ko")
    """
    q = request.args.get("lang", "")
    if q in SUPPORTED_LANGS:
        return q
    cookie = request.cookies.get("lang", "")
    if cookie in SUPPORTED_LANGS:
        return cookie
    return request.accept_languages.best_match(SUPPORTED_LANGS, default=DEFAULT_LANG)


def lang_url(request, lang: str) -> str:  # type: ignore[type-arg]
    """현재 경로 + 기존 쿼리(반복 키 포함)를 보존하고 ``lang``만 교체한 URL."""
    params = [(k, v) for k, vs in request.args.lists() if k != "lang" for v in vs]
    params.append(("lang", lang))
    return f"{request.path}?{urlencode(params)}"


# ---------------------------------------------------------------------------
# Stop names (ADR-014) — 한국어 원문은 도메인·DB에 그대로 두고 렌더 직전에만 번역한다.
# 사전 자체(StopNames)는 bushexa.services.stop_name_dict 가 관리자 편집 파일에서 로드한다.
# ---------------------------------------------------------------------------

_ANNOT_KEYS: dict[str, str] = {
    "시내": "stop.annot.city",
    "시내방향": "stop.annot.city",
    "시내 방향": "stop.annot.city",
    "시내 방면": "stop.annot.city",
    "UNIST": "stop.annot.unist",
    "학교": "stop.annot.unist",
    "종점": "stop.annot.terminus",
    "기점": "stop.annot.origin",
    "경유": "stop.annot.via",
}
_PAREN_RE = re.compile(r"\(([^)]*)\)")
_FROM_DATE_RE = re.compile(r"^(\d{1,2}/\d{1,2})\s*부터$")
_TOWARDS_SUFFIX = "방면"
_JOIN = " - "


def _localize_annotation(part: str, lang: str, names) -> str:
    part = part.strip()
    key = _ANNOT_KEYS.get(part)
    if key:
        return translate(key, lang)
    m = _FROM_DATE_RE.match(part)
    if m:
        return translate("stop.annot.from_date", lang, date=m.group(1))
    return names.lookup(part, lang) or part


def localize_stop(raw: str, lang: str, names) -> str:
    """정류소 이름(또는 그 조합)을 *lang*으로 표시할 문자열로 바꾼다.

    - ``ko``(또는 빈 값)는 원문 그대로(비용 0).
    - ``"천상 - 구영리 - 명촌 (종점)"`` 같은 경유 문자열은 `` - `` 토큰별로 번역.
    - ``"명촌 (시내) 방면"`` → ``dir.towards``(en ``"To Myeongchon (Ulsan)"``).
    - ``"진목회관 (시내)"`` → 기준명은 사전, 괄호 주석은 ``stop.annot.*`` 어휘(없으면 사전, 그래도 없으면 원문).
    - 사전에 없는 기준명은 한국어 원문을 유지한다(깨지지 않는 폴백).
    """
    if not raw or lang == DEFAULT_LANG:
        return raw
    if _JOIN in raw:
        return _JOIN.join(localize_stop(tok, lang, names) for tok in raw.split(_JOIN))
    stripped = raw.strip()
    if stripped.endswith(_TOWARDS_SUFFIX) and stripped != _TOWARDS_SUFFIX:
        inner = stripped[: -len(_TOWARDS_SUFFIX)].strip()
        return translate("dir.towards", lang, stop=localize_stop(inner, lang, names))
    base = clean_stop_name(stripped)
    out = names.lookup(base, lang) or base
    for annot in _PAREN_RE.findall(stripped):
        parts = [_localize_annotation(p, lang, names) for p in annot.split(",")]
        out += f" ({', '.join(parts)})"
    return out
