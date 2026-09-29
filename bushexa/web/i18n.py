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
